"""Shared fixtures.

Tests never touch the production database: DATABASE_URL is blocked with an empty
environment value for the whole session, and every database test gets its own freshly
created database on a throwaway local PostgreSQL server (pgserver, test-only
dependency) listening on 127.0.0.1. ``pg_dsn`` refuses any non-local host.

Run: python -m pytest tests/        (from the zen_credit/ directory)
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import uuid
from datetime import date, datetime, time, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Empty existing values also prevent load_dotenv(override=False) from restoring
# production credentials from either local .env file during config imports.
os.environ["DATABASE_URL"] = ""
os.environ["CRON_TOKEN"] = ""

import logging                                                                # noqa: E402
logging.raiseExceptions = False   # pgserver logs at interpreter exit after pytest closed stdout

import numpy as np                                                            # noqa: E402
import pandas as pd                                                           # noqa: E402
import pytest                                                                 # noqa: E402

from data.market_calendar import HolidaySetCalendar                           # noqa: E402
from config import StrategyConfig                                             # noqa: E402
from data.providers.base import MarketDataProvider, OptionChainSnapshot, OptionQuote  # noqa: E402
from utils.time import IST                                                    # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str):
    p = FIXTURES / name
    return json.loads(p.read_text()) if p.suffix == ".json" else p.read_text()


def ist(y, m, d, hh=0, mm=0, ss=0) -> datetime:
    return datetime(y, m, d, hh, mm, ss, tzinfo=IST)


def session_bars(days: list[date], start_price: float = 23000.0, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = []
    for d in days:
        t0 = pd.Timestamp(datetime.combine(d, time(9, 15)), tz=IST)
        idx += list(pd.date_range(t0, periods=375, freq="1min"))
    idx = pd.DatetimeIndex(idx)
    close = start_price * np.exp(np.cumsum(rng.normal(0, 0.0004, len(idx))))
    open_ = np.concatenate([[start_price], close[:-1]])
    return pd.DataFrame({"open": open_, "high": np.maximum(open_, close) + 1,
                         "low": np.minimum(open_, close) - 1, "close": close}, index=idx)


def make_chain(ts: datetime, expiry: date, spot: float, interval: float = 50.0, n: int = 30,
               vol_scale: float = 1.0) -> OptionChainSnapshot:
    snap = OptionChainSnapshot("NIFTY", expiry, ts, spot)
    k0 = round(spot / interval) * interval
    for i in range(-n, n + 1):
        k = float(k0 + i * interval)
        ce = max(spot - k, 0) + 60 * np.exp(-abs(spot - k) / 400)
        pe = max(k - spot, 0) + 60 * np.exp(-abs(spot - k) / 400)
        snap.quotes[(k, "CE")] = OptionQuote(k, "CE", round(ce, 2), round(ce - 0.5, 2), round(ce + 0.5, 2), 1000 * vol_scale)
        snap.quotes[(k, "PE")] = OptionQuote(k, "PE", round(pe, 2), round(pe - 0.5, 2), round(pe + 0.5, 2), 1000 * vol_scale)
    return snap


class FakeProvider(MarketDataProvider):
    def __init__(self, expiries, spot=23140.0, lot=65, fail=False):
        self.expiries, self.spot, self.lot, self.fail = expiries, spot, lot, fail
        self.now = None
        self.chain_ts_offset = timedelta(0)

    def get_spot_bars(self, as_of):
        days = [as_of.date() - timedelta(days=k) for k in (3, 2, 1, 0)]
        b = session_bars([d for d in days if d.weekday() < 5])
        return b[b.index <= pd.Timestamp(as_of) - pd.Timedelta(minutes=1)]

    def get_expiries(self):
        return list(self.expiries)

    def get_option_chain(self, expiry):
        if self.fail:
            from data.providers.base import MarketDataError
            raise MarketDataError("down")
        return make_chain(self.now + self.chain_ts_offset, expiry, self.spot)

    def get_lot_size(self, expiry):
        return self.lot


class FakeSMTP:
    sent: list = []

    def __init__(self, host, port):
        self.host, self.port = host, port

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self, context=None):
        pass

    def login(self, u, p):
        pass

    def send_message(self, msg):
        FakeSMTP.sent.append(msg)


@pytest.fixture
def cfg() -> StrategyConfig:
    return StrategyConfig()


@pytest.fixture
def calendar():
    return HolidaySetCalendar({date(2026, 10, 2), date(2026, 10, 20)})


@pytest.fixture(autouse=True)
def _reset_smtp():
    FakeSMTP.sent = []
    yield


# --------------------------------------------------------------------------- Postgres
@pytest.fixture(scope="session")
def pg_server():
    pgserver = pytest.importorskip("pgserver", reason="pip install -r requirements-dev.txt")
    srv = pgserver.get_server(tempfile.mkdtemp(prefix="zc_pg_"), cleanup_mode="stop")
    yield srv
    srv.cleanup()


@pytest.fixture
def pg_dsn(pg_server):
    """A brand-new empty database for this test, dropped afterwards."""
    import psycopg
    base = pg_server.get_uri()
    assert "@127.0.0.1:" in base or "@localhost:" in base, "tests must only use a local Postgres"
    name = "zc_test_" + uuid.uuid4().hex[:12]
    with psycopg.connect(base, autocommit=True) as c:
        c.execute(f"CREATE DATABASE {name}")
    dsn = base.rsplit("/", 1)[0] + "/" + name
    yield dsn
    with psycopg.connect(base, autocommit=True) as c:
        c.execute(f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{name}'")
        c.execute(f"DROP DATABASE IF EXISTS {name}")


@pytest.fixture(autouse=True)
def block_production_firestore(monkeypatch):
    """Unit tests must inject storage; never read credentials from TradeBud."""
    import execution.firebase_client as firebase_client
    def blocked():
        raise AssertionError('Production Firestore access is blocked in unit tests')
    monkeypatch.setattr(firebase_client, 'get_firestore_client', blocked)
