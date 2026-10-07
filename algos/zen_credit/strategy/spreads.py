"""Strike grid, ATM selection, expiry selection and spread construction."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np

from strategy.alpha2 import nearest_strike
from strategy.signals import Signal


@dataclass(frozen=True)
class SpreadLegs:
    option_type: str      # "PE" for bullish credit put spread, "CE" for bearish
    sell_strike: float
    buy_strike: float
    expiry: date


def strike_interval(strikes, around: float | None = None, band: int = 20) -> float:
    """Smallest positive spacing of the listed strike grid (optionally only the
    ``band`` strikes nearest ``around``, where the grid is densest)."""
    arr = np.unique(np.asarray(strikes, dtype=float))
    if around is not None and arr.size > band:
        arr = np.sort(arr[np.argsort(np.abs(arr - around))[:band]])
    diffs = np.diff(arr)
    diffs = diffs[diffs > 0]
    if diffs.size == 0:
        raise ValueError("cannot infer strike interval")
    return float(diffs.min())


def atm_strike(spot: float, strikes) -> float:
    """ATM = listed strike nearest to spot (tie -> lower)."""
    return nearest_strike(spot, strikes)


def select_expiry(trade_date: date, expiries: list[date]) -> date:
    """Nearest listed expiry on or after the trade date (same-day expiry included)."""
    future = sorted(e for e in expiries if e >= trade_date)
    if not future:
        raise ValueError("no expiry on/after trade date")
    return future[0]


def build_spread(signal: Signal, spot: float, strikes, expiry: date, distance: int) -> SpreadLegs:
    listed = set(float(s) for s in strikes)
    atm = atm_strike(spot, sorted(listed))
    if signal == Signal.BULLISH:
        legs = SpreadLegs("PE", atm, atm - distance, expiry)
    elif signal == Signal.BEARISH:
        legs = SpreadLegs("CE", atm, atm + distance, expiry)
    else:
        raise ValueError("no spread for Signal.NONE")
    if legs.buy_strike not in listed:
        raise ValueError(f"hedge strike {legs.buy_strike} not listed")
    return legs
