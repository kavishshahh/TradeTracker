"""zen_strategy_07 (Damper replica): same-day exit, credit + 40 stop, one re-entry only after a stop."""
from datetime import date, time

import pytest

from data.market_calendar import HolidaySetCalendar
from risk.exits import STOP_LOSS, TARGET, TIME_EXIT, time_exit_due
from strategy import registry
from strategy.engine import MarketView, StrategyEngine
from tests.conftest import ist


def test_profile_keeps_the_signal_and_changes_only_exits_and_reentry():
    cfg = registry.apply_profile("zen_strategy_07")
    base = registry.apply_profile("zen_strategy_01")
    assert cfg.stop_loss_margin_fraction * cfg.margin_to_width_ratio * cfg.spread_distance == pytest.approx(40.0)
    assert (cfg.time_exit_same_day, cfg.time_exit, cfg.max_entries_per_day, cfg.reentry_after_stop_only) == (
        True, time(14, 54), 2, True)
    assert cfg.monday_allocation_start == date(2025, 12, 22)
    for field in ("alpha_lookback_minutes", "alpha2_lookback_minutes", "signal_start", "signal_end", "spread_distance",
                  "strike_reference", "max_short_premium", "target_spread_value", "volatility_window",
                  "historical_time_exit_start", "historical_time_exit_end", "historical_time_exit"):
        assert getattr(cfg, field) == getattr(base, field), field
    assert registry.get_strategy("zen_strategy_07").calculate_indicators is \
        registry.get_strategy("zen_strategy_01").calculate_indicators


def test_scheduled_exit_is_on_the_entry_day():
    cfg = registry.apply_profile("zen_strategy_07")
    calendar = HolidaySetCalendar(set())
    assert time_exit_due(ist(2026, 11, 18, 10, 16), date(2026, 11, 24), calendar, cfg) == ist(2026, 11, 18, 14, 54)
    zen = registry.apply_profile("zen_strategy_01")
    assert time_exit_due(ist(2026, 11, 18, 10, 16), date(2026, 11, 24), calendar, zen).date() == date(2026, 11, 19)


def _engine():
    cfg = registry.apply_profile("zen_strategy_07")
    return StrategyEngine(cfg, HolidaySetCalendar(set()), max_data_age_seconds=None, require_quotes=False)


def _entry_reason(engine, hour, minute):
    view = MarketView(now=ist(2026, 11, 18, hour, minute), spot_bars=None, snapshots=None, chain=None, expiries=[],
                      lot_size=65)
    return engine.evaluate(view, None).reason


def test_reentry_only_after_a_stop_and_at_most_two_trades_a_day():
    engine = _engine()
    engine.note_exit(ist(2026, 11, 18, 11, 0), STOP_LOSS)
    assert "trades already today" not in _entry_reason(engine, 11, 2)       # one stop: may enter again
    assert "no re-entry" not in _entry_reason(engine, 11, 2)
    engine.note_exit(ist(2026, 11, 18, 13, 0), STOP_LOSS)
    assert _entry_reason(engine, 13, 2).startswith("2 trades already today")
    assert engine.cooldown_until is None                                    # no multi-session pause


@pytest.mark.parametrize("reason", [TARGET, TIME_EXIT])
def test_no_reentry_after_a_target_or_time_exit(reason):
    engine = _engine()
    engine.note_exit(ist(2026, 11, 18, 12, 0), reason)
    assert _entry_reason(engine, 12, 5).startswith("no re-entry today")


def test_next_day_starts_fresh():
    engine = _engine()
    engine.note_exit(ist(2026, 11, 17, 12, 0), TARGET)
    assert "no re-entry" not in _entry_reason(engine, 10, 20)


def test_other_strategies_ignore_the_daily_rules():
    cfg = registry.apply_profile("zen_strategy_01")
    assert cfg.max_entries_per_day is None and not cfg.reentry_after_stop_only and not cfg.time_exit_same_day
    engine = StrategyEngine(cfg, HolidaySetCalendar(set()), max_data_age_seconds=None, require_quotes=False)
    engine.note_exit(ist(2026, 11, 18, 12, 0), TARGET)
    assert "no re-entry" not in _entry_reason(engine, 12, 5)


def test_strategy_09_is_the_variance_signal_with_a_target_a_profit_lock_and_capped_lots():
    from risk.position_sizing import build_risk_plan
    cfg = registry.apply_profile("zen_strategy_09")
    base = registry.apply_profile("zen_strategy_02")
    assert cfg.stop_loss_margin_fraction * cfg.margin_to_width_ratio * cfg.spread_distance == pytest.approx(40.0)
    assert (cfg.target_credit_fraction, cfg.max_loss_fraction) == (0.5, 0.025)
    assert (cfg.profit_lock_trigger_fraction, cfg.profit_lock_keep_fraction) == (0.2, 0.0)
    assert (cfg.time_exit_same_day, cfg.time_exit, cfg.max_entries_per_day, cfg.reentry_after_stop_only) == (
        True, time(14, 54), 2, True)
    assert cfg.stop_cooldown_sessions == 0
    for field in ("alpha_lookback_minutes", "alpha2_lookback_minutes", "signal_start", "signal_end", "spread_distance",
                  "strike_reference", "max_short_premium", "volatility_window"):
        assert getattr(cfg, field) == getattr(base, field), field
    module = registry.get_strategy("zen_strategy_09")
    assert module.PROFIT_TARGET_ENABLED is True            # zen_strategy_02 itself has no target
    assert module.calculate_indicators is registry.get_strategy("zen_strategy_02").calculate_indicators
    plan = build_risk_plan(110.0, 20.0, 400, 65, False, cfg, date(2026, 9, 24))
    assert plan.lots == 3                                   # 8,000 / (40 x 65) = 3.08 -> 3 (5 without the cap)
    assert plan.target == pytest.approx(45.0)               # 90 credit: exit at half of it
    assert plan.stop_loss == pytest.approx(130.0)


def _held(engine, spread, hour=11, minute=0, stop=130.0):
    """One exit evaluation of a 90-credit call spread worth ``spread`` now."""
    from data.providers.base import OptionChainSnapshot, OptionQuote
    from strategy.engine import Position
    now = ist(2026, 11, 18, hour, minute)
    expiry = date(2026, 11, 24)
    pos = Position(signal_id="x", entry_ts=ist(2026, 11, 18, 10, 16), expiry=expiry, option_type="CE",
                   sell_strike=25300.0, buy_strike=25700.0, lots=3, lot_size=65, units=195, sell_price=110.0,
                   buy_price=20.0, net_credit=90.0, stop_loss=stop, target=45.0, max_loss=None, max_profit=None,
                   exit_due=ist(2026, 11, 18, 14, 54), spot_at_entry=25300.0, alpha=0.1, alpha2=0.1,
                   allocated_capital=320000.0)
    chain = OptionChainSnapshot("NIFTY", expiry, now, 25300.0)
    chain.quotes[(25300.0, "CE")] = OptionQuote(25300.0, "CE", spread + 5.0, spread + 4.0, spread + 6.0, None)
    chain.quotes[(25700.0, "CE")] = OptionQuote(25700.0, "CE", 5.0, 4.0, 6.0, None)
    view = MarketView(now=now, spot_bars=None, snapshots=None, chain=chain, expiries=[expiry], lot_size=65,
                      position_chain=chain)
    return engine.evaluate(view, pos), pos


def _engine_09():
    return registry.create_engine("zen_strategy_09", None, HolidaySetCalendar(set()), max_data_age_seconds=None,
                                  require_quotes=False)


def test_profit_lock_moves_the_stop_to_break_even_after_a_20_percent_gain():
    engine = _engine_09()
    result, pos = _held(engine, 80.0)                       # 10 of 90 earned: below the 20% trigger
    assert result.action == "none" and "stop_moved_to" not in result.diagnostics and pos.stop_loss == 130.0
    result, pos = _held(engine, 72.0)                       # 18 of 90 earned (20%): the stop moves to the credit
    assert result.action == "none" and result.diagnostics["stop_moved_to"] == 90.0 and pos.stop_loss == 90.0
    result, pos = _held(engine, 60.0, stop=90.0)            # already moved: nothing more to do
    assert result.action == "none" and "stop_moved_to" not in result.diagnostics


def test_a_moved_stop_exits_as_a_profit_lock_and_allows_no_reentry():
    engine = _engine_09()
    result, _ = _held(engine, 91.0, stop=90.0)              # back at the entry credit after the stop moved
    assert result.action == "exit" and result.reason == "Profit lock"
    assert result.exit.pnl == pytest.approx(-1.0 * 195)     # flat, less the minute's slip
    assert _entry_reason(engine, 11, 5).startswith("no re-entry today after a Profit lock")
    stopped, _ = _held(_engine_09(), 131.0)                 # the original stop is still a stop loss
    assert stopped.reason == STOP_LOSS


def test_strategies_without_the_setting_never_move_the_stop():
    engine = registry.create_engine("zen_strategy_07", None, HolidaySetCalendar(set()), max_data_age_seconds=None,
                                    require_quotes=False)
    result, pos = _held(engine, 60.0)
    assert result.action == "none" and "stop_moved_to" not in result.diagnostics and pos.stop_loss == 130.0


def test_replay_option_values_a_held_position_when_the_hedge_leg_has_no_price():
    from data.providers.base import OptionChainSnapshot, OptionQuote
    from strategy.engine import Position
    expiry = date(2026, 11, 24)
    pos = Position(signal_id="x", entry_ts=ist(2026, 11, 18, 10, 16), expiry=expiry, option_type="CE",
                   sell_strike=25300.0, buy_strike=25700.0, lots=3, lot_size=65, units=195, sell_price=110.0,
                   buy_price=20.0, net_credit=90.0, stop_loss=130.0, target=45.0, max_loss=None, max_profit=None,
                   exit_due=ist(2026, 11, 18, 14, 54), spot_at_entry=25300.0, alpha=0.1, alpha2=0.1,
                   allocated_capital=320000.0)

    def view(hour, minute, short, hedge):
        now = ist(2026, 11, 18, hour, minute)
        chain = OptionChainSnapshot("NIFTY", expiry, now, 25200.0)
        chain.quotes[(25300.0, "CE")] = OptionQuote(25300.0, "CE", short, short, short, None)
        if hedge is not None:
            chain.quotes[(25700.0, "CE")] = OptionQuote(25700.0, "CE", hedge, hedge, hedge, None)
        return MarketView(now=now, spot_bars=None, snapshots=None, chain=chain, expiries=[expiry], lot_size=65,
                          position_chain=chain)

    live = registry.create_engine("zen_strategy_07", None, HolidaySetCalendar(set()), max_data_age_seconds=None)
    assert live.evaluate(view(14, 54, 70.0, None), pos).reason == "Time exit due but no valid quotes"   # unchanged

    replay = registry.create_engine("zen_strategy_07", None, HolidaySetCalendar(set()), max_data_age_seconds=None)
    replay.carry_missing_hedge = True
    assert replay.evaluate(view(12, 0, 80.0, 12.0), pos).action == "none"       # hedge printed 12
    held = replay.evaluate(view(12, 1, 80.0, None), pos)                        # no print: reuse 12 for the checks
    assert held.action == "none" and held.diagnostics["spread_value"] == pytest.approx(68.0)
    out = replay.evaluate(view(14, 54, 70.0, None), pos)
    assert out.action == "exit" and out.reason == TIME_EXIT
    assert out.exit.exit_value == pytest.approx(70.0)                           # hedge booked at zero, not at 12
    assert out.diagnostics["hedge_carried_value"] == pytest.approx(12.0)


def test_research_only_strategies_never_get_a_paper_runner():
    from execution import coordinator
    from strategy.registry import RESEARCH_ONLY, STRATEGIES
    assert RESEARCH_ONLY == {"zen_strategy_07", "zen_strategy_09"} and RESEARCH_ONLY <= set(STRATEGIES)

    class Db:
        def collection(self, name):
            return self
        def stream(self, timeout=None):
            return []
    class Provider:
        def begin_round(self):
            pass
    class Store:
        def open_position_row(self):
            return None
    class Runner:
        store = Store()
    made = []
    worker = coordinator.PaperCoordinator(Db(), Provider(), lambda cfg, provider: made.append(cfg.runtime.strategy_name) or Runner())
    worker.run_once(ist(2026, 11, 18, 11, 0))
    assert made and not RESEARCH_ONLY & set(made) and "zen_strategy_05" in made
