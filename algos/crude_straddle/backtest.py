"""MCX crude oil intraday short straddle: sell the at-the-money call and put at a fixed time, buy back later.

Data: per-day files from download_rolling.py (Dhan's near-month series, at-the-money +/- 3 strikes, 1-minute
bars, futures price in ``spot``). Prices are rupees per barrel; one CRUDEOIL lot is 100 barrels.

A sold strike leaves the +/- 3 window when the future moves about 175 points away. Those minutes are priced
with Black-76 from the implied volatility of the nearest strike still in the window (``modelled`` column).

    python backtest.py                      # 16:30 to 23:00, no stop
    python backtest.py --leg-sl 0.3 --grid
"""
from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from datetime import time as dtime
from pathlib import Path

import numpy as np
import pandas as pd

STORE = Path(__file__).resolve().parents[1] / "data" / "mcx_crude"


@dataclass(frozen=True)
class Rules:
    entry: str = "16:30"
    exit: str = "23:00"
    leg_sl: float | None = None        # 0.3 = buy a leg back when it trades 30% above its sale price
    combined_sl: float | None = None   # 0.2 = close both when call + put is 20% above the premium collected
    stop_on: str = "high"              # "high" (any trade in the minute) or "close"
    slippage: float = 0.5              # rupees per barrel, each fill
    lot: int = 100
    min_days_left: float = 0.0         # skip days with fewer implied calendar days to expiry than this


def charges(sell_value, buy_value, orders):
    """Approximate MCX option costs in rupees: Rs 20 an order, exchange fee 0.0418% of premium, commodity
    transaction tax 0.05% on premium sold, stamp duty 0.003% on premium bought, 18% GST on fees."""
    brokerage = 20.0 * orders
    exchange = 0.000418 * (sell_value + buy_value)
    return brokerage + exchange + 0.0005 * sell_value + 0.00003 * buy_value + 0.18 * (brokerage + exchange)


def _cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def black76(future, strike, vol, years, call):
    if vol <= 0 or years <= 0:
        return max(future - strike, 0.0) if call else max(strike - future, 0.0)
    sd = vol * math.sqrt(years)
    d1 = (math.log(future / strike) + 0.5 * sd * sd) / sd
    d2 = d1 - sd
    return future * _cdf(d1) - strike * _cdf(d2) if call else strike * _cdf(-d2) - future * _cdf(-d1)


class Day:
    """One session: price tables by (minute, strike) for calls and puts, and the futures price by minute."""

    def __init__(self, path):
        raw = pd.read_csv(path, parse_dates=["time"])
        self.date = raw.time.iloc[0].date()
        raw = raw.drop_duplicates(["time", "side", "strike"])
        self.quoted = raw.loc[raw.offset.eq(0)].groupby("time").spot.first().sort_index()
        self.table = {}
        for side in ("CE", "PE"):
            part = raw.loc[raw.side.eq(side)]
            self.table[side] = {f: part.pivot(index="time", columns="strike", values=f).sort_index() for f in ("open", "high", "close", "iv")}
        # The future these options settle on, from put-call parity (strike + call - put, median over strikes).
        # Dhan's ``spot`` is the front future, which is a different contract between option and futures expiry.
        call, put = self.table["CE"]["close"], self.table["PE"]["close"]
        common = call.columns.intersection(put.columns)
        parity = (call[common] - put[common].reindex(call.index)).add(pd.Series(common, index=common), axis=1).median(axis=1)
        self.spot = parity.dropna().sort_index()
        self.basis = float((self.spot - self.quoted.reindex(self.spot.index)).median()) if len(self.spot) else 0.0

    def leg(self, side, strike, minutes, years):
        """open, high, close for a fixed strike over ``minutes``; gaps filled by Black-76. Returns the
        three series and the number of modelled minutes."""
        t = self.table[side]
        if strike in t["close"].columns:
            o, h, c = (t[f][strike].reindex(minutes) for f in ("open", "high", "close"))
        else:
            o = h = c = pd.Series(np.nan, index=minutes)
        missing = c.isna()
        if missing.any():
            iv = t["iv"].reindex(minutes).ffill()
            strikes = np.array(iv.columns, dtype=float)
            spot = self.spot.reindex(minutes).ffill().bfill()
            o, h, c = o.copy(), h.copy(), c.copy()
            for when in minutes[missing.values]:
                row = iv.loc[when].dropna()
                if row.empty or pd.isna(spot.loc[when]):
                    continue
                nearest = row.index[np.abs(np.array(row.index, dtype=float) - strike).argmin()]
                price = black76(float(spot.loc[when]), strike, float(row[nearest]) / 100, years, side == "CE")
                o.loc[when] = h.loc[when] = c.loc[when] = price
        return o, h, c.ffill(), int(missing.sum())


def run(days, rules: Rules):
    eh, em = map(int, rules.entry.split(":"))
    xh, xm = map(int, rules.exit.split(":"))
    rows = []
    for day in days:
        t0 = pd.Timestamp.combine(day.date, dtime(eh, em))
        t1 = pd.Timestamp.combine(day.date, dtime(xh, xm))
        if t0 not in day.spot.index or day.spot.index[-1] < t1 - pd.Timedelta(minutes=10):
            continue                                                    # no bar at entry, or a short session
        if t0 not in day.table["CE"]["open"].index or t0 not in day.table["PE"]["open"].index:
            continue
        gap = (day.table["CE"]["open"].loc[t0] - day.table["PE"]["open"].loc[t0]).dropna()
        future = float((gap + gap.index.values).median()) if len(gap) else float("nan")
        if pd.isna(future):
            continue
        strike = float(round(future / 50) * 50)
        try:
            sold = {s: float(day.table[s]["open"].at[t0, strike]) for s in ("CE", "PE")}
            vol = float(day.table["CE"]["iv"].at[t0, strike]) / 100
        except KeyError:
            continue
        if any(pd.isna(v) or v <= 0 for v in sold.values()) or not vol > 0:
            continue
        years = ((sold["CE"] + sold["PE"]) / (0.8 * future * vol)) ** 2     # from the at-the-money straddle
        if years * 365 < rules.min_days_left:
            continue
        minutes = pd.date_range(t0, t1, freq="1min")
        legs, modelled = {}, 0
        for side in ("CE", "PE"):
            o, h, c, n = day.leg(side, strike, minutes, years)
            legs[side] = (o, h, c)
            modelled += n
        bought, reason = {}, {}
        if rules.leg_sl is not None:
            for side, (o, h, c) in legs.items():
                level = sold[side] * (1 + rules.leg_sl)
                trigger = (h if rules.stop_on == "high" else c).iloc[1:]
                hit = trigger >= level
                if hit.any():
                    when = hit.idxmax()
                    opened = o.loc[when]
                    bought[side] = max(level, float(opened)) if rules.stop_on == "high" and not pd.isna(opened) else float(c.loc[when])
                    reason[side] = f"stop {when:%H:%M}"
        if rules.combined_sl is not None and not bought:
            total = legs["CE"][2] + legs["PE"][2]
            hit = total.iloc[1:] >= (sold["CE"] + sold["PE"]) * (1 + rules.combined_sl)
            if hit.any():
                when = hit.idxmax()
                for side in legs:
                    bought[side] = float(legs[side][2].loc[when])
                    reason[side] = f"stop {when:%H:%M}"
        for side in legs:
            if side not in bought:
                bought[side] = float(legs[side][2].iloc[-1])
                reason[side] = "time"
        if any(pd.isna(v) for v in bought.values()):
            continue
        sell_value = sum(sold.values()) * rules.lot
        buy_value = sum(bought.values()) * rules.lot
        gross = sell_value - buy_value
        slip = rules.slippage * 4 * rules.lot
        cost = charges(sell_value, buy_value, 4)
        end = day.spot.reindex(minutes).ffill().iloc[-1]
        rows.append({"date": day.date, "basis": round(day.basis), "days_left": round(years * 365, 1), "iv": round(vol * 100, 1),
                     "day_move_pct": round((future / float(day.spot.iloc[0]) - 1) * 100, 2), "future": future, "strike": strike,
                     "call_sold": sold["CE"], "put_sold": sold["PE"], "call_bought": round(bought["CE"], 1), "put_bought": round(bought["PE"], 1),
                     "call_exit": reason["CE"], "put_exit": reason["PE"], "move_pct": round((end / future - 1) * 100, 2),
                     "modelled": modelled, "gross": round(gross), "slippage": round(slip), "charges": round(cost),
                     "net": round(gross - slip - cost)})
    return pd.DataFrame(rows)


def summary(trades):
    if trades.empty:
        return {"days": 0}
    net = trades.net
    equity = net.cumsum()
    drawdown = equity - np.maximum(equity.cummax(), 0)
    wins, losses = net[net > 0], net[net <= 0]
    return {"days": len(net), "net": int(net.sum()), "avg": int(net.mean()), "win_pct": round(100 * (net > 0).mean(), 1),
            "avg_win": int(wins.mean()) if len(wins) else 0, "avg_loss": int(losses.mean()) if len(losses) else 0,
            "best": int(net.max()), "worst": int(net.min()), "max_dd": int(drawdown.min()),
            "gross": int(trades.gross.sum()), "costs": int((trades.slippage + trades.charges).sum()),
            "sharpe": round(net.mean() / net.std() * math.sqrt(250), 2) if net.std() > 0 else 0.0}


def load_days(symbol="CRUDEOIL"):
    return [Day(p) for p in sorted((STORE / f"rolling_{symbol}").glob("*.csv.gz")) if p.stat().st_size > 200]


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--entry", default="16:30")
    p.add_argument("--exit", default="23:00")
    p.add_argument("--leg-sl", type=float)
    p.add_argument("--combined-sl", type=float)
    p.add_argument("--stop-on", default="high", choices=["high", "close"])
    p.add_argument("--slippage", type=float, default=0.5)
    p.add_argument("--min-days-left", type=float, default=0.0)
    p.add_argument("--symbol", default="CRUDEOIL")
    p.add_argument("--grid", action="store_true")
    p.add_argument("--out")
    a = p.parse_args()
    days = load_days(a.symbol)
    lot = 10 if a.symbol == "CRUDEOILM" else 100
    base = Rules(a.entry, a.exit, a.leg_sl, a.combined_sl, a.stop_on, a.slippage, lot, a.min_days_left)
    trades = run(days, base)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_rows", 500)
    print(trades.to_string(index=False))
    print(summary(trades))
    if a.out:
        trades.to_csv(a.out, index=False)
    if a.grid:
        out = []
        for entry in ("10:00", "14:30", "16:30", "17:30", "18:30", "20:00"):
            for exit_ in ("19:00", "21:00", "23:00", "23:25"):
                if exit_ <= entry:
                    continue
                for label, leg, comb in (("none", None, None), ("leg 30%", 0.3, None), ("leg 50%", 0.5, None), ("both 20%", None, 0.2)):
                    r = Rules(entry, exit_, leg, comb, a.stop_on, a.slippage, lot, a.min_days_left)
                    out.append({"entry": entry, "exit": exit_, "stop": label, **summary(run(days, r))})
        print(pd.DataFrame(out).to_string(index=False))
