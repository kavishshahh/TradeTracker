"""alpha2: volume-confirmed, volatility-scaled price change, 300-minute ts_rank.

Provider text: "multiplies the price change by the average volume ratio of ATM
put and call options, then divides by the ATM volatility (sum of CE and PE
rolling volatility), and applies a 300-minute time-series rank."

Implemented interpretation (choices documented in the root README):

* price change      : the same causal 5-minute normalised change used by alpha.
* ATM strike        : nearest listed strike to spot at that minute (nearest expiry).
* per-minute volume : difference of the exchange's cumulative traded volume of
                      the SAME strike between adjacent one-minute snapshots of
                      the same session. Missing minutes remain missing.
* volume ratio      : for each side, mean volume over the last 5 minutes divided
                      by mean volume over the last 300 minutes; the two side
                      ratios are averaged.
* rolling vol       : standard deviation of 1-minute simple returns of the ATM
                      option (same strike across the step) over 300 minutes.
                      Returns, not prices, keep the quantity dimensionless.
* alpha2            : ts_rank(observed_change[T] * volume_ratio[T-h] /
                      (vol_ce[T-h] + vol_pe[T-h]), 300), h=5 in StrategyConfig.
                      This is the complete forward formula delayed by five bars;
                      its starting-bar option factors are delayed with price change.

All windows are trailing, so every value at minute t uses data <= t only.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from strategy.ranking import ts_rank
from utils.time import IST

PANEL_COLUMNS = ["spot", "atm_strike", "ce_volume", "pe_volume", "ce_return", "pe_return"]


def nearest_strike(spot: float, strikes: list[float] | np.ndarray) -> float:
    """Nearest listed strike; an exact tie resolves to the lower strike."""
    arr = np.sort(np.asarray(strikes, dtype=float))
    if arr.size == 0 or not np.isfinite(spot):
        raise ValueError("no strikes / invalid spot")
    dist = np.abs(arr - spot)
    return float(arr[int(np.argmin(dist))])


def build_atm_panel(snapshots: pd.DataFrame) -> pd.DataFrame:
    """Build the per-minute ATM option panel from stored chain snapshots.

    ``snapshots`` (long format) columns: minute (tz-aware), expiry, strike, spot,
    ce_ltp, pe_ltp, ce_cum_volume, pe_cum_volume. One row per (minute, strike).
    """
    if snapshots.empty:
        return pd.DataFrame(columns=PANEL_COLUMNS)
    if snapshots["expiry"].nunique() != 1:
        raise ValueError("ATM panel requires one expiry; filter snapshots before building it")
    if snapshots.duplicated(["minute", "strike"]).any():
        raise ValueError("duplicate minute/strike snapshots")
    snaps = snapshots.sort_values(["minute", "strike"])
    minutes = list(snaps["minute"].drop_duplicates())
    by_minute = {m: g.set_index("strike") for m, g in snaps.groupby("minute", sort=True)}
    rows = []
    prev_m = None
    for m in minutes:
        g = by_minute[m]
        spot = float(g["spot"].iloc[0])
        expiry = g["expiry"].iloc[0]
        atm = nearest_strike(spot, g.index.values)
        rec = {"minute": m, "spot": spot, "atm_strike": atm, "ce_volume": np.nan,
               "pe_volume": np.nan, "ce_return": np.nan, "pe_return": np.nan}
        if prev_m is not None:
            p = by_minute[prev_m]
            gap = (m - prev_m).total_seconds() / 60.0
            same_session = pd.Timestamp(m).date() == pd.Timestamp(prev_m).date()
            if (same_session and gap == 1
                    and p["expiry"].iloc[0] == expiry and atm in p.index):
                cur, old = g.loc[atm], p.loc[atm]
                for side in ("ce", "pe"):
                    dv = cur[f"{side}_cum_volume"] - old[f"{side}_cum_volume"]
                    if dv >= 0:
                        rec[f"{side}_volume"] = dv
                    if old[f"{side}_ltp"] > 0 and cur[f"{side}_ltp"] > 0:
                        rec[f"{side}_return"] = cur[f"{side}_ltp"] / old[f"{side}_ltp"] - 1.0
        rows.append(rec)
        prev_m = m
    panel = pd.DataFrame(rows).set_index("minute")
    panel.index = pd.DatetimeIndex(panel.index).tz_convert(IST)
    # Rolling windows count session minutes. Do not compress gaps or invent returns.
    days = []
    for _, day in panel.groupby(panel.index.date):
        days.append(day.reindex(pd.date_range(day.index[0], day.index[-1], freq="1min")))
    result = pd.concat(days)
    result.index.name = "minute"
    return result


def volume_ratio(volume: pd.Series, short: int, baseline: int, min_frac: float = 0.8) -> pd.Series:
    s = volume.rolling(short, min_periods=short).mean()
    b = volume.rolling(baseline, min_periods=math.ceil(baseline * min_frac)).mean()
    return s / b.where(b > 0)


def rolling_volatility(returns: pd.Series, window: int, min_frac: float = 0.8) -> pd.Series:
    return returns.rolling(window, min_periods=math.ceil(window * min_frac)).std(ddof=1)


def calculate_alpha2(price_change: pd.Series, panel: pd.DataFrame, lookback: int = 300,
                     volume_short: int = 5, volume_baseline: int = 300,
                     vol_window: int = 300, return_components: bool = False,
                     factor_lag_bars: int = 0):
    """``price_change`` and ``panel`` must share the same minute index."""
    pc = price_change.reindex(panel.index)
    vr = (volume_ratio(panel["ce_volume"], volume_short, volume_baseline)
          + volume_ratio(panel["pe_volume"], volume_short, volume_baseline)) / 2.0
    atm_vol = (rolling_volatility(panel["ce_return"], vol_window)
               + rolling_volatility(panel["pe_return"], vol_window))
    if factor_lag_bars < 0:
        raise ValueError("factor_lag_bars must be nonnegative")
    vr = vr.shift(factor_lag_bars)
    atm_vol = atm_vol.shift(factor_lag_bars)
    raw = pc * vr / atm_vol.where(atm_vol > 0)
    alpha2 = ts_rank(raw, lookback, min_periods=math.ceil(lookback * 0.9)).rename("alpha2")
    if return_components:
        return alpha2, pd.DataFrame({"price_change": pc, "volume_ratio": vr,
                                     "atm_volatility": atm_vol, "raw": raw, "alpha2": alpha2})
    return alpha2
