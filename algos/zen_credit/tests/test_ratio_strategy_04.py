"""ratio_strategy_04: R3's signal with afternoon entries, a delayed stop plus disaster stop, 40% target."""
from datetime import date, time

from data.market_calendar import HolidaySetCalendar
from strategy import registry
from strategy import ratio_strategy_03_fluxer as s3
from strategy import ratio_strategy_04_fluxer_tuned as s4
from tests.conftest import ist
from tests.test_ratio_strategy_03 import EXPIRY, _bars

R3_KEPT = ("spread_distance", "strike_reference", "time_exit", "time_exit_on_expiry", "max_days_to_expiry",
           "allow_expiry_day_entry", "target_entry_day_only", "signal_end", "monday_capital_fraction")


def test_profile_changes_only_execution_rules():
    r3, r4 = registry.apply_profile("ratio_strategy_03"), registry.apply_profile("ratio_strategy_04")
    assert all(getattr(r3, name) == getattr(r4, name) for name in R3_KEPT)
    assert r4.signal_start == time(11, 45) and r4.stop_grace_minutes == 60 and r4.target_credit_fraction == 0.4
    normal = r4.margin_to_width_ratio * r4.spread_distance
    assert round(r4.stop_loss_margin_fraction * normal, 6) == 50 and round(r4.hard_stop_margin_fraction * normal, 6) == 100
    assert s4.calculate_indicators is s3.calculate_indicators and s4.STRATEGY_NAME == "ratio_strategy_04"
    assert r3.stop_grace_minutes == 0 and r3.hard_stop_margin_fraction is None   # R3 unchanged


def test_stop_waits_for_the_grace_period_but_the_disaster_stop_does_not():
    from data.providers.base import OptionChainSnapshot, OptionQuote
    from strategy.engine import MarketView, Position
    cfg = registry.apply_profile("ratio_strategy_04")
    engine = registry.create_engine("ratio_strategy_04", cfg, HolidaySetCalendar(set()), max_data_age_seconds=None, require_quotes=False)
    pos = Position(signal_id="x", entry_ts=ist(2026, 9, 24, 12, 0), expiry=EXPIRY, option_type="CE",
                   sell_strike=24000.0, buy_strike=24400.0, lots=4, lot_size=65, units=260, sell_price=120.0,
                   buy_price=20.0, net_credit=100.0, stop_loss=150.0, target=60.0, max_loss=None, max_profit=None,
                   exit_due=ist(2026, 9, 29, 14, 57), spot_at_entry=24000.0, alpha=0.05, alpha2=0.05,
                   allocated_capital=320000.0)

    def view(now, spread):
        chain = OptionChainSnapshot("NIFTY", EXPIRY, now, 24000.0)
        chain.quotes[(24000.0, "CE")] = OptionQuote(24000.0, "CE", spread + 5.0, spread + 4.0, spread + 6.0, None)
        chain.quotes[(24400.0, "CE")] = OptionQuote(24400.0, "CE", 5.0, 4.0, 6.0, None)
        return MarketView(now=now, spot_bars=_bars([date(2026, 9, 24)]).iloc[:5], snapshots=None, chain=chain,
                          expiries=[EXPIRY], lot_size=65, indicators=(0.5, 0.5))

    held = engine.evaluate(view(ist(2026, 9, 24, 12, 30), 160.0), pos)     # beyond the stop, inside the grace
    assert held.action == "none" and held.diagnostics["stop_in_grace"] == 200.0
    assert engine.evaluate(view(ist(2026, 9, 24, 12, 30), 205.0), pos).reason == "Stop loss"   # disaster stop
    assert engine.evaluate(view(ist(2026, 9, 24, 13, 0), 160.0), pos).reason == "Stop loss"    # grace over
    assert engine.evaluate(view(ist(2026, 9, 24, 12, 10), 55.0), pos).reason == "Target"       # target unaffected
