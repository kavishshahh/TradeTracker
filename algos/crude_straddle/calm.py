"""Calm-market filters for the crude short straddle. Every measure is known before the 16:30 entry.

    python calm.py
"""
import pandas as pd

from backtest import Rules, load_days, run, summary

days = load_days()
pd.set_option("display.width", 250)
out = []
for exit_ in ("21:00", "23:00", "23:25"):
    t = run(days, Rules(exit=exit_))
    t["date"] = t.date.astype(str)
    t["evening_abs"] = t.move_pct.abs()
    t["prev5_evening"] = t.evening_abs.shift(1).rolling(5).mean()          # average size of the last 5 evenings' moves
    t["iv_median20"] = t.iv.shift(1).rolling(20).median()
    t["iv_prev"] = t.iv.shift(1)
    filters = {
        "all days": t.iv > 0,
        "iv < 35": t.iv < 35, "iv < 40": t.iv < 40, "iv < 50": t.iv < 50, "iv < 60": t.iv < 60,
        "iv below its 20-day median": t.iv < t.iv_median20,
        "last 5 evenings avg move < 1.0%": t.prev5_evening < 1.0,
        "last 5 evenings avg move < 1.5%": t.prev5_evening < 1.5,
        "today's move so far < 1%": t.day_move_pct.abs() < 1.0,
        "today's move so far < 2%": t.day_move_pct.abs() < 2.0,
        "iv < 50 and today < 1%": (t.iv < 50) & (t.day_move_pct.abs() < 1.0),
        "iv < 40 and last 5 evenings < 1.0%": (t.iv < 40) & (t.prev5_evening < 1.0),
        "5+ days to expiry": t.days_left >= 5,
        "iv < 40 and 5+ days to expiry": (t.iv < 40) & (t.days_left >= 5),
    }
    for name, mask in filters.items():
        part = t.loc[mask.fillna(False)]
        s = summary(part)
        y26 = part.loc[part.date >= "2026-01-01"]
        out.append({"exit": exit_, "filter": name, **{k: s.get(k) for k in ("days", "net", "avg", "win_pct", "worst", "max_dd", "gross", "sharpe")},
                    "days_2026": len(y26), "net_2026": int(y26.net.sum())})
    if exit_ == "23:00":
        t["month"] = t.date.str[:7]
        print(t.groupby("month").agg(days=("net", "size"), iv=("iv", "median"), evening=("evening_abs", "mean"), net=("net", "sum")).round(2).to_string())
print(pd.DataFrame(out).to_string(index=False))
