"""Crude short straddle by sessions left to option expiry (0 = expiry day). Expiry days are read off the
data: the session before the near-month series jumps to the next month.

    python expiry_week.py
"""
import pandas as pd

from backtest import Rules, load_days, run, summary

days = load_days()
pd.set_option("display.width", 250)


def with_sessions(t):
    t = t.reset_index(drop=True)
    t["date"] = t.date.astype(str)
    jump = t.days_left.shift(-1) > t.days_left + 10              # next session is a new, longer series
    cycle = jump.shift(1, fill_value=False).cumsum()
    t["cycle"] = cycle
    t["sessions_left"] = t.groupby("cycle").cumcount(ascending=False)
    t.loc[t.cycle.eq(t.cycle.max()), "sessions_left"] = 99        # current series: expiry not reached yet
    return t


if __name__ == "__main__":
    for exit_ in ("21:00", "23:00", "23:25"):
        t = with_sessions(run(days, Rules(exit=exit_)))
        rows = [{"sessions_left": k, **summary(g)} for k, g in t.loc[t.sessions_left < 99].groupby(t.sessions_left.clip(upper=8))]
        print("exit", exit_)
        print(pd.DataFrame(rows)[["sessions_left", "days", "net", "avg", "win_pct", "avg_win", "avg_loss", "worst", "gross"]].to_string(index=False))
        for n in (2, 3, 4, 5):
            part = t.loc[t.sessions_left < n]
            cyc = part.groupby("cycle").net.sum()
            y26 = part.loc[part.date >= "2026-01-01"]
            print(f"  last {n} sessions:", summary(part), "| cycles won", int((cyc > 0).sum()), "of", len(cyc), "| 2026 net", int(y26.net.sum()))
        if exit_ == "23:00":
            part = t.loc[t.sessions_left < 4]
            print(part.groupby("cycle").agg(first=("date", "min"), last=("date", "max"), days=("net", "size"), net=("net", "sum"), worst=("net", "min"), modelled=("modelled", "sum")).to_string())
