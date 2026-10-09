"""Strategy runner. One cycle = session check -> data -> evaluate -> persist -> email.

Deployment is a Render web service (`app.py`) whose ``POST /run-cycle`` calls
``Runner.cycle()``. This module is also runnable directly for local work:

    python main.py --once          one cycle, then exit (prints the JSON result)
    python main.py --once --force  ignore the session gate (testing only)
    python main.py --health        print health JSON and exit
    python main.py --test-email    send one test email and exit
    python main.py --check-db      verify existing Firestore access

paper_worker.py provides the continuous minute loop; app.py remains an optional manual HTTP adapter.

Email policy: an ENTRY or an EXIT sends mail. Nothing else does: no-trade cycles,
holidays, stale data and errors are logged and returned in the cycle's JSON.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import threading
from dataclasses import replace
from datetime import datetime, timedelta

from config import CONFIG, Config
from data.market_calendar import BundledNSECalendar, CalendarUnavailable, MarketCalendar, TradingCalendar
from data.providers.base import MarketDataError, MarketDataProvider
from data.providers.http import HttpClient
from data.providers.nse import NSEMarketDataProvider
from data.providers.yahoo import YahooSpotSource
from execution.store import PositionRecord, Store, StoreUnavailable, is_db_error, row_to_position
from notifications.email import EmailNotifier
from strategy.alpha2 import nearest_strike
from strategy.engine import MarketView, StrategyEngine
from strategy.registry import apply_profile, create_engine
from strategy.spreads import select_expiry
from utils.time import minute_bucket, now_ist, to_ist

log = logging.getLogger("paper.runner")

SNAPSHOT_STRIKES_EACH_SIDE = 15
SNAPSHOT_HISTORY_DAYS = 6
HTTP_OK_STATUSES = {"entry", "exit", "no_action", "duplicate", "duplicate_signal", "market_closed"}
MAX_RESPONSE_BYTES = 2048
MAX_REASON_CHARS = 200


def summarize_cycle(result: dict, context: dict | None = None) -> dict:
    """Compact, bounded /run-cycle response (cron-job.org caps response size).

    Whitelisted scalar fields only; bulk data (chain, snapshots, series) is never
    included and is logged server-side instead. Always well under MAX_RESPONSE_BYTES.
    """
    ctx = context or {}
    status = str(result.get("status", "unknown"))
    action = status if status in ("entry", "exit") else "none"
    reason = result.get("reason") or result.get("detail")
    position = ctx.get("position")
    if action == "entry":
        position = "IN_POSITION"
    elif action == "exit":
        position = "FLAT"

    def num(v):
        try:
            return None if v is None else round(float(v), 4)
        except (TypeError, ValueError):
            return None

    out = {"status": status, "session": result.get("session", "OPEN" if status not in
                                                      ("market_closed", "calendar_unavailable", "busy",
                                                       "db_unavailable") else None),
           "minute": result.get("minute") or ctx.get("minute"), "alpha": num(ctx.get("alpha")), "alpha2": num(ctx.get("alpha2")),
           "signal": ctx.get("signal"), "position": position, "action": action,
           "reason": redact(str(reason))[:MAX_REASON_CHARS] if reason else None}
    strategy = result.get("strategy") or ctx.get("strategy")
    if strategy:
        out["strategy"] = str(strategy)[:64]
    if result.get("signal_id"):
        out["signal_id"] = str(result["signal_id"])[:40]
    if len(json.dumps(out)) > MAX_RESPONSE_BYTES:      # defensive; cannot happen with the caps above
        out["reason"] = None
    return out


# --------------------------------------------------------------------------- logging
_SECRET_ENV = ("SMTP_PASSWORD", "CRON_TOKEN", "API_SECRET", "SMTP_USERNAME", "DATABASE_URL", "DHAN_ACCESS_TOKEN", "DHAN_CLIENT_ID", "FIREBASE_SERVICE_ACCOUNT_JSON")
_RESERVED = set(vars(logging.makeLogRecord({})).keys()) | {"message", "asctime"}
_PATTERNS = [re.compile(r"(password|passwd|secret|token|authorization|cookie)(\s*[=:]\s*)([^\s,;&]+)", re.I),
             re.compile(r"(postgres(?:ql)?://)[^\s@/]+@", re.I)]


def redact(text: str) -> str:
    out = str(text)
    for name in _SECRET_ENV:
        val = os.getenv(name)
        if val and len(val) >= 4:
            out = out.replace(val, "***")
    out = _PATTERNS[0].sub(lambda m: f"{m.group(1)}{m.group(2)}***", out)
    out = _PATTERNS[1].sub(lambda m: f"{m.group(1)}***@", out)
    return out


class RedactingFormatter(logging.Formatter):
    """Plain-text format shared with the other Dhan projects; structured fields
    passed via ``extra=`` are appended as key=value; secrets are masked."""

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        extras = {k: v for k, v in record.__dict__.items() if k not in _RESERVED}
        if extras:
            base += " " + " ".join(f"{k}={v}" for k, v in extras.items())
        return redact(base)


def configure_paper_logging() -> None:
    """Expose paper INFO events even when hosted under Uvicorn's logging."""
    logger = logging.getLogger("paper")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(RedactingFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)


def setup_logging(cfg: Config) -> None:
    configure_paper_logging()
    fmt = RedactingFormatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(getattr(logging, cfg.runtime.log_level.upper(), logging.INFO))
    root.handlers.clear()
    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(fmt)
    root.addHandler(stream)
    try:
        cfg.runtime.log_dir.mkdir(parents=True, exist_ok=True)
        fileh = logging.FileHandler(cfg.runtime.log_dir / "runner.log", encoding="utf-8")
        fileh.setFormatter(fmt)
        root.addHandler(fileh)
    except OSError:
        # Read-only or ephemeral filesystem (Render): stdout is enough, Render captures it.
        pass
    logging.getLogger("urllib3").setLevel("WARNING")


# --------------------------------------------------------------------------- runner
class Runner:
    def __init__(self, cfg: Config, store: Store, provider: MarketDataProvider,
                 calendar: TradingCalendar, notifier: EmailNotifier):
        cfg = replace(cfg, strategy=apply_profile(cfg.runtime.strategy_name, cfg.strategy))
        self.cfg, self.store, self.provider, self.calendar, self.notifier = cfg, store, provider, calendar, notifier
        self.session = MarketCalendar(calendar)
        self.engine = create_engine(cfg.runtime.strategy_name, cfg.strategy, calendar,
                                    entry_price_source=cfg.data.entry_price_source,
                                    max_data_age_seconds=cfg.data.max_data_age_seconds, require_quotes=True)
        self.strategy_name = getattr(self.engine, "strategy_name", cfg.runtime.strategy_name)
        self.cycles = 0
        self.last_context: dict = {}
        self._lock = threading.Lock()

    @classmethod
    def from_config(cls, cfg: Config = CONFIG, provider=None) -> "Runner":
        cfg = replace(cfg, strategy=apply_profile(cfg.runtime.strategy_name, cfg.strategy))
        http = HttpClient(cfg.data.request_timeout, cfg.data.max_retries, nse_base_url=cfg.data.nse_base_url)
        from execution.firestore_store import FirestoreStore
        store = FirestoreStore(cfg.runtime.strategy_name)
        if provider is None:
            if cfg.data.provider == "dhan":
                from data.providers.dhan import DhanLiveProvider
                provider = DhanLiveProvider()
            elif cfg.data.provider == "nse":  # isolated legacy fixtures
                provider = NSEMarketDataProvider(http, YahooSpotSource(http, cfg.data.yahoo_chart_url),
                                                 cfg.data.nse_base_url, cfg.data.nse_lot_size_url,
                                                 cfg.strategy.underlying)
            else:
                raise RuntimeError(f"unsupported DATA_PROVIDER={cfg.data.provider}")
        calendar = BundledNSECalendar()
        return cls(cfg, store, provider, calendar, EmailNotifier(cfg.email))

    # ------------------------------------------------------------------ emails
    def _send(self, kind: str, row: PositionRecord) -> None:
        res = self.notifier.send_entry(row) if kind == "entry" else self.notifier.send_exit(row)
        self.store.set_email_status(row.id, kind, "sent" if res.ok else "failed")

    def _flush_pending_emails(self) -> None:
        for kind, row in self.store.pending_emails(self.cfg.email.max_attempts):
            self._send(kind, row)

    # ------------------------------------------------------------------ cycle
    def cycle(self, now: datetime | None = None, force: bool = False) -> dict:
        """One evaluation. Always returns a JSON-serialisable summary."""
        now = to_ist(now) if now else now_ist()
        minute = minute_bucket(now)
        self.cycles += 1
        self.last_context = {"minute": minute.isoformat(), "strategy": self.strategy_name}
        # Each strategy has its own Firestore namespace and minute ledger.
        bound_strategy = self.store.get_state("selected_strategy")
        if bound_strategy and bound_strategy != self.strategy_name:
            return {"status": "strategy_state_mismatch", "strategy": self.strategy_name,
                    "reason": "Firestore namespace belongs to another strategy"}
        if bound_strategy is None:
            if self.strategy_name != "description" and self.store.open_position_row() is not None:
                return {"status": "strategy_state_mismatch", "strategy": self.strategy_name,
                        "reason": "Unlabelled open position exists; review this strategy namespace"}
            self.store.set_state("selected_strategy", self.strategy_name)
        self.store.set_state("last_evaluation", now.isoformat())
        # ---- session gate: before any market-data request ----
        try:
            verdict = self.session.check(now)
        except CalendarUnavailable as exc:
            log.error("calendar_unavailable: %s", exc, extra={"error": str(exc)})
            return {"status": "calendar_unavailable"}
        if not verdict.is_open and not force:
            log.info("skipped: %s", verdict.reason)
            return {"status": "market_closed", "session": verdict.state.value, "reason": verdict.reason}
        if not self.store.claim_minute(minute):
            log.info("duplicate_run_ignored", extra={"minute": minute.isoformat()})
            return {"status": "duplicate", "minute": minute.isoformat()}
        try:
            result = self._evaluate(now, minute)
        except (MarketDataError, CalendarUnavailable) as exc:
            log.error("run_data_error [%s]: %s", self.strategy_name, exc,
                      extra={"error": str(exc)})
            result = {"status": "data_error", "detail": str(exc)}
        except Exception as exc:  # never crash the endpoint
            log.exception("run_failed")
            result = {"status": "error", "detail": type(exc).__name__}
        self.store.finish_minute(minute, result.get("status", "?"), str(result.get("detail", "")))
        return result

    def locked_cycle(self, now: datetime | None = None, force: bool = False) -> dict:
        """Evaluate under a local mutex and a persistent, fenced Firestore lease.

        Storage failures return db_unavailable. A partially completed cycle is
        never rerun automatically: minute claims and transactionally committed
        positions survive a restart; an expired worker cannot commit new writes.
        """
        if not self._lock.acquire(blocking=False):
            return {"status": "busy", "strategy": self.strategy_name, "reason": "another cycle is running"}
        try:
            with self.store.session():
                with self.store.lock() as acquired:
                    if not acquired:
                        log.warning("paper_strategy_busy strategy=%s reason=lease_not_acquired", self.strategy_name)
                        return {"status": "busy", "strategy": self.strategy_name, "reason": "another cycle is running"}
                    result = self.cycle(now, force)
                    # Optional dashboard mirror; durable paper state precedes export.
                    try:
                        from execution.firebase_paper import publish_paper_snapshot
                        publish_paper_snapshot(self, result)
                    except Exception as exc:
                        log.warning("paper_dashboard_export_failed strategy=%s minute=%s error=%s",
                                    self.strategy_name, self.last_context.get('minute'), type(exc).__name__)
                    return result
        except Exception as exc:
            if not is_db_error(exc):
                raise
            reason = (str(exc) if isinstance(exc, StoreUnavailable)
                      else f"database connection lost during cycle ({type(exc).__name__}); not retried")
            log.error("database_unavailable", extra={"error": reason})
            return {"status": "db_unavailable", "strategy": self.strategy_name, "reason": reason}
        finally:
            self._lock.release()

    def _evaluate(self, now: datetime, minute: datetime) -> dict:
        open_row = self.store.open_position_row()
        position = row_to_position(open_row) if open_row else None
        chains = {}
        expiries = None
        if position is not None:
            log.info("paper_data_start strategy=%s minute=%s stage=held_position expiry=%s",
                     self.strategy_name, minute.isoformat(), position.expiry)
            # Evaluate the existing contract before fetching any entry-only inputs.
            settlement = None
            chain = None
            if position.expiry < now.date():
                settlement = self.provider.get_expiry_settlement(position.expiry)
            else:
                chain = self.provider.get_option_chain(position.expiry)
                chains[position.expiry] = chain
            view = MarketView(now=now, spot_bars=None, snapshots=None, chain=chain,
                              expiries=[], lot_size=None, position_chain=chain, settlement=settlement)
        else:
            log.info("paper_data_start strategy=%s minute=%s stage=instrument_master", self.strategy_name, minute.isoformat())
            expiries = self.provider.get_expiries()
            nearest = select_expiry(now.date(), expiries)
            log.info("paper_data_start strategy=%s minute=%s stage=option_quotes expiry=%s", self.strategy_name, minute.isoformat(), nearest)
            chain = self.provider.get_option_chain(nearest)
            chains[nearest] = chain
            self._collect_history(now, minute, chains, expiries)
            lot_size = self.provider.get_lot_size(nearest)
            log.info("paper_data_start strategy=%s minute=%s stage=index_candles", self.strategy_name, minute.isoformat())
            bars = self.provider.get_spot_bars(now)
            log.info("paper_data_start strategy=%s minute=%s stage=snapshot_history", self.strategy_name, minute.isoformat())
            snapshots = self.store.load_snapshots(now - timedelta(days=SNAPSHOT_HISTORY_DAYS))
            if not snapshots.empty:
                snapshots = snapshots[snapshots["minute"] <= minute]
                if self.strategy_name == "description":
                    snapshots = snapshots[snapshots["expiry"] == nearest]
            view = MarketView(now=now, spot_bars=bars, snapshots=snapshots, chain=chain,
                              expiries=expiries, lot_size=lot_size)
        res = self.engine.evaluate(view, position)
        # compact context for the HTTP summary (read-only copy of values already computed)
        d = res.diagnostics
        self.last_context.update(alpha=d.get("alpha"), alpha2=d.get("alpha2"), signal=d.get("signal"),
                                 position="IN_POSITION" if position is not None else "FLAT")
        log.info("paper_evaluation strategy=%s minute=%s action=%s reason=%s", self.strategy_name,
                 minute.isoformat(), res.action, res.reason,
                 extra={"action": res.action, "reason": res.reason,
                                      "spot": chain.spot if chain else None,
                                      "expiry": chain.expiry.isoformat() if chain else None,
                                      "position_open": position is not None,
                                      **{k: v for k, v in res.diagnostics.items()}})
        if res.action == "exit" and open_row is not None:
            closed = self.store.close_position(open_row.id, res.exit)
            if closed is not None:
                log.info("exit_signal", extra={"reason": res.exit.reason, "exit_value": res.exit.exit_value,
                                               "pnl": res.exit.pnl, "signal_id": closed.signal_id})
            result = {"status": "exit", "reason": res.exit.reason}
        elif res.action == "entry":
            row = self.store.insert_position(res.position, res.reason)
            if row is None:
                return {"status": "duplicate_signal"}
            self.store.set_state("last_signal_time", now.isoformat())
            log.info("entry_signal", extra={"signal_id": row.signal_id, "direction": res.reason,
                                            "sell_strike": row.sell_strike, "buy_strike": row.buy_strike,
                                            "option_type": row.option_type, "net_credit": row.net_credit,
                                            "stop_loss": row.stop_loss, "lots": row.lots})
            result = {"status": "entry", "signal_id": row.signal_id}
        else:
            result = {"status": "no_action", "detail": res.reason}
        # History collection and SMTP cannot prevent the exit decision/persistence.
        if position is not None:
            self._collect_history(now, minute, chains, expiries)
        try:
            self._flush_pending_emails()
        except Exception:
            log.exception("pending_email_flush_failed")
        return result

    def _save_chain_history(self, chain, minute: datetime, now: datetime) -> None:
        if (self.engine._stale(chain.timestamp, now) or chain.expiry < now.date()
                or not chain.strikes):
            return
        atm = nearest_strike(chain.spot, chain.strikes)
        ks = sorted(chain.strikes, key=lambda k: abs(k - atm))[:2 * SNAPSHOT_STRIKES_EACH_SIDE + 1]
        # Preserve both held legs for marked P&L even after a large index move.
        held = self.store.open_position_row()
        if held is not None and str(held.expiry) == chain.expiry.isoformat():
            ks = sorted(set(ks) | {float(held.sell_strike), float(held.buy_strike)})
        self.store.save_snapshot_rows(chain.to_rows(minute, ks))

    def _collect_history(self, now: datetime, minute: datetime, chains: dict,
                         expiries=None) -> None:
        """Collect the nearest TWO expiries so rollover retains an already warmed series.

        Each expiry is stored separately. Secondary data is best effort; entry
        still requires the primary chain, and exit requires only its own contract.
        """
        try:
            listed = expiries if expiries is not None else self.provider.get_expiries()
            upcoming = sorted(set(e for e in listed if e >= now.date()))[:2]
        except Exception as exc:
            if is_db_error(exc):
                raise
            log.warning("history_expiry_lookup_failed: %s", type(exc).__name__)
            return
        for expiry in upcoming:
            try:
                chain = chains.get(expiry)
                if chain is None:
                    chain = self.provider.get_option_chain(expiry)
                    chains[expiry] = chain
                self._save_chain_history(chain, minute, now)
            except Exception as exc:
                if is_db_error(exc):
                    raise
                log.warning("history_collection_failed for %s: %s", expiry, type(exc).__name__)

    # ------------------------------------------------------------------ status
    def status(self) -> dict:
        row = self.store.open_position_row()
        now = now_ist()
        try:
            session = self.session.check(now).state.value
        except CalendarUnavailable:
            session = "UNKNOWN"
        pos = None
        if row is not None:
            pos = {"direction": row.direction, "option_type": row.option_type, "expiry": str(row.expiry),
                   "sell_strike": row.sell_strike, "buy_strike": row.buy_strike, "lots": row.lots,
                   "net_credit": row.net_credit, "stop_loss": row.stop_loss, "target": row.target,
                   "entry_ts": str(row.entry_ts), "exit_due": str(row.exit_due)}
        return {"strategy": self.strategy_name, "market_session": session, "position": pos,
                "strategy_state": "IN_POSITION" if row else "FLAT",
                "last_evaluation": self.store.get_state("last_evaluation"),
                "last_signal_time": self.store.get_state("last_signal_time")}

    def health(self) -> dict:
        cal = self.calendar
        return {"strategy": self.strategy_name, "cycles": self.cycles, "state_backend": type(self.store).__name__,
                "holidays_known": getattr(cal, "holidays_known", None),
                "next_holidays": [d.isoformat() for d in getattr(cal, "next_holidays", lambda: [])()],
                "emails_sent": self.notifier.sent, "email_failures": self.notifier.failures}


# --------------------------------------------------------------------------- CLI helpers
def _redact_addr(addr: str | None) -> str:
    if not addr:
        return "(MISSING)"
    local, _, domain = addr.partition("@")
    return f"{local[:2]}***@{domain}" if domain else local[:2] + "***"


def send_test_email(cfg: Config) -> int:
    print("SMTP configuration")
    print(f"  host     : {cfg.email.host or '(MISSING)'}")
    print(f"  port     : {cfg.email.port}")
    print(f"  username : {_redact_addr(cfg.email.username)}")
    print(f"  password : {'set' if cfg.email.password else '(MISSING)'}")
    print(f"  from     : {_redact_addr(cfg.email.sender)}")
    print(f"  to       : {', '.join(_redact_addr(a) for a in cfg.email.recipient_list) or '(MISSING)'}")
    res = EmailNotifier(cfg.email)._send("SMTP test", "SMTP is working. ENTRY and EXIT alerts will arrive here.")
    print("SENT" if res.ok else f"FAILED: {res.detail}")
    return 0 if res.ok else 1


def check_db(cfg: Config) -> int:
    if not cfg.data.database_url:
        print("DATABASE_URL is not set. Set it to your Neon connection string (?sslmode=require).")
        return 1
    try:
        from execution.firestore_store import FirestoreStore
        store = FirestoreStore(cfg.runtime.strategy_name)
        store.ensure_schema()
        print("  Firestore access : OK")
        with store.lock() as acquired:
            print(f"  strategy lease   : {'OK' if acquired else 'HELD ELSEWHERE'}")
        store.set_state("__checkdb__", now_ist().isoformat())
        print(f"  write/read state : {'OK' if store.get_state('__checkdb__') else 'FAILED'}")
        store.close()
        print("Firestore is ready.")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED: {type(exc).__name__}: {redact(exc)}")
        print("Check the TradeBud server-side Firebase credentials and Firestore access.")
        return 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--once", action="store_true", help="one cycle, then exit")
    ap.add_argument("--force", action="store_true", help="ignore the session gate (testing only)")
    ap.add_argument("--health", action="store_true", help="print health JSON and exit")
    ap.add_argument("--test-email", action="store_true", help="send one test email and exit")
    ap.add_argument("--check-db", action="store_true", help="verify DATABASE_URL and exit")
    args = ap.parse_args()
    cfg = CONFIG
    setup_logging(cfg)
    if args.test_email:
        return send_test_email(cfg)
    if args.check_db:
        return check_db(cfg)
    runner = Runner.from_config(cfg)
    if args.health:
        print(json.dumps(runner.health(), indent=2, default=str))
        return 0
    if args.once:
        print(json.dumps(runner.locked_cycle(force=args.force), indent=2, default=str))
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
