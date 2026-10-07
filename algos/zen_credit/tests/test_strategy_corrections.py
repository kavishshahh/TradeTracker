"""Regressions for allocation, expiry rollover and dated settlement."""
from dataclasses import replace
from datetime import date

import numpy as np
import pandas as pd
import pytest

from backtest.engine import Backtester
from data.providers.base import ExpirySettlement
from strategy.alpha import observed_price_change
from strategy.alpha2 import build_atm_panel, calculate_alpha2
from strategy.engine import MarketView, StrategyEngine
from tests.conftest import ist, make_chain, session_bars
from tests.test_persistence import _pos


def test_expired_position_requires_its_official_settlement(cfg, calendar):
    pos = replace(_pos(), allocated_capital=320000)
    now = ist(2026, 9, 30, 10)
    # Today's spot and even a quote claiming the old expiry must not settle it.
    chain = make_chain(now, pos.expiry, 20000)
    view = MarketView(now, None, None, chain, [], None)
    engine = StrategyEngine(cfg, calendar)
    out = engine.evaluate(view, pos)
    assert out.action == "none" and "official settlement unavailable" in out.reason
    view.settlement = ExpirySettlement(date(2026, 10, 6), 23000, "official exchange report")
    assert engine.evaluate(view, pos).action == "none"
    view.settlement = ExpirySettlement(pos.expiry, 23000, "official exchange report")
    out = engine.evaluate(view, pos)
    assert out.action == "exit" and out.exit.reason == "Expiry"
    assert out.exit.exit_value == 150
    assert out.exit.pnl == (95 - 150) * 325
    assert out.diagnostics["settlement_source"] == "official exchange report"


def test_persisted_allocation_controls_percentage_even_if_config_changes(cfg, calendar):
    pos = replace(_pos(), allocated_capital=256000)
    now = ist(2026, 9, 25, 14, 53)
    chain = make_chain(now, pos.expiry, 23140)
    view = MarketView(now, None, None, chain, [], None)
    engine = StrategyEngine(replace(cfg, capital=999999), calendar)
    out = engine.evaluate(view, pos)
    assert out.action == "exit"
    assert out.exit.pnl_pct == pytest.approx(round(out.exit.pnl / 256000 * 100, 2), abs=.01)


def test_rollover_uses_prefetched_history_and_matches_backtester(cfg, calendar):
    days = [date(2026, 9, 28), date(2026, 9, 29), date(2026, 9, 30)]
    bars = session_bars(days, seed=20)
    minutes = bars.index + pd.Timedelta(minutes=1)
    old_exp, new_exp = date(2026, 9, 29), date(2026, 10, 6)
    rng = np.random.default_rng(5)
    frames = []
    for expiry in (old_exp, new_exp):
        ce = 100 * np.exp(np.cumsum(rng.normal(0, .001, len(minutes))))
        pe = 90 * np.exp(np.cumsum(rng.normal(0, .001, len(minutes))))
        volume_ce = np.concatenate([np.cumsum(rng.integers(100, 1000, 375)) for _ in days])
        volume_pe = np.concatenate([np.cumsum(rng.integers(100, 1000, 375)) for _ in days])
        frame = pd.DataFrame({"minute": minutes, "expiry": expiry, "strike": 23000.,
                              "spot": 23000., "ce_ltp": ce, "pe_ltp": pe,
                              "ce_cum_volume": volume_ce, "pe_cum_volume": volume_pe})
        if expiry == old_exp:
            frame = frame[frame.minute.dt.date <= old_exp]
        frames.append(frame)
    snapshots = pd.concat(frames, ignore_index=True)
    now = ist(2026, 9, 30, 10, 15)
    new_history = snapshots[(snapshots.expiry == new_exp) & (snapshots.minute <= now)]
    view = MarketView(now, bars[bars.index < now], new_history, None, [new_exp], 65)
    alpha, alpha2, _ = StrategyEngine(cfg, calendar).indicators(view)
    assert np.isfinite(alpha) and np.isfinite(alpha2)
    pc = observed_price_change(view.spot_bars)
    pc.index += pd.Timedelta(minutes=1)
    cold = new_history[new_history.minute.dt.date == now.date()]
    assert calculate_alpha2(pc, build_atm_panel(cold)).isna().all()
    expiries_for = lambda d: [e for e in (old_exp, new_exp) if e >= d]
    bt = Backtester(cfg, calendar, bars, expiries_for, lambda d: 65, snapshots=snapshots)
    indicators = bt._indicator_frame()
    assert indicators.loc[now, "alpha"] == pytest.approx(alpha)
    assert indicators.loc[now, "alpha2"] == pytest.approx(alpha2)
