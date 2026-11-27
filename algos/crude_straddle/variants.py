"""Variations of the Crude Expiry Straddle on the sessions close to option expiry.

Varies entry and exit time, stops, a profit target, how far from the money the sold strikes are, and
bought hedges ("wings"). Prices outside Dhan's +/- 3 strike window are Black-76 estimates with the time to
expiry counted to 23:30 on expiry day.

    python variants.py            # run the grid, save variants.csv
"""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from datetime import datetime, time as dtime, timedelta

import numpy as np
import pandas as pd

from backtest import STORE, Rules, charges, load_days, run
from expiry_week import with_sessions
from forward import trade_dates

STEP = 50
_erf = np.vectorize(math.erf)


def black76(future, strike, vol, years, call):
    sd = np.maximum(vol * np.sqrt(np.maximum(years, 1e-9)), 1e-9)
    d1 = (np.log(future / strike) + 0.5 * sd * sd) / sd
    d2 = d1 - sd
    cdf = lambda x: 0.5 * (1 + _erf(x / math.sqrt(2)))
    return future * cdf(d1) - strike * cdf(d2) if call else strike * cdf(-d2) - future * cdf(-d1)


class Session:
    """One day on a full minute grid, with fixed-strike leg prices cached."""

    def __init__(self, day, expiry):
        self.date, self.expiry, self.day = day.date, expiry, day
        first = min(day.table[s]["close"].index[0] for s in ("CE", "PE"))
        last = max(day.table[s]["close"].index[-1] for s in ("CE", "PE"))
        self.grid = pd.date_range(first, last, freq="1min")
        self.spot = day.spot.reindex(self.grid).ffill().bfill().to_numpy()
        end = datetime.combine(expiry, dtime(23, 30))
        self.years = np.maximum((end - self.grid.to_pydatetime()) / timedelta(days=365), 1e-6).astype(float)
        self._legs = {}

    def index(self, hhmm):
        h, m = map(int, hhmm.split(":"))
        when = pd.Timestamp.combine(self.date, dtime(h, m))
        return int(self.grid.get_indexer([when])[0])

    def leg(self, side, strike, bound="upper"):
        """open (real only), open, high, close and a missing-minute mask for a fixed strike.

        Minutes where the strike is outside Dhan's window are not estimated by formula in the default
        modes. They are bounded from real quotes of the nearest strike still in the window:
        ``upper`` (for sold legs) is the most the option can be worth, ``lower`` (for bought legs) the
        least, so the result errs against the strategy. ``model`` uses Black-76 instead."""
        key = (side, strike, bound)
        if key not in self._legs:
            t = self.day.table[side]
            if strike in t["close"].columns:
                raw_open = t["open"][strike].reindex(self.grid).to_numpy(dtype=float)
                high = t["high"][strike].reindex(self.grid).to_numpy(dtype=float)
                close = t["close"][strike].reindex(self.grid).to_numpy(dtype=float)
            else:
                raw_open = high = close = np.full(len(self.grid), np.nan)
            missing = np.isnan(close)
            opened = raw_open.copy()
            if missing.any():
                # Bounds use only strikes quoted in that same minute; a strike's last price is never carried forward.
                source = t["iv"].reindex(self.grid).ffill().bfill() if bound == "model" else t["close"].reindex(self.grid)
                strikes = source.columns.to_numpy(dtype=float)
                values = source.to_numpy(dtype=float)
                distance = np.where(np.isnan(values), np.inf, np.abs(strikes - strike)[None, :])
                pick = distance.argmin(axis=1)
                edge_value = values[np.arange(len(values)), pick]
                edge_strike = strikes[pick]
                if bound == "model":
                    estimate = black76(self.spot, strike, np.where(np.nan_to_num(edge_value) > 0, edge_value, 50.0) / 100, self.years, side == "CE")
                else:
                    deeper = (edge_strike - strike) if side == "CE" else (strike - edge_strike)     # > 0: our strike is further in the money
                    estimate = edge_value + np.maximum(deeper, 0) if bound == "upper" else np.where(deeper > 0, edge_value, 0.0)
                estimate = pd.Series(np.where(missing, estimate, close)).ffill().bfill().to_numpy()   # a minute with no quotes at all
                close = np.where(missing, estimate, close)
                high = np.where(missing, estimate, high)
                opened = np.where(np.isnan(opened), close, opened)
            self._legs[key] = (raw_open, opened, high, close, missing)
        return self._legs[key]


@dataclass(frozen=True)
class Spec:
    entry: str = "16:30"
    exit: str = "23:00"
    width: int = 0                 # sold strikes this many steps out of the money (0 = straddle)
    wing: int | None = None        # bought hedges this many steps beyond the sold strikes
    leg_sl: float | None = None
    combined_sl: float | None = None
    target: float | None = None    # 0.5 = close when half the credit is earned
    slippage: float = 0.5
    lot: int = 100
    pricing: str = "bound"       # "bound": real-quote bounds against the strategy; "model": Black-76


def simulate(s: Session, spec: Spec):
    i0, i1 = s.index(spec.entry), s.index(spec.exit)
    if i0 < 0:
        return None
    if i1 < 0:
        i1 = len(s.grid) - 1
        if s.grid[i1] < pd.Timestamp.combine(s.date, dtime(*map(int, spec.exit.split(":")))) - pd.Timedelta(minutes=15):
            return None
    if i1 <= i0:
        return None
    call_open = s.day.table["CE"]["open"].reindex([s.grid[i0]]).iloc[0]
    put_open = s.day.table["PE"]["open"].reindex([s.grid[i0]]).iloc[0]
    gap = (call_open - put_open).dropna()
    if gap.empty:
        return None
    future = float((gap + gap.index.values).median())
    atm = round(future / STEP) * STEP
    legs = [("CE", atm + spec.width * STEP, -1), ("PE", atm - spec.width * STEP, -1)]
    if spec.wing:
        legs += [("CE", atm + (spec.width + spec.wing) * STEP, 1), ("PE", atm - (spec.width + spec.wing) * STEP, 1)]
    data, entry_price = [], []
    for side, strike, sign in legs:
        bound = "model" if spec.pricing == "model" else ("upper" if sign < 0 else "lower")
        raw_open, opened, high, close, missing = s.leg(side, float(strike), bound)
        if np.isnan(raw_open[i0]) or raw_open[i0] <= 0:
            return None                                   # no real quote at entry
        data.append((opened, high, close, missing))
        entry_price.append(float(raw_open[i0]))
    exit_price = [None] * len(legs)
    exit_at = [i1] * len(legs)
    if spec.leg_sl is not None:
        for k in (0, 1):
            opened, high, close, _ = data[k]
            level = entry_price[k] * (1 + spec.leg_sl)
            hits = np.nonzero(high[i0 + 1:i1 + 1] >= level)[0]
            if len(hits):
                j = i0 + 1 + int(hits[0])
                exit_price[k], exit_at[k] = max(level, float(opened[j])), j
                if spec.wing:
                    exit_price[k + 2], exit_at[k + 2] = float(data[k + 2][2][j]), j
    elif spec.combined_sl is not None or spec.target is not None:
        value = sum(-sign * data[k][2][i0 + 1:i1 + 1] for k, (_, _, sign) in enumerate(legs))
        credit = sum(-sign * entry_price[k] for k, (_, _, sign) in enumerate(legs))
        hit = np.zeros(len(value), dtype=bool)
        if spec.combined_sl is not None:
            hit |= value >= credit * (1 + spec.combined_sl)
        if spec.target is not None:
            hit |= value <= credit * (1 - spec.target)
        hits = np.nonzero(hit)[0]
        if len(hits):
            j = i0 + 1 + int(hits[0])
            for k in range(len(legs)):
                exit_price[k], exit_at[k] = float(data[k][2][j]), j
    sold = bought = 0.0
    modelled = 0
    for k, (_, _, sign) in enumerate(legs):
        if exit_price[k] is None:
            exit_price[k] = float(data[k][2][i1])
        modelled += int(data[k][3][i0:exit_at[k] + 1].sum())
        if sign < 0:
            sold += entry_price[k]
            bought += exit_price[k]
        else:
            bought += entry_price[k]
            sold += exit_price[k]
    gross = (sold - bought) * spec.lot
    cost = charges(sold * spec.lot, bought * spec.lot, 2 * len(legs)) + spec.slippage * 2 * len(legs) * spec.lot
    return {"date": s.date, "future": future, "credit": round(sum(-g * entry_price[k] for k, (_, _, g) in enumerate(legs)), 1),
            "gross": gross, "net": gross - cost, "modelled": modelled, "minutes": (i1 - i0 + 1) * len(legs),
            "stopped": any(e < i1 for e in exit_at), "move_pct": round((s.spot[i1] / future - 1) * 100, 2),
            "strike": float(atm), "entry_time": s.grid[i0], "exit_time": s.grid[max(exit_at)],
            "legs": [{"side": side, "strike": float(strike), "sold": sign < 0, "entry": round(entry_price[k], 2), "exit": round(exit_price[k], 2)}
                     for k, (side, strike, sign) in enumerate(legs)]}


def sessions(max_left=5):
    days = load_days()
    base = with_sessions(run(days, Rules()))
    past = sorted(pd.to_datetime(base.loc[base.sessions_left.eq(0), "date"]).dt.date)
    plan = trade_dates(past, count=max_left)
    out = [(Session(d, plan[d.date][0]), plan[d.date][1], plan[d.date][0]) for d in days if d.date in plan]
    return out


def stats(frame):
    net = frame.net
    equity = net.cumsum()
    by_cycle = frame.groupby("expiry").net.sum()
    return {"days": len(net), "net": int(net.sum()), "avg": int(net.mean()), "win_pct": round(100 * (net > 0).mean(), 1),
            "worst": int(net.min()), "max_dd": int((equity - np.maximum(equity.cummax(), 0)).min()),
            "cycles_won": int((by_cycle > 0).sum()), "cycles": len(by_cycle), "worst_cycle": int(by_cycle.min()),
            "sharpe": round(net.mean() / net.std() * math.sqrt(len(net) / 1.3), 2) if net.std() > 0 else 0.0,
            "modelled_pct": round(100 * frame.modelled.sum() / frame.minutes.sum(), 1)}


def evaluate(pool, spec, keep=(0, 1, 2)):
    rows = []
    for session, left, expiry in pool:
        if left in keep:
            r = simulate(session, spec)
            if r:
                rows.append({**r, "left": left, "expiry": expiry})
    return pd.DataFrame(rows)


# Bought wings are left out: they sit at the edge of Dhan's +/- 3 strike window, so their exit prices are
# almost never observed, and Dhan's margin calculator gives them no margin relief on MCX.
STRUCTURES = {"straddle": (0, None), "strangle 1 out": (1, None), "strangle 2 out": (2, None)}
STOPS = {"none": {}, "leg 30%": {"leg_sl": 0.3}, "leg 50%": {"leg_sl": 0.5}, "leg 100%": {"leg_sl": 1.0},
         "both 25%": {"combined_sl": 0.25}, "both 50%": {"combined_sl": 0.5}, "target 50%": {"target": 0.5},
         "target 50% + both 50%": {"target": 0.5, "combined_sl": 0.5}}
ENTRIES = ("09:30", "12:00", "14:30", "15:30", "16:30", "17:30", "18:30", "19:30", "20:30")
EXITS = ("19:00", "20:00", "21:00", "22:00", "23:00", "23:25")
WINDOWS = {"last 2": (0, 1), "last 3": (0, 1, 2), "last 4": (0, 1, 2, 3), "last 3, not expiry day": (1, 2, 3), "2 before expiry day": (1, 2)}

if __name__ == "__main__":
    pool = sessions()
    out = []
    for entry, exit_, (sname, (width, wing)), (stop, extra) in itertools.product(ENTRIES, EXITS, STRUCTURES.items(), STOPS.items()):
        if exit_ <= entry:
            continue
        spec = Spec(entry=entry, exit=exit_, width=width, wing=wing, **extra)
        frame = evaluate(pool, spec, keep=(0, 1, 2, 3, 4))
        if frame.empty:
            continue
        for wname, keep in WINDOWS.items():
            part = frame.loc[frame.left.isin(keep)]
            if len(part) >= 20:
                out.append({"entry": entry, "exit": exit_, "structure": sname, "stop": stop, "window": wname, **stats(part)})
    table = pd.DataFrame(out)
    table.to_csv(STORE / "variants.csv", index=False)
    pd.set_option("display.width", 250)
    print(len(table), "variants; net positive:", int((table.net > 0).sum()))
    print(table.sort_values("net", ascending=False).head(25).to_string(index=False))
