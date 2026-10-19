"""Vectorised Black-Scholes implied volatility for index options (no dividends).

Used by strategy_03 so historical replay (candle closes) and the live service
(LTP snapshots) derive IV with one formula instead of a vendor IV feed.
Time to expiry counts calendar time to 15:30 IST on the expiry date, in years.
Prices below intrinsic or at/below zero have no solution and return NaN.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

import numpy as np
import pandas as pd

from utils.time import IST

SQRT2 = np.sqrt(2.0)
YEAR_MINUTES = 365.0 * 24 * 60


def _norm_cdf(x):
    from math import erf
    return 0.5 * (1.0 + np.vectorize(erf)(x / SQRT2))


def _norm_cdf_fast(x):
    # scipy-free CDF with ~1e-7 accuracy (Abramowitz-Stegun 7.1.26 on erf)
    x = np.asarray(x, dtype=float)
    z = np.abs(x) / SQRT2
    t = 1.0 / (1.0 + 0.3275911 * z)
    poly = t * (0.254829592 + t * (-0.284496736 + t * (1.421413741 + t * (-1.453152027 + t * 1.061405429))))
    erf = 1.0 - poly * np.exp(-z * z)
    return 0.5 * (1.0 + np.sign(x) * erf)


def bs_price(spot, strike, t_years, sigma, is_call, rate: float = 0.0):
    spot, strike, t, sigma = (np.asarray(a, dtype=float) for a in (spot, strike, t_years, sigma))
    is_call = np.asarray(is_call, dtype=bool)
    with np.errstate(divide="ignore", invalid="ignore"):
        sq = sigma * np.sqrt(t)
        d1 = (np.log(spot / strike) + (rate + 0.5 * sigma ** 2) * t) / sq
        d2 = d1 - sq
        disc = np.exp(-rate * t)
        call = spot * _norm_cdf_fast(d1) - strike * disc * _norm_cdf_fast(d2)
        put = strike * disc * _norm_cdf_fast(-d2) - spot * _norm_cdf_fast(-d1)
    return np.where(is_call, call, put)


def implied_vol(price, spot, strike, t_years, is_call, rate: float = 0.0, lo: float = 0.01, hi: float = 5.0,
                iterations: int = 60):
    """Bisection in [lo, hi] (annualised); monotone in sigma so it always converges.

    Returns NaN where inputs are invalid, price is below intrinsic, or outside the
    bracket. Output is a percentage (e.g. 12.5), matching exchange conventions.
    """
    price, spot, strike, t = (np.asarray(a, dtype=float) for a in (price, spot, strike, t_years))
    is_call = np.asarray(is_call, dtype=bool)
    shape = np.broadcast(price, spot, strike, t, is_call).shape
    price, spot, strike, t, is_call = (np.broadcast_to(a, shape).copy() for a in (price, spot, strike, t, is_call))
    disc = np.exp(-rate * t)
    intrinsic = np.where(is_call, np.maximum(spot - strike * disc, 0.0), np.maximum(strike * disc - spot, 0.0))
    valid = np.isfinite(price) & np.isfinite(spot) & np.isfinite(strike) & np.isfinite(t) & (price > 0) & (spot > 0) & (strike > 0) & (t > 0)
    valid &= price > intrinsic + 1e-9
    low = np.full(shape, lo); high = np.full(shape, hi)
    p_lo = bs_price(spot, strike, t, low, is_call, rate); p_hi = bs_price(spot, strike, t, high, is_call, rate)
    valid &= (p_lo <= price) & (price <= p_hi)
    for _ in range(iterations):
        mid = 0.5 * (low + high)
        pm = bs_price(spot, strike, t, mid, is_call, rate)
        up = pm < price
        low = np.where(up, mid, low); high = np.where(up, high, mid)
    sigma = 0.5 * (low + high)
    return np.where(valid, sigma * 100.0, np.nan)


def years_to_expiry(minutes: pd.DatetimeIndex, expiries, close_time: time = time(15, 30)) -> np.ndarray:
    """Calendar time from each decision minute to 15:30 IST on its expiry date."""
    minutes = pd.DatetimeIndex(minutes)
    if minutes.tz is None:
        raise ValueError("decision minutes must be timezone-aware")
    minutes = minutes.tz_convert(IST)
    ends = pd.DatetimeIndex([pd.Timestamp(datetime.combine(e, close_time), tz=IST) if isinstance(e, date) and not pd.isna(e)
                             else pd.NaT for e in expiries])
    delta = (ends - minutes).total_seconds().to_numpy() / 60.0
    return delta / YEAR_MINUTES
