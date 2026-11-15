import numpy as np, pandas as pd, warnings, runpy, io, contextlib
warnings.filterwarnings("ignore"); pd.set_option("display.width", 220)
with contextlib.redirect_stdout(io.StringIO()): ns = runpy.run_path("analyze_forward.py")
P, rule, m = ns["P"], ns["rule"], ns["m"]
print(m.groupby("strategy")[["buy_px", "px+0", "px+5", "px+15", "px+30"]].mean().round(3))
live_t = np.sort(m.t_buy.values)
def active(start):  # was the live worker placing bets around this market's window?
    i = np.searchsorted(live_t, start); near = []
    if i < len(live_t): near.append(abs(live_t[i] - start))
    if i > 0: near.append(abs(live_t[i-1] - start))
    return min(near) < 900
for name, T, lo, hi, strat in (("3m", 180, .70, .98, "updown_leader_3m"), ("early", 285, .70, .90, "updown_leader_early")):
    b = rule(T, lo, hi); b["active"] = b.start.map(active)
    l = m[m.strategy == strat].set_index("cid")
    b["live_traded"] = b.cid.isin(l.index)
    b = b[b.active]
    print(f"\n=== {name}: backtest signals while the live worker was active: {len(b)}")
    print(b.groupby("live_traded").agg(n=("won", "size"), win=("won", "mean"), fill=("fill", "mean"), roi=("ret", "mean")).round(3))
    j = b.set_index("cid").join(l[["outcome", "buy_px", "sec", "win"]], rsuffix="_live", how="inner")
    print(f"same market, both bet: n={len(j)} same side {(j.outcome == j.side).mean():.2f} | bt win {j.won.mean():.3f} live win {j.win.mean():.3f} | bt entry sec {j.sec.median():.0f} live {j.sec_live.median():.0f} | bt fill {j.fill.mean():.3f} live {j.buy_px.mean():.3f}")
    # how fast was the price moving when the backtest "filled"? compare traded vs not traded
    def speed(r):
        up = P[r.cid][1]; s = int(r.sec); a = up[max(s-10, 0)]; c = up[s]
        if np.isnan(a) or np.isnan(c): return np.nan
        return (c - a) if r.side == 0 else (a - c)
    b["move10s"] = b.apply(speed, axis=1)
    b["fast"] = pd.cut(b.move10s, [-1, .02, .06, .12, 1], labels=["calm <2c", "2-6c", "6-12c", "jump >12c"])
    print(b.groupby("fast", observed=True).agg(n=("won", "size"), win=("won", "mean"), fill=("fill", "mean"), roi=("ret", "mean"), live_traded=("live_traded", "mean")).round(3))
