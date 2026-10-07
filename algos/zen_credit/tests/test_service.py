"""Runner end-to-end: fake market data, a local test Postgres, a mocked SMTP server."""
from datetime import date, timedelta

import pytest

from config import Config, DataConfig, EmailConfig, RuntimeConfig, StrategyConfig
from execution.store import Store
from main import Runner
from notifications.email import EmailNotifier
from tests.conftest import FakeProvider, FakeSMTP, ist

EXPS = [date(2026, 9, 29), date(2026, 10, 6)]


def make_config(dsn: str, smtp: bool = True, token: str = "", strategy=None) -> Config:
    email = (EmailConfig(host="smtp.test", port=587, username="", password="pw-secret", sender="a@x",
                         recipients="b@x", use_tls=True, enabled=True)
             if smtp else EmailConfig(host="", sender="", recipients="", password="", enabled=True))
    # This fixture has independently mocked chain spot and candle prices; keep
    # its explicit spot-based strikes for notification/idempotency assertions.
    return Config(strategy=strategy or StrategyConfig(strike_reference="spot"), data=DataConfig(database_url=dsn), email=email,
                  runtime=RuntimeConfig(cron_token=token, strategy_name="description"))


def make_runner(dsn, calendar, smtp=True, provider=None, token="", strategy=None):
    cfg = make_config(dsn, smtp, token, strategy)
    prov = provider or FakeProvider(EXPS)
    r = Runner(cfg, Store(dsn), prov, calendar, EmailNotifier(cfg.email, smtp_factory=FakeSMTP))
    return r, prov


def force_indicators(runner, alpha, alpha2):
    runner.engine.indicators = lambda view: (alpha, alpha2, {})


def run_at(runner, prov, ts):
    prov.now = ts
    return runner.cycle(ts)


class ExplodingProvider(FakeProvider):
    """Any market-data request fails the test: proves the session gate short-circuits."""
    def get_spot_bars(self, as_of):
        raise AssertionError("market data fetched on a closed session")

    def get_expiries(self):
        raise AssertionError("market data fetched on a closed session")

    def get_option_chain(self, expiry):
        raise AssertionError("market data fetched on a closed session")

    def get_lot_size(self, expiry):
        raise AssertionError("market data fetched on a closed session")


def test_strategy02_persists_disabled_target_in_virtual_forward_store(pg_dsn, calendar):
    import pandas as pd
    from execution.store import row_to_position
    cfg=Config(strategy=StrategyConfig(),data=DataConfig(database_url=pg_dsn),
        email=EmailConfig(enabled=False),runtime=RuntimeConfig(strategy_name='strategy_02'))
    provider=FakeProvider(EXPS);now=ist(2026,9,24,10,30)
    provider.get_spot_bars=lambda asof:pd.DataFrame({'open':[provider.spot],
        'close':[provider.spot]},index=pd.DatetimeIndex([asof-timedelta(minutes=1)]))
    runner=Runner(cfg,Store(pg_dsn),provider,calendar,EmailNotifier(cfg.email,smtp_factory=FakeSMTP))
    force_indicators(runner,.1,.1)
    assert run_at(runner,provider,now)['status']=='entry'
    row=runner.store.open_position_row()
    assert row.target is None and row_to_position(row).target is None
    assert runner.store.get_state('selected_strategy')=='strategy_02'
    assert FakeSMTP.sent==[]


def test_no_signal_no_email(pg_dsn, calendar):
    r, p = make_runner(pg_dsn, calendar)
    force_indicators(r, 0.5, 0.5)
    assert run_at(r, p, ist(2026, 9, 24, 10, 30))["status"] == "no_action"
    assert FakeSMTP.sent == []


def test_market_closed_does_nothing(pg_dsn, calendar):
    r, p = make_runner(pg_dsn, calendar)
    force_indicators(r, 0.95, 0.95)
    assert run_at(r, p, ist(2026, 9, 26, 11, 0))["status"] == "market_closed"      # Saturday
    assert run_at(r, p, ist(2026, 10, 2, 11, 0))["status"] == "market_closed"      # holiday
    assert run_at(r, p, ist(2026, 9, 24, 9, 0))["status"] == "market_closed"
    assert FakeSMTP.sent == []


def test_holiday_short_circuit_no_fetch_no_email(pg_dsn, calendar):
    r, p = make_runner(pg_dsn, calendar, provider=ExplodingProvider(EXPS))
    r.engine.indicators = lambda view: (_ for _ in ()).throw(AssertionError("alpha computed"))
    res = run_at(r, p, ist(2026, 10, 2, 11, 0))
    assert res == {"status": "market_closed", "session": "HOLIDAY",
                   "reason": "NSE trading holiday (2026-10-02)"}
    wk = run_at(r, p, ist(2026, 9, 26, 11, 0))
    assert wk["session"] == "WEEKEND" and wk["status"] == "market_closed"
    after = run_at(r, p, ist(2026, 9, 24, 15, 30))
    assert after["session"] == "AFTER_CLOSE"
    assert FakeSMTP.sent == []
    assert r.store.claim_minute(ist(2026, 10, 2, 11, 0))    # the holiday minute was never claimed


def test_weekend_decided_without_holiday_lookup(pg_dsn):
    class NoHolidayData(__import__("data.market_calendar", fromlist=["TradingCalendar"]).TradingCalendar):
        def is_trading_day(self, d):
            raise AssertionError("holiday source consulted on a weekend")
    r, p = make_runner(pg_dsn, NoHolidayData(), provider=ExplodingProvider(EXPS))
    assert run_at(r, p, ist(2026, 9, 27, 11, 0))["session"] == "WEEKEND"


def test_entry_then_idempotent_then_exit(pg_dsn, calendar):
    r, p = make_runner(pg_dsn, calendar)
    force_indicators(r, 0.95, 0.95)
    t = ist(2026, 9, 24, 10, 16, 20)
    res = run_at(r, p, t)
    assert res["status"] == "entry"
    assert len(FakeSMTP.sent) == 1 and FakeSMTP.sent[0]["Subject"] == "Zen Credit Algo | NIFTY ENTRY"
    body = FakeSMTP.sent[0].get_content()
    assert body.startswith("NIFTY 23140.00  | Expiry 29-Sep-2026\nSELL  23150 PE   Qty 5 lot (325)")
    # duplicate cron call in the same minute
    assert run_at(r, p, t + timedelta(seconds=20))["status"] == "duplicate"
    # next minute: signal still on, but a position is open -> no new entry, no email
    assert run_at(r, p, t + timedelta(minutes=1))["status"] == "no_action"
    assert len(FakeSMTP.sent) == 1
    st = r.status()
    assert st["strategy_state"] == "IN_POSITION" and st["position"]["sell_strike"] == 23150
    # next trading day at the time exit -> EXIT email once
    t_exit = ist(2026, 9, 25, 14, 53, 5)
    assert run_at(r, p, t_exit)["status"] == "exit"
    assert run_at(r, p, t_exit + timedelta(seconds=10))["status"] == "duplicate"
    assert len(FakeSMTP.sent) == 2 and FakeSMTP.sent[1]["Subject"] == "Zen Credit Algo | NIFTY EXIT"
    lines = FakeSMTP.sent[1].get_content().rstrip("\n").splitlines()
    assert lines[0] == "EXIT 23150/22750 PE  29-Sep-2026" and lines[3] == "Reason: Time exit"
    assert r.status()["strategy_state"] == "FLAT"


def test_stop_loss_exit(pg_dsn, calendar):
    r, p = make_runner(pg_dsn, calendar)
    force_indicators(r, 0.95, 0.95)
    run_at(r, p, ist(2026, 9, 24, 10, 16))
    p.spot = 22900.0                           # market falls through the short put
    res = run_at(r, p, ist(2026, 9, 24, 11, 0))
    assert res == {"status": "exit", "reason": "Stop loss"}


def test_stale_chain_blocks_entry(pg_dsn, calendar):
    r, p = make_runner(pg_dsn, calendar)
    force_indicators(r, 0.95, 0.95)
    p.chain_ts_offset = timedelta(minutes=-20)
    res = run_at(r, p, ist(2026, 9, 24, 10, 20))
    assert res["status"] == "no_action" and "stale option chain" in res["detail"]
    assert FakeSMTP.sent == []


def test_market_data_failure_is_logged_not_emailed(pg_dsn, calendar):
    r, p = make_runner(pg_dsn, calendar, provider=FakeProvider(EXPS, fail=True))
    force_indicators(r, 0.95, 0.95)
    assert run_at(r, p, ist(2026, 9, 24, 10, 20))["status"] == "data_error"
    assert FakeSMTP.sent == []


def test_smtp_unconfigured_keeps_email_pending_and_retries(pg_dsn, calendar):
    r, p = make_runner(pg_dsn, calendar, smtp=False)
    force_indicators(r, 0.95, 0.95)
    assert run_at(r, p, ist(2026, 9, 24, 10, 16))["status"] == "entry"
    row = r.store.open_position_row()
    assert row.entry_email_status == "failed"
    r.notifier = EmailNotifier(make_config(pg_dsn).email, smtp_factory=FakeSMTP)
    run_at(r, p, ist(2026, 9, 24, 10, 17))
    assert len(FakeSMTP.sent) == 1 and r.store.open_position_row().entry_email_status == "sent"
    run_at(r, p, ist(2026, 9, 24, 10, 18))
    assert len(FakeSMTP.sent) == 1                                     # never re-sent


def test_state_survives_restart(pg_dsn, calendar):
    r, p = make_runner(pg_dsn, calendar)
    force_indicators(r, 0.05, 0.05)
    assert run_at(r, p, ist(2026, 9, 24, 10, 16))["status"] == "entry"
    r.store.close()
    r2, p2 = make_runner(pg_dsn, calendar)                             # new process, same DB
    force_indicators(r2, 0.05, 0.05)
    assert run_at(r2, p2, ist(2026, 9, 24, 10, 30))["status"] == "no_action"
    assert r2.status()["position"]["option_type"] == "CE"
    assert run_at(r2, p2, ist(2026, 9, 24, 10, 16, 40))["status"] == "duplicate"   # minute ledger survived
    assert len(FakeSMTP.sent) == 1


def test_snapshots_recorded_each_run(pg_dsn, calendar):
    r, p = make_runner(pg_dsn, calendar)
    force_indicators(r, 0.5, 0.5)
    run_at(r, p, ist(2026, 9, 24, 10, 16))
    run_at(r, p, ist(2026, 9, 24, 10, 17))
    snaps = r.store.load_snapshots(ist(2026, 9, 24))
    assert snaps["minute"].nunique() == 2 and len(snaps) == 2 * 31 * 2
    assert set(snaps["expiry"]) == set(EXPS)
    assert str(snaps["minute"].dt.tz) == "Asia/Kolkata"


def test_locked_cycle_returns_busy_when_lock_held(pg_dsn, calendar):
    r, p = make_runner(pg_dsn, calendar)
    other = Store(pg_dsn)
    with other.lock() as held:
        assert held
        assert r.locked_cycle(ist(2026, 9, 24, 10, 16))["status"] == "busy"
    p.now = ist(2026, 9, 24, 10, 16)
    force_indicators(r, 0.5, 0.5)
    assert r.locked_cycle(ist(2026, 9, 24, 10, 16))["status"] == "no_action"


def test_exit_persists_before_entry_data_or_email(pg_dsn, calendar, monkeypatch):
    r, p = make_runner(pg_dsn, calendar)
    force_indicators(r, .95, .95)
    assert run_at(r, p, ist(2026, 9, 24, 10, 16))["status"] == "entry"

    def unavailable(*args):
        from data.providers.base import MarketDataError
        # Exit must already be saved before optional history/SMTP runs.
        assert r.store.open_position_row() is None
        raise MarketDataError("entry input unavailable")

    monkeypatch.setattr(p, "get_spot_bars", unavailable)
    monkeypatch.setattr(p, "get_lot_size", unavailable)
    monkeypatch.setattr(p, "get_expiries", unavailable)
    monkeypatch.setattr(r, "_flush_pending_emails", unavailable)
    assert run_at(r, p, ist(2026, 9, 25, 14, 53))["status"] == "exit"
    assert r.store.closed_positions()[0].exit_reason == "Time exit"


def test_next_expiry_failure_does_not_block_entry(pg_dsn, calendar, monkeypatch):
    r, p = make_runner(pg_dsn, calendar)
    force_indicators(r, .95, .95)
    original = p.get_option_chain

    def chain(expiry):
        from data.providers.base import MarketDataError
        if expiry == EXPS[1]:
            raise MarketDataError("secondary expiry unavailable")
        return original(expiry)

    monkeypatch.setattr(p, "get_option_chain", chain)
    assert run_at(r, p, ist(2026, 9, 24, 10, 16))["status"] == "entry"


def test_monday_capital_survives_restart_and_drives_return(pg_dsn, calendar):
    allocation = StrategyConfig(strike_reference="spot", monday_capital_fraction=.8)
    r, p = make_runner(pg_dsn, calendar, strategy=allocation)
    force_indicators(r, .95, .95)
    assert run_at(r, p, ist(2026, 9, 28, 10, 16))["status"] == "entry"
    row = r.store.open_position_row()
    assert row.lots == 4 and row.allocated_capital == 256000
    r.store.close()
    r2, p2 = make_runner(pg_dsn, calendar, strategy=allocation)
    assert run_at(r2, p2, ist(2026, 9, 29, 14, 53))["status"] == "exit"
    row = r2.store.closed_positions()[0]
    assert row.allocated_capital == 256000
    assert row.pnl_pct == pytest.approx(round(row.pnl / 256000 * 100, 2), abs=.01)


class MemoryDeploymentStore:
    """Only strategy binding/session-gate state; never connects to a database."""
    def __init__(self):
        self.state = {}
        self.position = None

    def get_state(self, key):
        return self.state.get(key)

    def set_state(self, key, value):
        self.state[key] = value

    def open_position_row(self):
        return self.position


def named_runner(calendar, name="strategy_01", store=None, strategy=None):
    cfg = Config(strategy=strategy or StrategyConfig(), data=DataConfig(database_url=""),
                 email=EmailConfig(enabled=False), runtime=RuntimeConfig(strategy_name=name))
    return Runner(cfg, store or MemoryDeploymentStore(), ExplodingProvider(EXPS), calendar,
                  EmailNotifier(cfg.email, smtp_factory=FakeSMTP))


def test_selected_service_profile_applies_before_engine_and_preserves_user_capital(calendar):
    from strategy.registry import apply_profile
    original = StrategyConfig(capital=123000, volume_short_window=7, volume_baseline_window=99,
                              margin_per_lot_override=42000)
    runner = named_runner(calendar, strategy=original)
    assert runner.cfg.strategy == apply_profile("strategy_01", original)
    assert runner.engine.cfg == runner.cfg.strategy
    assert runner.cfg.strategy.capital == 123000
    assert runner.cfg.strategy.margin_per_lot_override == 42000
    assert original.volume_short_window == 7  # caller's config was not mutated
    assert runner.strategy_name == "strategy_01"
    assert runner.health()["strategy"] == "strategy_01"


def test_description_service_preserves_original_config(calendar):
    original = StrategyConfig(volume_short_window=7, volume_baseline_window=99)
    runner = named_runner(calendar, name="description", strategy=original)
    assert runner.cfg.strategy == original
    assert runner.strategy_name == "description"


def test_service_provider_receives_selected_profile_underlying(calendar, monkeypatch):
    import main
    from types import SimpleNamespace
    seen = []
    cfg = Config(strategy=StrategyConfig(underlying="OTHER"), data=DataConfig(database_url=""),
                 email=EmailConfig(enabled=False), runtime=RuntimeConfig(strategy_name="strategy_01"))
    monkeypatch.setattr(main, 'HttpClient', lambda *a, **kw: object())
    import execution.firestore_store as firestore_storage
    monkeypatch.setattr(firestore_storage, 'FirestoreStore', lambda name: SimpleNamespace(holiday_cache_get=None, holiday_cache_set=None))
    monkeypatch.setattr(main, 'YahooSpotSource', lambda *a: object())
    def provider(*args):
        seen.append(args[-1])
        return ExplodingProvider(EXPS)
    monkeypatch.setattr(main, 'NSEMarketDataProvider', provider)
    monkeypatch.setattr(main, 'NSEHolidayCalendar', lambda *a: calendar)
    runner = Runner.from_config(cfg)
    assert seen == ['NIFTY']
    assert runner.cfg.strategy.underlying == 'NIFTY'
    assert cfg.strategy.underlying == 'OTHER'


def test_service_rejects_unknown_strategy_before_market_requests(calendar):
    with pytest.raises(ValueError):
        named_runner(calendar, name="unknown_strategy")


def test_runtime_reads_named_strategy_and_defaults_to_first(monkeypatch):
    monkeypatch.delenv("STRATEGY_NAME", raising=False)
    assert RuntimeConfig().strategy_name == "strategy_01"
    monkeypatch.setenv("STRATEGY_NAME", " description ")
    assert RuntimeConfig().strategy_name == "description"


def test_strategy_database_binding_prevents_cross_strategy_state(calendar):
    from main import summarize_cycle, MAX_RESPONSE_BYTES
    import json
    store = MemoryDeploymentStore()
    first = named_runner(calendar, store=store)
    result = first.cycle(ist(2026, 10, 3, 11))
    assert result["status"] == "market_closed"
    assert store.state["selected_strategy"] == "strategy_01"
    second = named_runner(calendar, name="description", store=store)
    rejected = second.cycle(ist(2026, 10, 3, 11))
    assert rejected["status"] == "strategy_state_mismatch"
    assert store.state["selected_strategy"] == "strategy_01"
    body = summarize_cycle(rejected, second.last_context)
    assert body["strategy"] == "description"
    assert len(json.dumps(body)) < MAX_RESPONSE_BYTES
    assert FakeSMTP.sent == []


def test_named_strategy_refuses_unlabelled_existing_open_position(calendar):
    store = MemoryDeploymentStore()
    store.position = object()
    runner = named_runner(calendar, store=store)
    assert runner.cycle(ist(2026, 10, 3, 11))["status"] == "strategy_state_mismatch"
    assert "selected_strategy" not in store.state


@pytest.mark.parametrize("name,expected_rows", [("strategy_01", 2), ("strategy_02", 2), ("description", 1)])
def test_service_history_keeps_rollover_inputs_only_for_named_profile(calendar, monkeypatch, name, expected_rows):
    import pandas as pd
    from types import SimpleNamespace
    now = ist(2026, 9, 30, 10, 16)
    store = MemoryDeploymentStore()
    history = pd.DataFrame({'minute': [ist(2026, 9, 29, 10, 15), ist(2026, 9, 30, 10, 15),
                                      ist(2026, 9, 30, 10, 17)],
                            'expiry': [EXPS[0], EXPS[1], EXPS[1]]})
    store.load_snapshots = lambda since: history.copy()
    runner = named_runner(calendar, name=name, store=store)
    runner.provider = FakeProvider(EXPS)
    runner.provider.now = now
    monkeypatch.setattr(runner, '_collect_history', lambda *args: None)
    monkeypatch.setattr(runner, '_flush_pending_emails', lambda: None)
    seen = []
    def evaluate(view, position):
        seen.append(view.snapshots)
        return SimpleNamespace(action='none', reason='history test', diagnostics={})
    monkeypatch.setattr(runner.engine, 'evaluate', evaluate)
    assert runner._evaluate(now, now)['status'] == 'no_action'
    assert len(seen[0]) == expected_rows
    assert (seen[0].minute <= now).all()
    if name != 'description':
        assert set(seen[0].expiry) == set(EXPS)
