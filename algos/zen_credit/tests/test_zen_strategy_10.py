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
