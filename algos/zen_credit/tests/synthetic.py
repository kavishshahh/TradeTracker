"""Synthetic 1-minute market (spot bars + option-chain snapshots) for mechanics tests."""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from tests.conftest import session_bars

DAYS = [date(2026, 9, 21), date(2026, 9, 22), date(2026, 9, 23), date(2026, 9, 24), date(2026, 9, 25)]
EXPIRY = date(2026, 9, 29)


def synthetic_market(seed: int = 7, snapshot_days: int = 3, strikes_each_side: int = 12):
    bars = session_bars(DAYS, seed=seed)
    rng = np.random.default_rng(seed + 1)
    snap_days = set(DAYS[-snapshot_days:])
    rows = []
    cum = {}
    for ts, row in bars.iterrows():
        if ts.date() not in snap_days:
            continue
        minute = ts + pd.Timedelta(minutes=1)          # snapshot taken at the bar's end
        spot = float(row["close"])
        k0 = round(spot / 50) * 50
        tau = max((pd.Timestamp(EXPIRY, tz=ts.tz) + pd.Timedelta(hours=15, minutes=30) - ts).total_seconds()
                  / 86400, 0.05)
        for i in range(-strikes_each_side, strikes_each_side + 1):
            k = float(k0 + i * 50)
            tv = 18 * np.sqrt(tau) * np.exp(-abs(spot - k) / 350)
            ce = max(spot - k, 0) + tv
            pe = max(k - spot, 0) + tv
            key = (ts.date(), k)
            c_prev = cum.get(key, (0.0, 0.0))
            c = (c_prev[0] + rng.integers(50, 400), c_prev[1] + rng.integers(50, 400))
            cum[key] = c
            rows.append({"minute": minute, "expiry": EXPIRY, "strike": k, "spot": spot,
                         "ce_ltp": round(ce, 2), "pe_ltp": round(pe, 2),
                         "ce_bid": round(ce - 0.25, 2), "ce_ask": round(ce + 0.25, 2),
                         "pe_bid": round(pe - 0.25, 2), "pe_ask": round(pe + 0.25, 2),
                         "ce_cum_volume": float(c[0]), "pe_cum_volume": float(c[1])})
    snaps = pd.DataFrame(rows)
    return bars, snaps
