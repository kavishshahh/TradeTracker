"""Would betting the other side have paid? Uses the full trade tape, not our fills.
For each market: the first print of a side at lo..hi with 20..T seconds left = 'leader signal'.
Leader buys at next print + 1c; the fade buys the other side at (1 - next print) + 1c. Both pay the 7% fee curve."""
import sys, json, numpy as np, pandas as pd
pd.set_option("display.width", 220)
FEE = .07
def load(path):
    d = pd.read_pickle(path); return d[d.trades.map(len) >= 30].sort_values("start").reset_index(drop=True)
def signals(d, T, lo, hi, minleft=20):
    out = []
    for r in d.itertuples():
        t = [(x[0], x[2] if x[1] == 0 else 1 - x[2]) for x in r.trades]
        for i, (s, up) in enumerate(t[:-1]):
            if not (300 - T <= s <= 300 - minleft): continue
            side = 0 if lo <= up <= hi else 1 if lo <= 1 - up <= hi else None
            if side is None: continue
            ns, nup = t[i + 1]
            if ns - s > 10: continue
            p = nup if side == 0 else 1 - nup                 # leader's price at the next print
            if p > (up if side == 0 else 1 - up) + .03 or p >= .98 or p <= .5: continue
            won = r.won_up if side == 0 else 1 - r.won_up
            lf, ff = min(p + .01, .99), min(1 - p + .01, .99)
            out.append(dict(cid=r.cid, coin=r.coin, start=r.start, sec=s, p=p, won=won,
                            lead=(won - lf - FEE * lf * (1 - lf)) / lf, fade=((1 - won) - ff - FEE * ff * (1 - ff)) / ff))
            break
    return pd.DataFrame(out)
def show(name, b):
    if not len(b): print(name, "no signals"); return
    se = b.fade.std() / len(b) ** .5
    print(f"{name:34s} n={len(b):5d} leader won {b.won.mean():.3f} at {b.p.mean():.3f} | leader {b.lead.mean():+.3f}/bet | fade {b.fade.mean():+.3f}/bet (t {b.fade.mean()/se:+.1f})")
for label, path in (("6 days 8-14 Nov", "data/updown5m.pkl"), ("14-15 Nov (v1 hours)", "data/updown5m_live.pkl"), ("last 15h (v2 hours)", "data/updown5m_v2.pkl")):
    d = load(path); print(f"\n=== {label}: {len(d)} markets")
    for T in (180, 285):
        b = signals(d, T, .70, .90); show(f"<= {T}s left, 70-90c", b)
        for lo, hi in ((.70, .75), (.75, .80), (.80, .85), (.85, .90)):
            show(f"   first print {lo:.2f}-{hi:.2f}", signals(d, T, lo, hi))
    if "v2" in path:
        b = signals(d, 180, .70, .90); b["hour"] = pd.to_datetime(b.start, unit="s").dt.floor("3h")
        print(b.groupby("hour").agg(n=("won", "size"), leader_won=("won", "mean"), p=("p", "mean"), fade=("fade", "mean")).round(3))
        # our own v2 bets on the same tape
        rows = pd.DataFrame(json.load(open("data/forward_snapshot2.json")))
        rows = rows[(rows.version == 2) & rows.strategy.str.startswith("updown")]
        f, s = rows[rows.kind == "fill"], rows[rows.kind == "settled"]
        m = s.merge(f[["strategy", "cid", "outcome", "price", "t"]].rename(columns={"price": "buy", "t": "t_buy"}), on=["strategy", "cid", "outcome"])
        m["win"] = m.pnl > 0
        for strat, T in (("updown_leader_3m", 180), ("updown_leader_early", 285)):
            l = m[m.strategy == strat]; bt = signals(d, T, .70, .90).set_index("cid")
            j = l.set_index("cid").join(bt, how="inner", rsuffix="_bt")
            print(f"{strat}: live {len(l)} bets won {l.win.mean():.3f} at {l.buy.mean():.3f} | same markets on tape: n={len(j)} tape-rule won {j.won.mean():.3f} at {j.p.mean():.3f}, live won {j.win.mean():.3f}; tape signals in markets live skipped: n={len(bt[~bt.index.isin(l.cid)])} won {bt[~bt.index.isin(l.cid)].won.mean():.3f}")
