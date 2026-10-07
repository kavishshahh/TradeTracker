"""Time-series rank.

Definition:

    ts_rank(x, w)[t] = rank of x[t] among x[t-w+1 .. t] (average rank for ties)
                       divided by w

The window is trailing and includes the current observation, so no future value
is ever used. The result lies in [1/w, 1]; it is NaN until w valid values exist.
This is exactly ``pandas.Series.rolling(w).rank(pct=True)`` for a full window.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def ts_rank(series: pd.Series, window: int, min_periods: int | None = None) -> pd.Series:
    """``min_periods`` < window tolerates missing observations (e.g. a skipped
    cron minute); the rank is then taken over the valid values only."""
    if window < 1:
        raise ValueError("window must be >= 1")
    s = pd.Series(series, dtype="float64")
    mp = window if min_periods is None else min_periods
    return s.rolling(window, min_periods=mp).rank(method="average", pct=True)


def ts_rank_last(values: np.ndarray) -> float:
    """Reference (slow, explicit) implementation used by the tests."""
    arr = np.asarray(values, dtype=float)
    if np.isnan(arr).any():
        return float("nan")
    cur = arr[-1]
    less = np.sum(arr < cur)
    equal = np.sum(arr == cur)
    avg_rank = less + (equal + 1) / 2.0
    return float(avg_rank / len(arr))
