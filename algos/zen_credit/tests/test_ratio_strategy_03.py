"""Strategy 03 (Ratio-Fluxer style): IV solver, panel, indicators, signal and exit rules."""
from datetime import date, datetime, time

import numpy as np
import pandas as pd
import pytest

from data.market_calendar import HolidaySetCalendar
from risk.exits import TARGET, TIME_EXIT, evaluate_exit, time_exit_due
from risk.position_sizing import build_risk_plan
from strategy import registry
from strategy import ratio_strategy_03_fluxer as s3
from strategy.implied_vol import bs_price, implied_vol, years_to_expiry
from strategy.signals import Signal, evaluate_signal
from tests.conftest import ist
from utils.time import IST

EXPIRY = date(2026, 9, 29)
DAYS = [date(2026, 9, 23), date(2026, 9, 24), date(2026, 9, 25), date(2026, 9, 28)]


def _bars(days=DAYS, seed=3):
    rng = np.random.default_rng(seed)
    idx = pd.DatetimeIndex([t for d in days for t in
                            pd.date_range(pd.Timestamp(datetime.combine(d, time(9, 15)), tz=IST), periods=375, freq="1min")])
    close = 24000 * np.exp(np.cumsum(rng.normal(0, 0.0002, len(idx))))
    open_ = np.r_[24000.0, close[:-1]]
    return pd.DataFrame({"open": open_, "high": np.maximum(open_, close) + 1,
                         "low": np.minimum(open_, close) - 1, "close": close}, index=idx)


def _options(bars, skew_points):
    """Price ATM +-100/200 strikes from a smile whose put-call wing difference is ``skew_points``."""
    clock = bars.index + pd.Timedelta(minutes=1)
    close = bars["close"].to_numpy()
    tyrs = years_to_expiry(clock, [EXPIRY] * len(clock))
    skew = np.broadcast_to(np.asarray(skew_points, dtype=float), len(clock))
    rows = []
    for i, m in enumerate(clock):
        atm = float(s3.atm_strike(close[i]))
        for k in (-4, -2, 0, 2, 4):
            strike = atm + 50 * k
            iv_ce = 0.13 + (0.0 if k <= 0 else 0.0)              # flat call wing
            iv_pe = 0.13 + (skew[i] / 100.0 if k < 0 else 0.0)   # put wing carries the skew
            rows.append({"minute": m, "expiry": EXPIRY, "strike": strike,
                         "ce_ltp": float(bs_price(close[i], strike, tyrs[i], iv_ce, True, rate=s3.RISK_FREE_RATE)),
                         "pe_ltp": float(bs_price(close[i], strike, tyrs[i], iv_pe, False, rate=s3.RISK_FREE_RATE))})
    return pd.DataFrame(rows).set_index(["minute", "expiry", "strike"])


# ----------------------------------------------------------------------------- implied vol
def test_implied_vol_round_trip_and_invalid_inputs():
    spot, strikes, t = 24000.0, np.array([23800.0, 24000.0, 24200.0]), 2.5 / 365
    for sigma in (0.08, 0.15, 0.40):
        for call in (True, False):
            price = bs_price(spot, strikes, t, sigma, call, rate=0.065)
            iv = implied_vol(price, spot, strikes, t, call, rate=0.065)
            assert np.allclose(iv, sigma * 100, atol=1e-5)
    bad = implied_vol([0.0, np.nan, 1e-4, 10000.0], spot, 24000.0, t, True)
    assert np.isnan(bad).all()                      # zero, missing, below bracket, above bracket
    assert np.isnan(implied_vol(50.0, spot, 24000.0, 0.0, True))   # expired


def test_years_to_expiry_counts_to_close_of_expiry_day():
    minutes = pd.DatetimeIndex([ist(2026, 9, 28, 15, 30), ist(2026, 9, 29, 15, 30)])
    years = years_to_expiry(minutes, [EXPIRY, EXPIRY])
    assert years[0] == pytest.approx(1 / 365)
    assert years[1] == 0.0
    with pytest.raises(ValueError):
        years_to_expiry(pd.DatetimeIndex([datetime(2026, 9, 28, 15, 30)]), [EXPIRY])


# ----------------------------------------------------------------------------- panel / indicators
def test_panel_recovers_skew_and_matches_between_history_and_snapshots():
    bars = _bars()
    options = _options(bars, 3.0)
    panel = s3.panel_from_options(bars, options, lambda d: [EXPIRY])
    assert list(panel.columns) == list(s3.PANEL_COLUMNS)
    assert panel.index.equals(bars.index + pd.Timedelta(minutes=1))
    valid = panel.dropna(subset=["skew"])
    assert len(valid) > 0.95 * len(panel)
    assert np.allclose(valid["skew"], 3.0, atol=0.05)
    assert np.allclose(valid["iv_ce_atm"], 13.0, atol=0.05)
    snapshots = options.reset_index().assign(spot=np.nan)
    from_snapshots = s3.panel_from_snapshots(bars, snapshots)
    pd.testing.assert_frame_equal(from_snapshots, panel)


def test_indicators_follow_a_skew_regime_change_and_are_causal():
    bars = _bars()
    n = len(bars)
    # calm skew for the first three sessions, then calls become rich (negative skew)
    rng = np.random.default_rng(7)
    skew = np.where(np.arange(n) < 3 * 375, 1.0, s3.SKEW_CALL_MAX - 1.0) + rng.normal(0, 0.05, n)
    panel = s3.panel_from_options(bars, _options(bars, skew), lambda d: [EXPIRY])
    ind = s3.calculate_indicators(bars, panel)
    assert list(ind.columns)[:2] == ["alpha", "alpha2"]
    assert ind["alpha"].iloc[:s3.RANK_MIN_PERIODS - 1].isna().all()
    # the first 100 minutes of the new regime rank below everything in the 800-minute window
    late = ind.iloc[3 * 375 + 1:3 * 375 + 100]
    assert (late["alpha"] < s3.BEARISH_RANK).all()
    assert (late["alpha2"] < s3.BEARISH_RANK).all()
    assert (late["gate"] == 1.0).all()
    calm = ind.iloc[s3.RANK_MIN_PERIODS:3 * 375]
    assert (calm["alpha2"] == 0.5).all()           # gate closed -> neutral alpha2
    # causality: truncating the inputs never changes earlier values
    cut = 3 * 375 + 40
    truncated = s3.calculate_indicators(bars.iloc[:cut], panel.iloc[:cut])
    pd.testing.assert_frame_equal(truncated, ind.iloc[:cut])


def test_profile_pins_expiry_style_rules():
    cfg = registry.apply_profile("ratio_strategy_03")
    assert (cfg.bullish_threshold, cfg.bearish_threshold) == (s3.BULLISH_RANK, s3.BEARISH_RANK)
    assert cfg.target_credit_fraction == 0.5 and cfg.time_exit_on_expiry and cfg.time_exit == time(14, 57)
    assert cfg.max_days_to_expiry == 5 and not cfg.allow_expiry_day_entry
    assert cfg.strike_reference == "last_bar_open" and cfg.spread_distance == 400
    assert cfg.historical_time_exit_start is None
    t = ist(2026, 9, 24, 11, 0)
    assert evaluate_signal(0.05, 0.05, t, cfg) == Signal.BEARISH
    assert evaluate_signal(0.05, 0.5, t, cfg) == Signal.NONE       # gate closed
    assert evaluate_signal(0.95, 0.95, t, cfg) == Signal.BULLISH


# ----------------------------------------------------------------------------- exits / sizing
def test_fractional_target_and_expiry_day_time_exit():
    cfg = registry.apply_profile("ratio_strategy_03")
    plan = build_risk_plan(120.0, 20.0, 400, 65, False, cfg, date(2026, 9, 24))
    assert plan.net_credit == 100.0 and plan.target == 50.0
    assert plan.stop_loss == pytest.approx(100.0 + 0.05 * 2.25 * 400 * 65 / 65)
    calendar = HolidaySetCalendar(set())
    due = time_exit_due(ist(2026, 9, 24, 11, 0), EXPIRY, calendar, cfg)
    assert due == ist(2026, 9, 29, 14, 57)
    assert evaluate_exit(ist(2026, 9, 25, 12, 0), 49.9, plan.stop_loss, plan.target, due, EXPIRY).reason == TARGET
    assert evaluate_exit(ist(2026, 9, 25, 12, 0), 60.0, plan.stop_loss, plan.target, due, EXPIRY) is None
    assert evaluate_exit(ist(2026, 9, 29, 14, 57), 60.0, plan.stop_loss, plan.target, due, EXPIRY).reason == TIME_EXIT


def test_engine_rejects_expiry_day_and_far_expiry_entries():
    from data.providers.base import OptionChainSnapshot, OptionQuote
    from strategy.engine import MarketView, StrategyEngine
    cfg = registry.apply_profile("ratio_strategy_03")
    calendar = HolidaySetCalendar(set())
    engine = StrategyEngine(cfg, calendar, max_data_age_seconds=None, require_quotes=False)
    bars = _bars([date(2026, 9, 29)])

    def view(now, expiries):
        chain = OptionChainSnapshot("NIFTY", expiries[0], now, 24000.0)
        for k in range(23000, 25050, 50):
            ce = max(5.0, 300.0 - (k - 23000) / 8.0)          # 24000 -> 175, 24400 -> 125
            pe = max(5.0, 50.0 + (k - 23000) / 8.0)
            chain.quotes[(float(k), "CE")] = OptionQuote(float(k), "CE", ce, ce - 1, ce + 1, None)
            chain.quotes[(float(k), "PE")] = OptionQuote(float(k), "PE", pe, pe - 1, pe + 1, None)
        return MarketView(now=now, spot_bars=bars.iloc[:5], snapshots=None, chain=chain, expiries=expiries,
                          lot_size=65, indicators=(0.05, 0.05))

    assert engine.evaluate(view(ist(2026, 9, 29, 11, 0), [EXPIRY]), None).reason == "no entry on expiry day"
    far = engine.evaluate(view(ist(2026, 9, 23, 11, 0), [EXPIRY]), None)
    assert far.reason.startswith("expiry 6 days away")
    ok = engine.evaluate(view(ist(2026, 9, 24, 11, 0), [EXPIRY]), None)
    assert ok.action == "entry" and ok.position.option_type == "CE" and ok.position.exit_due == ist(2026, 9, 29, 14, 57)
