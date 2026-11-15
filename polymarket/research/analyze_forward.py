import numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")
pd.set_option("display.width", 220)
d = pd.read_pickle("data/updown5m_live.pkl"); d = d[d.trades.map(len) >= 30].sort_values("start").reset_index(drop=True)
secs = np.arange(0, 300)
def prep(r):
    t = np.array([(x[0], x[2] if x[1] == 0 else 1 - x[2]) for x in r.trades], float)
    idx = np.searchsorted(t[:, 0], secs, side="right") - 1
    up = np.where(idx >= 0, t[np.clip(idx, 0, None), 1], np.nan); age = np.where(idx >= 0, secs - t[np.clip(idx, 0, None), 0], 999); up[age > 20] = np.nan
    ni = np.searchsorted(t[:, 0], secs, side="right"); ok = (ni < len(t)) & (t[np.clip(ni, 0, len(t)-1), 0] <= secs + 10)
    return up, np.where(ok, t[np.clip(ni, 0, len(t)-1), 1], np.nan)
P = {r.cid: (r, *prep(r)) for r in d.itertuples()}
def rule(T, lo, hi, minleft=20):
    out = []
    for cid, (r, up, nxt) in P.items():
        win = np.arange(300 - T, 300 - minleft)
        for side in (0, 1):
            p = up[win] if side == 0 else 1 - up[win]
            k = np.flatnonzero((p >= lo) & (p <= hi))
            if not len(k): continue
            s = win[k[0]]; fill = nxt[s] if side == 0 else 1 - nxt[s]
            if np.isnan(fill) or fill > p[k[0]] + .03 or fill >= .995: continue
            f = min(fill + .01, .999); won = r.won_up if side == 0 else 1 - r.won_up
            out.append((cid, r.coin, r.start, s, side, f, won, (won - f - .07*f*(1-f))/f)); break
    return pd.DataFrame(out, columns=["cid", "coin", "start", "sec", "side", "fill", "won", "ret"])
print("markets in forward-test window:", len(P), pd.to_datetime(d.start.min(), unit="s"), "->", pd.to_datetime(d.start.max(), unit="s"))
print("\n== BACKTEST METHOD on the same hours the live algos traded ==")
for name, T, lo, hi in (("3m  (<=180s, 70-98c)", 180, .70, .98), ("early (<=285s, 70-90c)", 285, .70, .90)):
    b = rule(T, lo, hi); print(f"{name}: n={len(b)} win={b.won.mean():.3f} avg_px={b.fill.mean():.3f} roi={b.ret.mean():+.3f}")
import json
_t = pd.DataFrame(json.load(open("data/forward_snapshot.json"))["trades"])
_f = _t[_t.kind == "fill"]; _s = _t[_t.kind == "settled"]
m = _s.merge(_f[["strategy", "cid", "outcome", "price", "t"]].rename(columns={"t": "t_buy", "price": "buy_px"}), on=["strategy", "cid", "outcome"], how="left")
m["win"] = (m.pnl > 0).astype(int); m["ret"] = m.pnl / m.cost
m = m[m.strategy.str.startswith("updown")].copy()
m["start"] = m.cid.map(lambda c: P[c][0].start if c in P else np.nan); m["coin"] = m.cid.map(lambda c: P[c][0].coin if c in P else None)
m["sec"] = m.t_buy - m.start; m["left"] = 300 - m.sec
print("\nlive updown bets:", len(m), "| matched to downloaded markets:", m.start.notna().sum())
m = m[m.start.notna()]
# what the print-based price was at the live entry second, and 5/15/30s later
def px_at(row, dt):
    up = P[row.cid][1]; s = int(min(max(row.sec + dt, 0), 299)); v = up[s]
    return v if row.outcome == 0 else 1 - v
for dt in (0, 5, 15, 30): m[f"px+{dt}"] = m.apply(lambda r: px_at(r, dt), axis=1)
print("\n== LIVE bets: what happened to the side's price right after entry ==")
g = m.groupby("strategy").agg(n=("win", "size"), win=("win", "mean"), buy=("buy_px", "mean"), print_at_entry=("px+0", "mean"), after5s=("px+5", "mean"), after15s=("px+15", "mean"), after30s=("px+30", "mean"))
print(g.round(3))
for col, bins in (("buy_px", [0, .705, .75, .8, .9, 1]), ("left", [0, 60, 120, 150, 181, 300])):
    m["b"] = pd.cut(m[col], bins)
    print(f"\n== LIVE by {col} =="); print(m.groupby(["strategy", "b"], observed=True).agg(n=("win", "size"), win=("win", "mean"), px=("buy_px", "mean"), pnl=("pnl", "sum"), roi=("ret", "mean")).round(3))
print("\n== LIVE by coin =="); print(m.groupby(["strategy", "coin"]).agg(n=("win", "size"), win=("win", "mean"), pnl=("pnl", "sum")).round(3))
m["hour"] = pd.to_datetime(m.t_buy, unit="s").dt.floor("2h")
print("\n== LIVE by time (UTC) =="); print(m.groupby("hour").agg(n=("win", "size"), win=("win", "mean"), pnl=("pnl", "sum")).round(3))
# same markets: did the backtest method take the same side, and how did it do there?
for name, T, lo, hi, strat in (("3m", 180, .70, .98, "updown_leader_3m"), ("early", 285, .70, .90, "updown_leader_early")):
    b = rule(T, lo, hi).set_index("cid"); l = m[m.strategy == strat].set_index("cid")
    j = l.join(b, rsuffix="_bt", how="left")
    both = j[j.won.notna()]
    print(f"\n== {name}: live bets {len(l)}, backtest also bet in {len(both)} of those markets; same side {(both.outcome == both.side).mean():.2f}; live win {both.win.mean():.3f} vs backtest win in the same markets {both.won.mean():.3f}; live entry sec {both.sec.median():.0f} vs bt {both.sec_bt.median():.0f}; live px {both.buy_px.mean():.3f} vs bt {both.fill.mean():.3f}")
    print(f"   backtest bets in markets live did NOT trade: n={len(b[~b.index.isin(l.index)])} win={b[~b.index.isin(l.index)].won.mean():.3f}")
m.drop(columns=["b"]).to_csv("data/forward_updown_matched.csv", index=False)
