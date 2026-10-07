"""CSV loading, backtester, metrics and regression checks against the provider history.

The provider CSV is an external reference dataset here; these tests guard the
replication quality of the reconstructed components, they do not feed anything
back into strategy logic.
"""
import dataclasses

import pandas as pd
import pytest

from data.market_calendar import HolidaySetCalendar
from backtest import data as bdata
from backtest.engine import Backtester
from backtest.metrics import compute_metrics
from tests.synthetic import EXPIRY, synthetic_market


def test_csv_loads():
    trades = bdata.load_provider_trades()
    assert len(trades) == 208 and trades["signal_id"].is_unique
    assert trades["entry_ts"].dt.tz is not None
    assert (trades["buy_strike"] - trades["sell_strike"]).abs().eq(400).all()
    assert trades["pnl_reported"].sum() == pytest.approx(835053.25)


def test_metrics_reproduce_provider_reported_figures():
    trades = bdata.load_provider_trades().rename(columns={"pnl_reported": "pnl"})
    m = compute_metrics(trades, 320000.0)
    assert m["total_return_pct"] == 260.95
    assert m["win_rate_pct"] == 58.17
    assert m["max_drawdown_pct"] == pytest.approx(-25.39, abs=0.01)
    assert m["max_consecutive_wins"] == 10 and m["max_consecutive_losses"] == 4
    assert m["win_days_pct"] == pytest.approx(63.30) and m["win_months_pct"] == pytest.approx(86.67)
    assert m["sharpe"] == pytest.approx(2.89, abs=0.01)
    assert m["best_day_pct"] == 13.07 and m["worst_day_pct"] == -20.47
    assert m["max_recovery_days"] == 60


def test_full_mode_backtest_produces_priced_trades(cfg):
    bars, snaps = synthetic_market()
    c = dataclasses.replace(cfg, bullish_threshold=0.6, bearish_threshold=0.4)
    res = Backtester(c, HolidaySetCalendar(set()), bars, lambda d: [EXPIRY], lambda d: 65, snapshots=snaps).run()
    df = res.to_frame()
    assert res.mode == "full" and len(df) >= 1
    closed = df[df["pnl"].notna()]
    assert len(closed) >= 1
    for _, t in closed.iterrows():
        assert t["exit_reason"] in {"Stop loss", "Target", "Time exit", "Expiry"}
        assert t["pnl"] == pytest.approx((t["net_credit"] - t["exit_value"]) * t["units"], abs=0.01)
        assert pd.Timestamp(t["entry_ts"]).time() >= c.signal_start
    # never more than one open position
    starts = pd.to_datetime(df["entry_ts"]).tolist()
    ends = pd.to_datetime(df["exit_ts"]).tolist()
    assert all(starts[i + 1] >= ends[i] for i in range(len(df) - 1) if ends[i] is not pd.NaT)
    assert compute_metrics(closed, c.capital)["trade_count"] == len(closed)
