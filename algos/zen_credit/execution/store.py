"""Legacy PostgreSQL regression adapter and shared position record types.

Production algo workers use execution.firestore_store.FirestoreStore.
The implementation below is retained only for the existing isolated test suite.

Render's free web service has an ephemeral disk and restarts routinely, so every
piece of state that must survive lives here: the open/closed positions, signal
ids, email status, the per-minute option-chain snapshots alpha2 needs, the run
ledger and small key/value state (including the NSE holiday cache).

Duplicate protection (unchanged Zen Credit semantics, now on Postgres):

1. ``zc_runs.minute`` is UNIQUE: a minute bucket is processed at most once, so a
   duplicate cron call in the same minute does nothing.
2. ``zc_positions.signal_id`` is UNIQUE and a partial unique index allows only one
   row with ``status = 'open'``: one position at a time, never inserted twice.
3. Email status is stored per position (pending -> sent/failed); a sent email is
   never re-sent, a failed one is retried up to ``max_attempts`` times.
4. A session-level ``pg_try_advisory_lock`` serialises whole cycles across
   processes/instances; a concurrent call gets "busy" without touching state.

Connection handling: a FRESH psycopg connection per cycle (``Store.session``),
closed when the cycle ends -- Neon autosuspends idle compute and terminates open
connections, so nothing is cached across requests. Autocommit, ``connect_timeout``,
connect retried up to 3 times while Neon wakes, schema created on first use (no
migration tool). Neon requires TLS: the URL must include ``?sslmode=require``.
"""
from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from dataclasses import dataclass, fields
from datetime import date, datetime, timedelta

import pandas as pd

from strategy.engine import ExitEvent, Position
from utils.time import IST

log = logging.getLogger(__name__)

ADVISORY_LOCK_KEY = 7_203_115_991        # arbitrary, stable; namespaces this app's lock

SCHEMA = """
CREATE TABLE IF NOT EXISTS zc_positions (
    id                   bigserial PRIMARY KEY,
    signal_id            text UNIQUE NOT NULL,
    status               text NOT NULL DEFAULT 'open',
    strategy_state       text NOT NULL DEFAULT 'IN_POSITION',
    direction            text NOT NULL,
    entry_ts             timestamptz NOT NULL,
    expiry               date NOT NULL,
    option_type          text NOT NULL,
    sell_strike          double precision NOT NULL,
    buy_strike           double precision NOT NULL,
    lots                 integer NOT NULL,
    lot_size             integer NOT NULL,
    units                integer NOT NULL,
    spot_at_entry        double precision,
    sell_price           double precision NOT NULL,
    buy_price            double precision NOT NULL,
    entry_spread_price   double precision NOT NULL,
    net_credit           double precision NOT NULL,
    stop_loss            double precision NOT NULL,
    target               double precision,
    max_loss             double precision NOT NULL,
    max_profit           double precision NOT NULL,
    exit_due             timestamptz NOT NULL,
    alpha                double precision,
    alpha2               double precision,
    exit_ts              timestamptz,
    exit_value           double precision,
    exit_reason          text,
    pnl                  double precision,
    pnl_pct              double precision,
    entry_email_status   text NOT NULL DEFAULT 'pending',
    entry_email_attempts integer NOT NULL DEFAULT 0,
    exit_email_status    text NOT NULL DEFAULT 'none',
    exit_email_attempts  integer NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS zc_positions_one_open ON zc_positions ((status)) WHERE status = 'open';
ALTER TABLE zc_positions ADD COLUMN IF NOT EXISTS allocated_capital double precision;
ALTER TABLE zc_positions ALTER COLUMN target DROP NOT NULL;

CREATE TABLE IF NOT EXISTS zc_option_snapshots (
    id            bigserial PRIMARY KEY,
    minute        timestamptz NOT NULL,
    expiry        date NOT NULL,
    strike        double precision NOT NULL,
    spot          double precision NOT NULL,
    ce_ltp        double precision,
    pe_ltp        double precision,
    ce_bid        double precision,
    ce_ask        double precision,
    pe_bid        double precision,
    pe_ask        double precision,
    ce_cum_volume double precision,
    pe_cum_volume double precision,
    CONSTRAINT uq_snapshot UNIQUE (minute, expiry, strike)
);
CREATE INDEX IF NOT EXISTS zc_option_snapshots_minute ON zc_option_snapshots (minute);

CREATE TABLE IF NOT EXISTS zc_runs (
    id         bigserial PRIMARY KEY,
    minute     timestamptz UNIQUE NOT NULL,
    started_at timestamptz NOT NULL DEFAULT now(),
    result     text NOT NULL DEFAULT 'started',
    detail     text
);

CREATE TABLE IF NOT EXISTS zc_state (
    key   text PRIMARY KEY,
    value text NOT NULL
);
"""

SNAPSHOT_COLUMNS = ["minute", "expiry", "strike", "spot", "ce_ltp", "pe_ltp", "ce_bid", "ce_ask",
                    "pe_bid", "pe_ask", "ce_cum_volume", "pe_cum_volume"]


@dataclass
class PositionRecord:
    """One zc_positions row (attribute access, like the ORM row it replaced)."""
    id: int
    signal_id: str
    status: str
    strategy_state: str
    direction: str
    entry_ts: datetime
    expiry: date
    option_type: str
    sell_strike: float
    buy_strike: float
    lots: int
    lot_size: int
    units: int
    spot_at_entry: float | None
    sell_price: float
    buy_price: float
    entry_spread_price: float
    net_credit: float
    stop_loss: float
    target: float | None
    max_loss: float
    max_profit: float
    exit_due: datetime
    alpha: float | None
    alpha2: float | None
    exit_ts: datetime | None
    exit_value: float | None
    exit_reason: str | None
    pnl: float | None
    pnl_pct: float | None
    entry_email_status: str
    entry_email_attempts: int
    exit_email_status: str
    exit_email_attempts: int
    allocated_capital: float | None


_POSITION_FIELDS = [f.name for f in fields(PositionRecord)]


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=IST) if dt.tzinfo is None else dt.astimezone(IST)


def normalize_dsn(url: str) -> str:
    """psycopg wants postgresql://; drop SQLAlchemy-style driver suffixes."""
    for prefix in ("postgres://", "postgresql+psycopg://", "postgresql+psycopg2://"):
        if url.startswith(prefix):
            return "postgresql://" + url[len(prefix):]
    return url


class StoreUnavailable(RuntimeError):
    """The database could not be reached (e.g. Neon compute still waking up)."""


def is_db_error(exc: BaseException) -> bool:
    """Connection-level failure (includes AdminShutdown: Neon terminated the session)."""
    if isinstance(exc, StoreUnavailable): return True
    try:
        import psycopg
    except ImportError:  # pragma: no cover
        return False
    return isinstance(exc, psycopg.OperationalError)


class Store:
    """Connections are never cached across requests.

    Neon autosuspends idle compute and terminates open connections, so a
    long-lived connection goes stale between cron calls. Each cycle runs inside
    :meth:`session`, which opens a fresh connection (retrying the CONNECT only,
    up to ``connect_retries`` times with short backoff while Neon wakes up) and
    closes it when the cycle ends; the advisory lock is taken and released on
    that same connection. Calls outside a session (status page, tests, CLI) open
    a short-lived connection per call.
    """

    def __init__(self, dsn: str, connect_timeout: int = 10, connect_retries: int = 3,
                 backoff_seconds: float = 1.0, sleep=None):
        if not dsn:
            raise RuntimeError("DATABASE_URL is not set (Neon Postgres connection string required)")
        import time as _time
        self.dsn = normalize_dsn(dsn)
        self.connect_timeout = connect_timeout
        self.connect_retries = max(1, connect_retries)
        self.backoff_seconds = backoff_seconds
        self._sleep = sleep or _time.sleep
        self._conn = None                      # only set while a session is active
        self._schema_ready = False

    # ------------------------------------------------------------ plumbing
    def _open(self):
        """Fresh autocommit connection; retries the connect only. Schema on first use."""
        import psycopg
        last: Exception | None = None
        for attempt in range(1, self.connect_retries + 1):
            try:
                conn = psycopg.connect(self.dsn, autocommit=True, connect_timeout=self.connect_timeout)
                break
            except psycopg.OperationalError as exc:        # includes AdminShutdown
                last = exc
                log.warning("database connect failed (attempt %d/%d): %s", attempt, self.connect_retries,
                            type(exc).__name__)
                if attempt < self.connect_retries:
                    self._sleep(self.backoff_seconds * (2 ** (attempt - 1)))
        else:
            raise StoreUnavailable(f"database unreachable after {self.connect_retries} connect attempts "
                                   f"({type(last).__name__})") from last
        if not self._schema_ready:
            try:
                with conn.cursor() as cur:
                    cur.execute(SCHEMA)
            except Exception:
                conn.close()
                raise
            self._schema_ready = True
        return conn

    def ensure_schema(self) -> None:
        conn = self._open()
        conn.close()

    @contextmanager
    def session(self):
        """One fresh connection for the whole cycle, always closed afterwards."""
        self.close()                           # never reuse a possibly-stale connection
        self._conn = self._open()
        try:
            yield self._conn
        finally:
            self.close()

    @contextmanager
    def _cursor(self, dict_rows: bool = False):
        from psycopg.rows import dict_row
        if self._conn is not None:             # inside a session
            with self._conn.cursor(row_factory=dict_row if dict_rows else None) as cur:
                yield cur
            return
        conn = self._open()                    # outside a session: short-lived connection
        try:
            with conn.cursor(row_factory=dict_row if dict_rows else None) as cur:
                yield cur
        finally:
            conn.close()

    def close(self) -> None:
        conn, self._conn = self._conn, None
        if conn is not None and not conn.closed:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass

    @contextmanager
    def lock(self):
        """Session-level advisory lock on the session's connection. Yields False
        if another cycle holds it. Outside a session, opens one for its duration."""
        if self._conn is None:
            with self.session():
                with self.lock() as acquired:
                    yield acquired
            return
        acquired = False
        try:
            with self._cursor() as cur:
                cur.execute("SELECT pg_try_advisory_lock(%s)", (ADVISORY_LOCK_KEY,))
                acquired = bool(cur.fetchone()[0])
            yield acquired
        finally:
            if acquired:
                try:
                    with self._cursor() as cur:
                        cur.execute("SELECT pg_advisory_unlock(%s)", (ADVISORY_LOCK_KEY,))
                except Exception as exc:  # noqa: BLE001 - lock dies with the session anyway
                    log.warning("advisory unlock failed: %s", exc)

    # ------------------------------------------------------------- run lock
    def claim_minute(self, minute: datetime) -> bool:
        with self._cursor() as cur:
            cur.execute("INSERT INTO zc_runs (minute) VALUES (%s) ON CONFLICT (minute) DO NOTHING "
                        "RETURNING id", (minute,))
            return cur.fetchone() is not None

    def finish_minute(self, minute: datetime, result: str, detail: str = "") -> None:
        with self._cursor() as cur:
            cur.execute("UPDATE zc_runs SET result = %s, detail = %s WHERE minute = %s",
                        (result, detail[:2000], minute))

    # ------------------------------------------------------------- kv state
    def set_state(self, key: str, value: str) -> None:
        with self._cursor() as cur:
            cur.execute("INSERT INTO zc_state (key, value) VALUES (%s, %s) "
                        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", (key, value))

    def get_state(self, key: str) -> str | None:
        with self._cursor() as cur:
            cur.execute("SELECT value FROM zc_state WHERE key = %s", (key,))
            row = cur.fetchone()
            return row[0] if row else None

    def holiday_cache_get(self) -> dict | None:
        raw = self.get_state("nse_holidays")
        return json.loads(raw) if raw else None

    def holiday_cache_set(self, blob: dict) -> None:
        self.set_state("nse_holidays", json.dumps(blob))

    # ------------------------------------------------------------- snapshots
    def save_snapshot_rows(self, rows: list[dict]) -> int:
        n = 0
        cols = ", ".join(SNAPSHOT_COLUMNS)
        ph = ", ".join(["%s"] * len(SNAPSHOT_COLUMNS))
        with self._cursor() as cur:
            for r in rows:
                cur.execute(f"INSERT INTO zc_option_snapshots ({cols}) VALUES ({ph}) "
                            "ON CONFLICT (minute, expiry, strike) DO NOTHING",
                            [r.get(c) for c in SNAPSHOT_COLUMNS])
                n += cur.rowcount
        return n

    def load_snapshots(self, since: datetime) -> pd.DataFrame:
        with self._cursor() as cur:
            cur.execute(f"SELECT {', '.join(SNAPSHOT_COLUMNS)} FROM zc_option_snapshots "
                        "WHERE minute >= %s ORDER BY minute, id", (since,))
            rows = cur.fetchall()
        if not rows:
            return pd.DataFrame(columns=["minute", "expiry", "strike", "spot", "ce_ltp", "pe_ltp",
                                         "ce_cum_volume", "pe_cum_volume"])
        df = pd.DataFrame(rows, columns=SNAPSHOT_COLUMNS)
        df["minute"] = pd.to_datetime(df["minute"], utc=True).dt.tz_convert(IST)
        return df

    def prune_snapshots(self, older_than_days: int = 10) -> None:
        cutoff = datetime.now(IST) - timedelta(days=older_than_days)
        with self._cursor() as cur:
            cur.execute("DELETE FROM zc_option_snapshots WHERE minute < %s", (cutoff,))

    # ------------------------------------------------------------- positions
    @staticmethod
    def _record(row: dict | None) -> PositionRecord | None:
        if row is None:
            return None
        rec = PositionRecord(**{k: row[k] for k in _POSITION_FIELDS})
        for k in ("entry_ts", "exit_due", "exit_ts"):
            setattr(rec, k, _aware(getattr(rec, k)))
        return rec

    def open_position_row(self) -> PositionRecord | None:
        with self._cursor(dict_rows=True) as cur:
            cur.execute("SELECT * FROM zc_positions WHERE status = 'open' ORDER BY id DESC LIMIT 1")
            return self._record(cur.fetchone())

    def insert_position(self, p: Position, direction: str) -> PositionRecord | None:
        """Returns None if the signal was already recorded or a position is open."""
        values = {
            "signal_id": p.signal_id, "status": "open", "strategy_state": "IN_POSITION",
            "direction": direction, "entry_ts": p.entry_ts, "expiry": p.expiry,
            "option_type": p.option_type, "sell_strike": p.sell_strike, "buy_strike": p.buy_strike,
            "lots": p.lots, "lot_size": p.lot_size, "units": p.units, "spot_at_entry": p.spot_at_entry,
            "sell_price": p.sell_price, "buy_price": p.buy_price, "entry_spread_price": p.net_credit,
            "net_credit": p.net_credit, "stop_loss": p.stop_loss, "target": p.target,
            "max_loss": p.max_loss, "max_profit": p.max_profit, "exit_due": p.exit_due,
            "alpha": p.alpha, "alpha2": p.alpha2, "entry_email_status": "pending",
            "allocated_capital": p.allocated_capital,
        }
        cols = ", ".join(values)
        ph = ", ".join(["%s"] * len(values))
        with self._cursor(dict_rows=True) as cur:
            # any unique violation (signal_id, or the single-open-position index) -> no row
            cur.execute(f"INSERT INTO zc_positions ({cols}) VALUES ({ph}) ON CONFLICT DO NOTHING "
                        "RETURNING *", list(values.values()))
            return self._record(cur.fetchone())

    def close_position(self, row_id: int, ev: ExitEvent) -> PositionRecord | None:
        with self._cursor(dict_rows=True) as cur:
            cur.execute(
                "UPDATE zc_positions SET status = 'closed', strategy_state = 'FLAT', exit_ts = %s, "
                "exit_value = %s, exit_reason = %s, pnl = %s, pnl_pct = %s, exit_email_status = 'pending' "
                "WHERE id = %s AND status = 'open' RETURNING *",
                (ev.exit_ts, ev.exit_value, ev.reason, ev.pnl, ev.pnl_pct, row_id))
            return self._record(cur.fetchone())

    def set_email_status(self, row_id: int, kind: str, status: str) -> None:
        if kind not in ("entry", "exit"):
            raise ValueError(kind)
        with self._cursor() as cur:
            cur.execute(f"UPDATE zc_positions SET {kind}_email_status = %s, "
                        f"{kind}_email_attempts = {kind}_email_attempts + 1 WHERE id = %s",
                        (status, row_id))

    def pending_emails(self, max_attempts: int = 5) -> list[tuple[str, PositionRecord]]:
        out = []
        with self._cursor(dict_rows=True) as cur:
            for kind in ("entry", "exit"):
                cur.execute(f"SELECT * FROM zc_positions WHERE {kind}_email_status IN ('pending', 'failed') "
                            f"AND {kind}_email_attempts < %s ORDER BY id", (max_attempts,))
                out += [(kind, self._record(r)) for r in cur.fetchall()]
        return out

    def closed_positions(self, limit: int = 50) -> list[PositionRecord]:
        with self._cursor(dict_rows=True) as cur:
            cur.execute("SELECT * FROM zc_positions WHERE status = 'closed' ORDER BY id DESC LIMIT %s",
                        (limit,))
            return [self._record(r) for r in cur.fetchall()]


def row_to_position(row: PositionRecord) -> Position:
    return Position(
        signal_id=row.signal_id, entry_ts=_aware(row.entry_ts), expiry=row.expiry,
        option_type=row.option_type, sell_strike=row.sell_strike, buy_strike=row.buy_strike,
        lots=row.lots, lot_size=row.lot_size, units=row.units, sell_price=row.sell_price,
        buy_price=row.buy_price, net_credit=row.net_credit, stop_loss=row.stop_loss, target=row.target,
        max_loss=row.max_loss, max_profit=row.max_profit, exit_due=_aware(row.exit_due),
        spot_at_entry=row.spot_at_entry, alpha=row.alpha, alpha2=row.alpha2,
        allocated_capital=row.allocated_capital)


def row_exit_ts(row: PositionRecord) -> datetime | None:
    return _aware(row.exit_ts)


def row_date(d) -> date:
    return d if isinstance(d, date) else pd.Timestamp(d).date()
