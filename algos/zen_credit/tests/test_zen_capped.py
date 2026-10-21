"""zen_strategy_05/06: per-trade loss cap and the one-session pause after a stop."""
from dataclasses import replace
from datetime import date

import pytest

from data.market_calendar import HolidaySetCalendar
from risk.exits import STOP_LOSS, TARGET
from risk.position_sizing import build_risk_plan
from strategy import registry
from strategy.engine import StrategyEngine
from tests.conftest import ist


@pytest.mark.parametrize("name", ["zen_strategy_05", "zen_strategy_06"])
def test_profiles_keep_the_signal_and_add_risk_rules(name):
    cfg = registry.apply_profile(name)
    base = registry.apply_profile({"zen_strategy_05": "zen_strategy_01", "zen_strategy_06": "zen_strategy_02"}[name])
    assert cfg.stop_loss_margin_fraction * cfg.margin_to_width_ratio * cfg.spread_distance == pytest.approx(35.0)
    assert (cfg.max_loss_fraction, cfg.stop_cooldown_sessions) == (0.025, 1)
    for field in ("alpha_lookback_minutes", "alpha2_lookback_minutes", "signal_start", "signal_end", "spread_distance",
                  "strike_reference", "max_short_premium", "target_spread_value", "time_exit", "volatility_window"):
        assert getattr(cfg, field) == getattr(base, field), field
    module = registry.get_strategy(name)
    assert module.calculate_indicators is registry.get_strategy(
        {"zen_strategy_05": "zen_strategy_01", "zen_strategy_06": "zen_strategy_02"}[name]).calculate_indicators


def test_lot_cap_limits_the_loss_of_one_stop():
    cfg = registry.apply_profile("zen_strategy_05")
    plan = build_risk_plan(110.0, 20.0, 400, 65, False, cfg, date(2026, 9, 24))
    stop_loss_rupees = (plan.stop_loss - plan.net_credit) * plan.units
    assert stop_loss_rupees <= cfg.capital * cfg.max_loss_fraction
    uncapped = build_risk_plan(110.0, 20.0, 400, 65, False, replace(cfg, max_loss_fraction=None), date(2026, 9, 24))
    assert plan.lots == 3 and uncapped.lots == 5   # 8,000 / (35 x 65) = 3.5 -> 3; 320,000 / 58,500 = 5.5 -> 5


def test_cooldown_skips_the_rest_of_the_stop_day_and_the_next_session():
    cfg = registry.apply_profile("zen_strategy_05")
    calendar = HolidaySetCalendar({date(2026, 10, 2)})
    engine = StrategyEngine(cfg, calendar, max_data_age_seconds=None, require_quotes=False)
    engine.note_exit(ist(2026, 9, 30, 11, 0), TARGET)
    assert engine.cooldown_until is None                     # only stops start a pause
    engine.note_exit(ist(2026, 10, 1, 11, 0), STOP_LOSS)     # Thursday; Friday 2 Oct is a holiday
    assert engine.cooldown_until == date(2026, 10, 6)        # Mon 5 Oct is skipped, Tue 6 Oct trades
    from strategy.engine import MarketView
    view = MarketView(now=ist(2026, 10, 5, 11, 0), spot_bars=None, snapshots=None, chain=None, expiries=[], lot_size=65)
    assert engine.evaluate(view, None).reason.startswith("cooldown after stop until 2026-10-06")


def test_default_config_has_no_cap_and_no_cooldown():
    cfg = registry.apply_profile("zen_strategy_01")
    assert cfg.max_loss_fraction is None and cfg.stop_cooldown_sessions == 0
    engine = StrategyEngine(cfg, HolidaySetCalendar(set()), max_data_age_seconds=None, require_quotes=False)
    engine.note_exit(ist(2026, 10, 1, 11, 0), STOP_LOSS)
    assert engine.cooldown_until is None
