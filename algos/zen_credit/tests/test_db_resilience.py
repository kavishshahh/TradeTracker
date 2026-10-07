"""Neon autosuspend resilience: per-cycle connections, connect retries, 503 when down."""
import psycopg
import pytest

import main
from app import create_app
from execution.store import Store, StoreUnavailable
from tests.conftest import FakeSMTP, ist
from tests.test_service import ExplodingProvider, EXPS, force_indicators, make_config, make_runner
from main import Runner
from notifications.email import EmailNotifier

UNREACHABLE = "postgresql://postgres:x@127.0.0.1:1/nodb?connect_timeout=1"


def _terminate_all(dsn):
    admin = dsn.rsplit("/", 1)[0] + "/postgres"
    name = dsn.rsplit("/", 1)[1]
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                  "WHERE datname = %s AND pid <> pg_backend_pid()", (name,))


def test_no_connection_is_kept_between_cycles(pg_dsn, calendar):
    r, p = make_runner(pg_dsn, calendar)
    force_indicators(r, 0.5, 0.5)
    p.now = ist(2026, 9, 24, 10, 30)
    assert r.locked_cycle(p.now)["status"] == "no_action"
    assert r.store._conn is None                                     # closed at the end of the cycle


def test_terminated_connection_before_cycle_uses_fresh_connection(pg_dsn, calendar):
    r, p = make_runner(pg_dsn, calendar)
    force_indicators(r, 0.5, 0.5)
    p.now = ist(2026, 9, 24, 10, 30)
    assert r.locked_cycle(p.now)["status"] == "no_action"
    # a stale long-lived connection left behind, then Neon-style termination of every session
    r.store._conn = psycopg.connect(pg_dsn, autocommit=True)
    _terminate_all(pg_dsn)
    force_indicators(r, 0.95, 0.95)
    p.now = ist(2026, 9, 24, 10, 31)
    res = r.locked_cycle(p.now)
    assert res["status"] == "entry"                                  # succeeded on a fresh connection
    assert len(FakeSMTP.sent) == 1 and r.store._conn is None


def test_connect_retried_while_neon_wakes(pg_dsn, calendar, monkeypatch):
    r, p = make_runner(pg_dsn, calendar)
    r.store._sleep = lambda s: None
    real, calls = psycopg.connect, {"n": 0}

    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise psycopg.errors.AdminShutdown("terminating connection due to administrator command")
        return real(*a, **k)
    monkeypatch.setattr(psycopg, "connect", flaky)
    force_indicators(r, 0.5, 0.5)
    p.now = ist(2026, 9, 24, 10, 30)
    assert r.locked_cycle(p.now)["status"] == "no_action" and calls["n"] >= 3


def _unreachable_runner(calendar):
    cfg = make_config(UNREACHABLE)
    store = Store(UNREACHABLE, connect_timeout=1, sleep=lambda s: None)
    prov = ExplodingProvider(EXPS)                                   # any data fetch would fail the test
    return Runner(cfg, store, prov, calendar, EmailNotifier(cfg.email, smtp_factory=FakeSMTP)), prov


def test_db_unreachable_returns_db_unavailable_no_email(calendar, monkeypatch):
    r, _ = _unreachable_runner(calendar)
    attempts = {"n": 0}
    real = psycopg.connect

    def counting(*a, **k):
        attempts["n"] += 1
        return real(*a, **k)
    monkeypatch.setattr(psycopg, "connect", counting)
    res = r.locked_cycle(ist(2026, 9, 24, 10, 30))
    assert res["status"] == "db_unavailable" and "3 connect attempts" in res["reason"]
    assert attempts["n"] == 3 and FakeSMTP.sent == []
    with pytest.raises(StoreUnavailable):
        r.store.get_state("last_evaluation")                         # nothing was (or could be) written


def test_db_unreachable_http_503_small_json(calendar):
    r, _ = _unreachable_runner(calendar)
    c = create_app(lambda: r, cron_token="t0k").test_client()
    resp = c.post("/run-cycle", headers={"X-Cron-Token": "t0k"})
    j = resp.get_json()
    assert resp.status_code == 503 and len(resp.get_data()) < 1024
    assert j["status"] == "db_unavailable" and j["action"] == "none" and j["session"] is None
    assert "x@" not in resp.get_data(as_text=True)                   # no credentials in the response
    assert FakeSMTP.sent == []
    assert c.get("/health").status_code == 200                       # liveness unaffected


def test_connection_lost_mid_cycle_is_not_retried(pg_dsn, calendar):
    r, p = make_runner(pg_dsn, calendar)
    force_indicators(r, 0.5, 0.5)
    p.now = ist(2026, 9, 24, 10, 30)
    orig = r._evaluate

    def dying(now, minute):
        _terminate_all(pg_dsn)                                       # connection dies after state was written
        return orig(now, minute)
    r._evaluate = dying
    res = r.locked_cycle(p.now)
    assert res["status"] == "db_unavailable" and "not retried" in res["reason"]
    # the minute was claimed before the failure, so a retry in the same minute is a no-op
    r._evaluate = orig
    assert r.locked_cycle(p.now)["status"] == "duplicate"
    assert FakeSMTP.sent == []
