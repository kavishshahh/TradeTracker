"""alpha: time-series rank of the 5-minute forward price change normalised by the
opening price, 800-minute lookback.

Research definition (what the provider text literally says), on 1-minute bars::

    fwd_change[t] = (close[t + h] - close[t]) / open[t]          h = 5 bars
    alpha_research[t] = ts_rank(fwd_change, 800)[t]

``fwd_change[t]`` uses a future price, so it cannot be known at time t. It only
becomes observable at t + h. A live system can therefore only act on::

    alpha_live[T] = ts_rank(fwd_change, 800)[T - h]
                  = rank of (close[T] - close[T-h]) / open[T-h] among the last
                    800 such observed values

i.e. the research series shifted by h bars. Full-history research finds directional
agreement at many entries but does not reproduce most first entry times. This is
a causal hypothesis, not the recovered private formula. ``mode="live"`` is used.
"""
from __future__ import annotations

import pandas as pd

from strategy.ranking import ts_rank


def forward_price_change(bars: pd.DataFrame, horizon: int = 5) -> pd.Series:
    """Research quantity; uses close[t+h] (future). Never use for live signals."""
    return (bars["close"].shift(-horizon) - bars["close"]) / bars["open"]


def observed_price_change(bars: pd.DataFrame, horizon: int = 5) -> pd.Series:
    """The forward change of bar t-h, which becomes known at bar t (causal)."""
    return forward_price_change(bars, horizon).shift(horizon)


def calculate_alpha(bars: pd.DataFrame, lookback: int = 800, horizon: int = 5,
                    mode: str = "live") -> pd.Series:
    if mode == "research":
        change = forward_price_change(bars, horizon)
    elif mode == "live":
        change = observed_price_change(bars, horizon)
    else:
        raise ValueError("mode must be 'live' or 'research'")
    return ts_rank(change, lookback).rename("alpha")
