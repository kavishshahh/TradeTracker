"""Postgres store against a local throwaway database (never production)."""
from datetime import date

import pandas as pd

from execution.store import Store, normalize_dsn, row_to_position
from strategy.engine import ExitEvent, Position
from tests.conftest import ist


def _pos(sig="abc"):
    return Position(signal_id=sig, entry_ts=ist(2026, 9, 24, 10, 16), expiry=date(2026, 9, 29),
                    option_type="PE", sell_strike=23150, buy_strike=22750, lots=5, lot_size=65, units=325,
                    sell_price=110.0, buy_price=15.0, net_credit=95.0, stop_loss=140.0, target=10.0,
                    max_loss=98475.0, max_profit=30875.0, exit_due=ist(2026, 9, 25, 14, 53), spot_at_entry=23140.0)


def test_position_roundtrip_and_single_open(pg_dsn):
    db = Store(pg_dsn)
    row = db.insert_position(_pos(), "BULLISH")
    assert row is not None
    assert db.insert_position(_pos("other"), "BULLISH") is None            # one position at a time
    p = row_to_position(db.open_position_row())
    assert p.entry_ts == ist(2026, 9, 24, 10, 16) and p.exit_due == ist(2026, 9, 25, 14, 53)
    closed = db.close_position(row.id, ExitEvent("Target", ist(2026, 9, 25, 11, 0), 9.8, 27690.0, 8.65))
    assert closed.status == "closed" and closed.exit_email_status == "pending"
    assert db.close_position(row.id, ExitEvent("Target", ist(2026, 9, 25, 11, 1), 9.8, 1, 1)) is None
    assert db.insert_position(_pos("abc"), "BULLISH") is None               # same signal id never re-inserted


def test_minute_claim_is_idempotent(pg_dsn):
    db = Store(pg_dsn)
    m = ist(2026, 9, 24, 10, 16)
    assert db.claim_minute(m) is True
    assert db.claim_minute(m) is False
    assert db.claim_minute(ist(2026, 9, 24, 10, 17)) is True


def test_state_kv(pg_dsn):
    db = Store(pg_dsn)
    db.set_state("k", "1")
    db.set_state("k", "2")
    assert db.get_state("k") == "2" and db.get_state("missing") is None


def test_restart_survival(pg_dsn):
    a = Store(pg_dsn)
    row = a.insert_position(_pos("persist"), "BULLISH")
    a.claim_minute(ist(2026, 9, 24, 10, 16))
    a.set_email_status(row.id, "entry", "sent")
    a.holiday_cache_set({"fetched_at": 1.0, "payload": {"FO": []}})
    a.close()
    b = Store(pg_dsn)                                                       # fresh process / connection
    got = b.open_position_row()
    assert got.signal_id == "persist" and got.entry_email_status == "sent" and got.entry_email_attempts == 1
    assert b.claim_minute(ist(2026, 9, 24, 10, 16)) is False
    assert b.holiday_cache_get() == {"fetched_at": 1.0, "payload": {"FO": []}}
    assert b.pending_emails() == []


def test_snapshot_roundtrip_and_dedupe(pg_dsn):
    db = Store(pg_dsn)
    m = ist(2026, 9, 24, 10, 16)
    rows = [{"minute": m, "expiry": date(2026, 9, 29), "strike": 23150.0, "spot": 23140.5, "ce_ltp": 60.0,
             "pe_ltp": 70.0, "ce_bid": 59.5, "ce_ask": 60.5, "pe_bid": 69.5, "pe_ask": 70.5,
             "ce_cum_volume": 1000.0, "pe_cum_volume": 900.0}]
    assert db.save_snapshot_rows(rows) == 1
    assert db.save_snapshot_rows(rows) == 0
    df = db.load_snapshots(ist(2026, 9, 24))
    assert list(df.columns[:4]) == ["minute", "expiry", "strike", "spot"]
    assert df["minute"].iloc[0] == pd.Timestamp(m) and df["expiry"].iloc[0] == date(2026, 9, 29)


def test_dsn_normalisation():
    assert normalize_dsn("postgres://u:p@h/db?sslmode=require") == "postgresql://u:p@h/db?sslmode=require"
    assert normalize_dsn("postgresql+psycopg://u:p@h/db") == "postgresql://u:p@h/db"


def test_additive_allocation_migration_preserves_legacy_position(pg_dsn):
    import psycopg
    db = Store(pg_dsn)
    row = db.insert_position(_pos("legacy"), "BULLISH")
    with psycopg.connect(pg_dsn, autocommit=True) as conn:
        conn.execute("ALTER TABLE zc_positions DROP COLUMN allocated_capital")
    db.close()
    upgraded = Store(pg_dsn)
    restored = upgraded.open_position_row()   # creates the new column without losing the row
    assert restored.id == row.id and restored.signal_id == "legacy"
    assert row_to_position(restored).allocated_capital is None
