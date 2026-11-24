"""zen_strategy_10: one 45-minute price-change rank, entries from 11:45, capped lots, no profit target."""
from datetime import time

import numpy as np
import pandas as pd
import pytest

from strategy import registry
from strategy import zen_strategy_10_momentum as s10
from utils.time import IST


def _bars(closes):
    index = pd.date_range("2026-09-21 09:15", periods=len(closes), freq="1min", tz=IST)
    closes = np.asarray(closes, dtype=float)
    return pd.DataFrame({"open": np.r_[closes[0], closes[:-1]], "close": closes}, index=index)


def test_profile_changes_only_the_signal_window_thresholds_and_the_loss_cap():
    cfg, base = registry.apply_profile("zen_strategy_10"), registry.apply_profile("zen_strategy_01")
    changed = {f for f in cfg.__dataclass_fields__ if getattr(cfg, f) != getattr(base, f)}
    assert changed == {"price_change_horizon_minutes", "bullish_threshold", "bearish_threshold", "signal_start",
                       "max_loss_fraction"}
    assert (cfg.price_change_horizon_minutes, cfg.alpha_lookback_minutes) == (45, 800)
    assert (cfg.bullish_threshold, cfg.bearish_threshold, cfg.signal_start) == (0.9, 0.1, time(11, 45))
    assert cfg.max_loss_fraction == 0.025
    assert cfg.stop_loss_margin_fraction * cfg.margin_to_width_ratio * cfg.spread_distance == pytest.approx(45.0)
    assert s10.PROFIT_TARGET_ENABLED is False


def test_it_is_registered_and_run_by_the_paper_worker():
    assert "zen_strategy_10" in registry.strategy_names()
    assert "zen_strategy_10" not in registry.RESEARCH_ONLY          # listed in Algo Lab on 20 Nov 2026
    assert registry.get_strategy("zen_strategy_10") is s10


def test_rank_is_the_45_minute_change_over_800_candles_and_needs_no_option_panel():
    rng = np.random.default_rng(10)
    closes = 24000 + np.cumsum(rng.normal(0, 4, 1200))
    bars = _bars(closes)
    frame = s10.calculate_indicators(bars)                      # no panel at all
    assert frame.index[0] == bars.index[0] + pd.Timedelta(minutes=1)   # decision clock = candle start + 1 minute
    assert frame.alpha.equals(frame.alpha2)
    assert frame.alpha.iloc[:844].isna().all() and frame.alpha.iloc[844:].notna().all()   # 45 + 800 - 1 candles
    k = 1100
    change = (bars.close - bars.open.shift(45)) / bars.open.shift(45)
    assert frame.price_change.iloc[k] == pytest.approx(change.iloc[k])
    window = change.iloc[k - 799:k + 1]
    expected = ((window < window.iloc[-1]).sum() + ((window == window.iloc[-1]).sum() + 1) / 2) / 800
    assert frame.alpha.iloc[k] == pytest.approx(expected)
    # causal: later candles never change an earlier rank
    assert s10.calculate_indicators(bars.iloc[:k + 1]).alpha.iloc[k] == frame.alpha.iloc[k]


def test_a_strong_rise_ranks_bullish_and_a_strong_fall_bearish():
    flat = [24000.0] * 1000
    up = s10.calculate_indicators(_bars(flat + list(np.linspace(24000, 24200, 60)))).alpha.iloc[-1]
    down = s10.calculate_indicators(_bars(flat + list(np.linspace(24000, 23800, 60)))).alpha.iloc[-1]
    assert up > s10.BULLISH_RANK and down < s10.BEARISH_RANK


def test_live_engine_enters_from_index_candles_alone_and_only_from_1145():
    """The paper worker's path: indicators from the view's candles, no option snapshots, capped lots."""
    from datetime import date
    from data.market_calendar import HolidaySetCalendar
    from data.providers.base import OptionChainSnapshot, OptionQuote
    from strategy.engine import MarketView
    cfg = registry.apply_profile("zen_strategy_10")
    engine = registry.create_engine("zen_strategy_10", cfg, HolidaySetCalendar(set()), max_data_age_seconds=None,
                                    require_quotes=False)
    expiry = date(2026, 9, 29)

    def view(closes, minutes_after_open):
        index = pd.date_range("2026-09-22 09:15", periods=375, freq="1min", tz=IST).append(
            pd.date_range("2026-09-23 09:15", periods=375, freq="1min", tz=IST)).append(
            pd.date_range("2026-09-24 09:15", periods=minutes_after_open, freq="1min", tz=IST))
        closes = np.asarray(closes, dtype=float)[-len(index):]
        bars = pd.DataFrame({"open": np.r_[closes[0], closes[:-1]], "close": closes}, index=index)
        now = index[-1] + pd.Timedelta(minutes=1)
        atm = float(np.floor((bars.open.iloc[-1] + 25 - 1e-8) / 50) * 50)
        chain = OptionChainSnapshot("NIFTY", expiry, now, float(bars.close.iloc[-1]))
        for k in np.arange(atm - 1000, atm + 1050, 50):
            ce, pe = max(5.0, 150.0 - (k - atm) / 4.0), max(5.0, 150.0 + (k - atm) / 4.0)
            chain.quotes[(float(k), "CE")] = OptionQuote(float(k), "CE", ce, ce, ce, None)
            chain.quotes[(float(k), "PE")] = OptionQuote(float(k), "PE", pe, pe, pe, None)
        return MarketView(now=now, spot_bars=bars, snapshots=None, chain=chain, expiries=[expiry], lot_size=65), atm

    flat = [24000.0] * 1200
    rise, fall = list(np.linspace(24000, 24200, 60)), list(np.linspace(24000, 23800, 60))
    early, _ = view(flat + rise, 120)                                   # 11:15: before the window
    assert engine.evaluate(early, None).reason == "outside signal window"
    bullish, atm = view(flat + rise, 180)                               # 12:15
    entry = engine.evaluate(bullish, None)
    assert entry.action == "entry" and entry.position.option_type == "PE"
    assert (entry.position.sell_strike, entry.position.buy_strike) == (atm, atm - 400)
    assert entry.position.target is None                                # no profit target
    assert entry.position.stop_loss == pytest.approx(entry.position.net_credit + 45)
    assert entry.position.lots == 2                                     # 8,000 / (45 x 65) = 2.7 -> 2, not margin's 5
    bearish, atm = view(flat + fall, 180)
    entry = engine.evaluate(bearish, None)
    assert entry.action == "entry" and entry.position.option_type == "CE"
    assert (entry.position.sell_strike, entry.position.buy_strike) == (atm, atm + 400)


def test_replay_closes_an_overnight_spread_on_schedule_when_the_hedge_has_no_price():
    """The cached history has no price for the 400-point hedge after a favourable move. With
    carry_hedge_overnight the spread still closes at its next-day exit, the hedge valued by a model."""
    from datetime import date

    from data.market_calendar import HolidaySetCalendar
    from data.providers.base import OptionChainSnapshot, OptionQuote
    from risk.exits import TIME_EXIT
    from strategy.engine import MarketView, Position
    from tests.conftest import ist

    expiry = date(2026, 11, 24)
    pos = Position(signal_id="x", entry_ts=ist(2026, 11, 18, 12, 0), expiry=expiry, option_type="CE",
                   sell_strike=25300.0, buy_strike=25700.0, lots=2, lot_size=65, units=130, sell_price=110.0,
                   buy_price=20.0, net_credit=90.0, stop_loss=135.0, target=None, max_loss=None, max_profit=None,
                   exit_due=ist(2026, 11, 19, 14, 53), spot_at_entry=25300.0, alpha=0.05, alpha2=0.05,
                   allocated_capital=320000.0)

    def view(day, hour, minute, spot, short, hedge):
        now = ist(2026, 11, day, hour, minute)
        chain = OptionChainSnapshot("NIFTY", expiry, now, spot)
        chain.quotes[(25300.0, "CE")] = OptionQuote(25300.0, "CE", short, short, short, None)
        if hedge is not None:
            chain.quotes[(25700.0, "CE")] = OptionQuote(25700.0, "CE", hedge, hedge, hedge, None)
        return MarketView(now=now, spot_bars=None, snapshots=None, chain=chain, expiries=[expiry], lot_size=65,
                          position_chain=chain)

    def engine(**flags):
        made = registry.create_engine("zen_strategy_10", None, HolidaySetCalendar(set()), max_data_age_seconds=None)
        for name, value in flags.items():
            setattr(made, name, value)
        return made

    steps = [(18, 12, 30, 25250.0, 95.0, 14.0), (18, 15, 0, 25150.0, 60.0, None), (19, 11, 0, 25100.0, 40.0, None)]
    due = (19, 14, 53, 25080.0, 30.0, None)

    for flags in ({}, {"carry_missing_hedge": True}):               # live engine, and the same-session carry: still held
        held = engine(**flags)
        for step in steps:
            assert held.evaluate(view(*step), pos).action == "none"
        assert held.evaluate(view(*due), pos).action == "none"

    replay = engine(carry_missing_hedge=True, carry_hedge_overnight=True)
    for step in steps:
        assert replay.evaluate(view(*step), pos).action == "none"
    assert replay.evaluate(view(*steps[-1]), pos).diagnostics["spread_value"] == pytest.approx(26.0)   # 40 - 14 carried
    out = replay.evaluate(view(*due), pos)
    assert out.action == "exit" and out.reason == TIME_EXIT
    hedge = out.diagnostics["hedge_carried_exit_value"]
    assert out.diagnostics["hedge_carried_value"] == pytest.approx(14.0)
    assert 0.0 < hedge < 14.0                                        # further out of the money and a day older
    assert out.exit.exit_value == pytest.approx(30.0 - hedge, abs=0.01)
    assert out.diagnostics["hedge_leg_booked_at_zero"] is False
