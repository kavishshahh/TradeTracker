"""Canonical bar representation.

* Canonical series: 1-minute OHLC bars of the NIFTY 50 index, index = bar START
  time, tz-aware Asia/Kolkata, session 09:15 <= start < 15:30.
* A bar is complete only when ``start + 1 minute <= as_of``; incomplete bars are
  dropped so a live evaluation never sees a partially formed bar.
* Minute counts in the provider description (5, 300, 800 minutes) are counted
  in session bars: the series is the concatenation of trading sessions, so a
  lookback crosses the overnight gap exactly as a bar-indexed shift would.
* ``resample_ohlc`` builds 5-minute bars (anchored at 09:15, left-labelled,
  left-closed, incomplete trailing bar dropped) for diagnostics.
"""
from __future__ import annotations

from datetime import datetime, time

import pandas as pd

from utils.time import IST

BAR_COLUMNS = ["open", "high", "low", "close"]


def normalize_bars(df: pd.DataFrame, session_open: time = time(9, 15),
                   session_close: time = time(15, 30)) -> pd.DataFrame:
    if df.index.tz is None:
        raise ValueError("bar index must be timezone-aware")
    out = df.copy()
    out.index = out.index.tz_convert(IST)
    out = out[~out.index.duplicated(keep="last")].sort_index()
    t = out.index.time
    out = out[(t >= session_open) & (t < session_close)]
    return out.dropna(subset=["open", "close"])


def complete_bars(df: pd.DataFrame, as_of: datetime, bar_minutes: int = 1) -> pd.DataFrame:
    cutoff = pd.Timestamp(as_of).tz_convert(IST) - pd.Timedelta(minutes=bar_minutes)
    return df[df.index <= cutoff]


def resample_ohlc(df: pd.DataFrame, minutes: int = 5, as_of: datetime | None = None) -> pd.DataFrame:
    parts = []
    for _, day in df.groupby(df.index.date):
        anchor = day.index[0].normalize() + pd.Timedelta(hours=9, minutes=15)
        r = day.resample(f"{minutes}min", origin=anchor, label="left", closed="left").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
        parts.append(r)
    out = pd.concat(parts) if parts else df.iloc[0:0]
    if as_of is not None:
        out = complete_bars(out, as_of, minutes)
    return out
