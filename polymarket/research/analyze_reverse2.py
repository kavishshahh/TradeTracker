"""Leader vs fade on the trade tape, without trusting the order of prints inside one second
(the saved tape is sorted, so that order is not chronological - the earlier backtest relied on it
and bought at the cheapest print of the next second, which made it look profitable).
Signal: the size-weighted average price of a second puts one side at lo..hi with 20..T s left.
Fill: next second that has trades (within 10 s): 'avg' = its size-weighted average, 'worst' = its worst print."""
import numpy as np, pandas as pd
pd.set_option("display.width", 220); FEE = .07
def load(path):
    d = pd.read_pickle(path); return d[d.trades.map(len) >= 30].sort_values("start").reset_index(drop=True)
def per_second(r):
    t = pd.DataFrame([(x[0], x[2] if x[1] == 0 else 1 - x[2], x[3]) for x in r.trades], columns=["s", "up", "sz"])
    t["w"] = t.up * t.sz; g = t.groupby("s")
    return pd.DataFrame(dict(avg=g.w.sum() / g.sz.sum(), lo=g.up.min(), hi=g.up.max())).reset_index().values
def ret(won, f): return (won - f - FEE * f * (1 - f)) / f
def signals(d, T, lo, hi, minleft=20):
    out = []
    for r in d.itertuples():
        a = per_second(r)
        for i in range(len(a) - 1):
            s, up = a[i, 0], a[i, 1]
            if not (300 - T <= s <= 300 - minleft): continue
            side = 0 if lo <= up <= hi else 1 if lo <= 1 - up <= hi else None
            if side is None: continue
            ns, navg, nlo, nhi = a[i + 1]
            if ns - s > 10: break
            sig = up if side == 0 else 1 - up
            p_avg = navg if side == 0 else 1 - navg; p_worst = nhi if side == 0 else 1 - nlo; p_best = nlo if side == 0 else 1 - nhi
            if p_avg > sig + .03 or p_avg >= .98: break
            won = r.won_up if side == 0 else 1 - r.won_up
            out.append(dict(cid=r.cid, coin=r.coin, start=r.start, p=p_avg, won=won,
                            lead_avg=ret(won, min(p_avg + .01, .99)), lead_worst=ret(won, min(p_worst + .01, .99)),
                            fade_avg=ret(1 - won, min(1 - p_avg + .01, .99)), fade_worst=ret(1 - won, min(1 - p_best + .01, .99))))
            break
    return pd.DataFrame(out)
def show(name, b):
    t = lambda c: b[c].mean() / (b[c].std() / len(b) ** .5)
    print(f"{name:26s} n={len(b):5d} leader won {b.won.mean():.3f} at {b.p.mean():.3f} | leader avg {b.lead_avg.mean():+.3f} (t {t('lead_avg'):+.1f}) worst {b.lead_worst.mean():+.3f} | fade avg {b.fade_avg.mean():+.3f} (t {t('fade_avg'):+.1f}) worst {b.fade_worst.mean():+.3f}")
if __name__ == "__main__":
    for label, path in (("6 days 8-14 Nov", "data/updown5m.pkl"), ("14-15 Nov", "data/updown5m_live.pkl"), ("last 15h", "data/updown5m_v2.pkl")):
        d = load(path); print(f"\n=== {label}: {len(d)} markets")
        for T in (180, 285):
            show(f"<={T}s, 70-90c", signals(d, T, .70, .90))
            for lo, hi in ((.70, .80), (.80, .90), (.90, .97)):
                show(f"   {lo:.2f}-{hi:.2f}", signals(d, T, lo, hi))
        if "updown5m.pkl" in path:
            b = signals(d, 180, .70, .90); b["day"] = pd.to_datetime(b.start, unit="s").dt.date
            print(b.groupby("day").agg(n=("won", "size"), won=("won", "mean"), p=("p", "mean"), lead=("lead_avg", "mean"), fade=("fade_avg", "mean")).round(3))
            print(b.groupby("coin").agg(n=("won", "size"), won=("won", "mean"), p=("p", "mean"), lead=("lead_avg", "mean"), fade=("fade_avg", "mean")).round(3))
