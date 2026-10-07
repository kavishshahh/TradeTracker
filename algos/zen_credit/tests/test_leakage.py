"""Mandatory data-leakage tests.

Each test perturbs data strictly AFTER a decision time and asserts that nothing
computed at or before that time changes.
"""
import dataclasses

import numpy as np
import pandas as pd
import pytest

from data.market_calendar import HolidaySetCalendar
from strategy.alpha import calculate_alpha, observed_price_change
from strategy.alpha2 import build_atm_panel, calculate_alpha2
from strategy.engine import MarketView, StrategyEngine
from backtest.engine import Backtester
from tests.synthetic import EXPIRY, synthetic_market

CAL = HolidaySetCalendar(set())


@pytest.mark.parametrize('strategy_name',['strategy_01','strategy_02'])
def test_named_completed_formula_prefix_and_future_quotes_cannot_change_past(strategy_name):
    from strategy.registry import get_strategy
    calculate_indicators=get_strategy(strategy_name).calculate_indicators
    rng=np.random.default_rng(41);index=pd.date_range('2026-09-24 09:15',periods=1400,freq='min',tz='Asia/Kolkata')
    bars=pd.DataFrame({'open':23000+rng.normal(0,10,1400).cumsum(),'close':23000+rng.normal(0,10,1400).cumsum()},index=index)
    clock=index+pd.Timedelta(minutes=1)
    panel=pd.DataFrame({'ce_native_volume':rng.uniform(1,100,1400),'pe_native_volume':rng.uniform(1,100,1400),
        'ce_return':rng.normal(0,.01,1400),'pe_return':rng.normal(0,.01,1400)},index=clock)
    cut=1100;full=calculate_indicators(bars,panel)
    pd.testing.assert_frame_equal(full.iloc[:cut+1],calculate_indicators(bars.iloc[:cut+1],panel.iloc[:cut+1]))
    changed_bars=bars.copy();changed_bars.iloc[cut+1:]*=3
    changed_panel=panel.copy();changed_panel.iloc[cut+1:]*=7
    pd.testing.assert_frame_equal(full.iloc[:cut+1],calculate_indicators(changed_bars,changed_panel).iloc[:cut+1])


@pytest.fixture(scope="module")
def market():
    return synthetic_market()


def _loose(cfg):
    # looser thresholds only so that the synthetic market produces trades
    return dataclasses.replace(cfg, bullish_threshold=0.6, bearish_threshold=0.4)


def test_alpha_uses_no_future_prices(market, cfg):
    bars, _ = market
    t = 1300
    full = calculate_alpha(bars, cfg.alpha_lookback_minutes, 5)
    trunc = calculate_alpha(bars.iloc[:t + 1], cfg.alpha_lookback_minutes, 5)
    assert full.iloc[t] == trunc.iloc[-1]
    shocked = bars.copy()
    shocked.iloc[t + 1:, :] *= 1.5
    assert calculate_alpha(shocked, cfg.alpha_lookback_minutes, 5).iloc[:t + 1].equals(full.iloc[:t + 1])


def _alpha2(bars, snaps, cfg):
    pc = observed_price_change(bars, 5)
    pc.index = pc.index + pd.Timedelta(minutes=1)
    return calculate_alpha2(pc, build_atm_panel(snaps), cfg.alpha2_lookback_minutes, 5, 300, 300,
                            factor_lag_bars=cfg.alpha2_factor_lag_bars)


def test_alpha2_uses_no_future_volume_or_volatility(market, cfg):
    bars, snaps = market
    base = _alpha2(bars, snaps, cfg)
    cut = snaps["minute"].drop_duplicates().iloc[700]
    shocked = snaps.copy()
    later = shocked["minute"] > cut
    shocked.loc[later, ["ce_cum_volume", "pe_cum_volume"]] *= 7.0      # future volume
    shocked.loc[later, ["ce_ltp", "pe_ltp"]] *= 3.0                    # future option prices -> volatility
    other = _alpha2(bars, shocked, cfg)
    pd.testing.assert_series_equal(base[base.index <= cut], other[other.index <= cut])
    trunc = _alpha2(bars, snaps[snaps["minute"] <= cut], cfg)
    assert trunc.iloc[-1] == base.loc[cut] or (np.isnan(trunc.iloc[-1]) and np.isnan(base.loc[cut]))


def test_backtester_precomputed_indicators_equal_incremental(market, cfg):
    bars, snaps = market
    bt = Backtester(cfg, CAL, bars, lambda d: [EXPIRY], lambda d: 65, snapshots=snaps)
    frame = bt._indicator_frame()
    engine = StrategyEngine(cfg, CAL, max_data_age_seconds=None)
    for m in snaps["minute"].drop_duplicates().iloc[[650, 700, 740]]:
        view = MarketView(now=m.to_pydatetime(), spot_bars=bars[bars.index < m],
                          snapshots=snaps[snaps["minute"] <= m], chain=None, expiries=[EXPIRY], lot_size=65)
        a, a2, _ = engine.indicators(view)
        assert a == pytest.approx(frame.loc[m, "alpha"], nan_ok=True)
        assert a2 == pytest.approx(frame.loc[m, "alpha2"], nan_ok=True)


def test_entry_price_and_strikes_use_only_current_snapshot(market, cfg):
    bars, snaps = market
    c = _loose(cfg)
    res = Backtester(c, CAL, bars, lambda d: [EXPIRY], lambda d: 65, snapshots=snaps).run()
    assert res.trades, "synthetic market should produce at least one trade"
    first = res.trades[0]
    row = snaps[(snaps["minute"] == pd.Timestamp(first.entry_ts)) & (snaps["strike"] == first.sell_strike)]
    col = "pe_ltp" if first.option_type == "PE" else "ce_ltp"
    assert first.net_credit is not None and row[col].iloc[0] > 0
    shocked = snaps.copy()
    later = shocked["minute"] > pd.Timestamp(first.entry_ts)
    shocked.loc[later, ["ce_ltp", "pe_ltp"]] *= 2.0
    shocked = shocked[~(later & (shocked["strike"] % 100 == 0))]     # future strike availability changes
    res2 = Backtester(c, CAL, bars, lambda d: [EXPIRY], lambda d: 65, snapshots=shocked).run()
    f2 = res2.trades[0]
    assert (f2.entry_ts, f2.sell_strike, f2.buy_strike, f2.option_type, f2.net_credit, f2.stop_loss) == \
           (first.entry_ts, first.sell_strike, first.buy_strike, first.option_type, first.net_credit, first.stop_loss)


def test_future_trade_results_do_not_change_earlier_signals(market, cfg):
    bars, snaps = market
    c = _loose(cfg)
    res = Backtester(c, CAL, bars, lambda d: [EXPIRY], lambda d: 65, snapshots=snaps).run()
    assert len(res.trades) >= 1
    t0 = res.trades[0]
    # change everything after the first exit (the outcome of later trades)
    cut = pd.Timestamp(t0.exit_ts) if t0.exit_ts else pd.Timestamp(t0.entry_ts)
    b2 = bars.copy()
    b2.loc[b2.index > cut, ["open", "high", "low", "close"]] *= 0.9
    s2 = snaps.copy()
    s2.loc[s2["minute"] > cut, ["ce_ltp", "pe_ltp"]] *= 0.5
    res2 = Backtester(c, CAL, b2, lambda d: [EXPIRY], lambda d: 65, snapshots=s2).run()
    a, b = res.trades[0], res2.trades[0]
    assert (a.entry_ts, a.direction, a.sell_strike, a.alpha, a.alpha2) == \
           (b.entry_ts, b.direction, b.sell_strike, b.alpha, b.alpha2)
