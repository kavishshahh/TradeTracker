"""Flask endpoints: /health, /status, /run-cycle (and the /run alias)."""
import main
from app import create_app
from tests.conftest import FakeSMTP, ist
from tests.test_service import force_indicators, make_runner


def _client(pg_dsn, calendar, token=""):
    r, p = make_runner(pg_dsn, calendar, token=token)
    return create_app(lambda: r, cron_token=token).test_client(), r, p


def test_health(pg_dsn, calendar):
    c, _, _ = _client(pg_dsn, calendar)
    body = c.get("/health").get_json()
    assert body["status"] == "ok" and body["service"] == "zen-credit"
    assert body["state_backend"] == "Store"
    assert body["strategy"] == "description"


def test_status_has_no_secrets(pg_dsn, calendar):
    c, _, _ = _client(pg_dsn, calendar)
    resp = c.get("/status")
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200 and "market_session" in body
    assert "pw-secret" not in body and "smtp" not in body.lower() and "postgresql://" not in body


def test_run_requires_bearer_secret(pg_dsn, calendar):
    c, r, _ = _client(pg_dsn, calendar, token="cron-123")
    r.locked_cycle = lambda now=None, force=False: {"status": "market_closed", "session": "WEEKEND"}
    assert c.post("/run-cycle").status_code == 401
    assert c.post("/run-cycle", headers={"X-Cron-Token": "wrong"}).status_code == 401
    assert c.post("/run-cycle", headers={"X-Cron-Token": "cron-123"}).status_code == 200
    assert c.post("/run-cycle?token=cron-123").status_code == 200
    ok = c.post("/run", headers={"Authorization": "Bearer cron-123"})
    assert ok.status_code == 200 and ok.get_json()["status"] == "market_closed"


def test_run_without_secret_configured(pg_dsn, calendar):
    # fails closed: an unset CRON_TOKEN refuses every run request
    c, _, _ = _client(pg_dsn, calendar, token="")
    assert c.post("/run-cycle").status_code == 401
    assert c.post("/run").status_code == 401
    assert c.get("/run-cycle").status_code == 405


def test_duplicate_run_cycle_is_idempotent_over_http(pg_dsn, calendar, monkeypatch):
    c, r, p = _client(pg_dsn, calendar, token="t0k")
    force_indicators(r, 0.95, 0.95)
    t = ist(2026, 9, 24, 10, 16, 5)
    p.now = t
    monkeypatch.setattr(main, "now_ist", lambda: t)
    h = {"X-Cron-Token": "t0k"}
    first = c.post("/run-cycle", headers=h)
    second = c.post("/run-cycle", headers=h)
    assert first.get_json()["status"] == "entry" and second.get_json()["status"] == "duplicate"
    assert first.status_code == second.status_code == 200
    assert len(FakeSMTP.sent) == 1


def test_run_cycle_busy_returns_409(pg_dsn, calendar):
    from execution.store import Store
    c, _, _ = _client(pg_dsn, calendar, token="t0k")
    with Store(pg_dsn).lock() as held:
        assert held
        resp = c.post("/run-cycle", headers={"X-Cron-Token": "t0k"})
    assert resp.status_code == 409 and resp.get_json()["status"] == "busy"


SUMMARY_KEYS = {"status", "session", "minute", "alpha", "alpha2", "signal", "position", "action", "reason", "strategy"}


def test_market_open_cycle_response_is_compact(pg_dsn, calendar, monkeypatch):
    c, r, p = _client(pg_dsn, calendar, token="t0k")
    h = {"X-Cron-Token": "t0k"}
    t = ist(2026, 9, 24, 10, 30, 5)
    p.now = t
    monkeypatch.setattr(main, "now_ist", lambda: t)
    force_indicators(r, 0.5, 0.5)
    resp = c.post("/run-cycle", headers=h)                      # market open, no signal
    body = resp.get_data()
    assert resp.status_code == 200 and len(body) < 2048
    j = resp.get_json()
    assert set(j) == SUMMARY_KEYS
    assert j["status"] == "no_action" and j["action"] == "none" and j["session"] == "OPEN"
    assert j["position"] == "FLAT" and j["minute"] == "2026-09-24T10:30:00+05:30"
    for bulk in ("chain", "snapshots", "quotes", "strikes", "bars", "["):
        assert bulk not in body.decode()
    t2 = ist(2026, 9, 24, 10, 31, 5)
    p.now = t2
    monkeypatch.setattr(main, "now_ist", lambda: t2)
    force_indicators(r, 0.95, 0.95)
    resp = c.post("/run-cycle", headers=h)                      # market open, entry
    j = resp.get_json()
    assert len(resp.get_data()) < 2048
    assert j["action"] == "entry" and j["position"] == "IN_POSITION" and j["alpha"] == 0.95 and "signal_id" in j


def test_summary_is_bounded_even_with_huge_error_text():
    from main import MAX_RESPONSE_BYTES, summarize_cycle
    import json as _json
    s = summarize_cycle({"status": "data_error", "detail": "x" * 50_000},
                        {"minute": "2026-09-24T10:30:00+05:30", "alpha": 0.1, "alpha2": 0.2})
    assert len(_json.dumps(s)) < MAX_RESPONSE_BYTES and len(s["reason"]) == 200


def test_error_pages_are_compact_json(pg_dsn, calendar):
    c, _, _ = _client(pg_dsn, calendar, token="t0k")
    for resp in (c.get("/run-cycle"), c.get("/nope")):
        assert resp.is_json and len(resp.get_data()) < 200
