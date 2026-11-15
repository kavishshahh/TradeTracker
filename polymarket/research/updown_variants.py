import numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore"); pd.set_option("display.width", 220)
secs = np.arange(0, 300)
def prep(r):
    t = np.array([(x[0], x[2] if x[1] == 0 else 1 - x[2]) for x in r.trades], float)
    idx = np.searchsorted(t[:, 0], secs, side="right") - 1
    up = np.where(idx >= 0, t[np.clip(idx, 0, None), 1], np.nan); age = np.where(idx >= 0, secs - t[np.clip(idx, 0, None), 0], 999); up[age > 20] = np.nan
    ni = np.searchsorted(t[:, 0], secs, side="right"); ok = (ni < len(t)) & (t[np.clip(ni, 0, len(t)-1), 0] <= secs + 10)
    return up, np.where(ok, t[np.clip(ni, 0, len(t)-1), 1], np.nan)
def load(path):
    d = pd.read_pickle(path); d = d[d.trades.map(len) >= 30].sort_values("start")
    return [(r, *prep(r)) for r in d.itertuples()]
OLD, NEW = load("data/updown5m.pkl"), load("data/updown5m_live.pkl")
def rule(rows, T, lo, hi, persist=0, coins=("btc", "eth"), minleft=20, slip=.01):
    out = []
    for r, up, nxt in rows:
        if r.coin not in coins: continue
        win = np.arange(max(300 - T, persist), 300 - minleft)
        for side in (0, 1):
            q = up if side == 0 else 1 - up
            hit = (q[win] >= lo) & (q[win] <= hi)
            for back in range(5, persist + 1, 5):          # the side must have been >= lo for the whole last `persist` seconds
                hit &= q[win - back] >= lo
            k = np.flatnonzero(hit)
            if not len(k): continue
            s = win[k[0]]; fill = nxt[s] if side == 0 else 1 - nxt[s]
            if np.isnan(fill) or fill > q[s] + .03 or fill >= .995: continue
            f = min(fill + slip, .999); won = r.won_up if side == 0 else 1 - r.won_up
            out.append((r.start, r.coin, s, f, won, (won - f - .07*f*(1-f))/f)); break
    return pd.DataFrame(out, columns=["start", "coin", "sec", "fill", "won", "ret"])
def st(b):
    if len(b) < 5: return f"n={len(b)}"
    return f"n={len(b):4d} win={b.won.mean():.3f} px={b.fill.mean():.3f} roi={b.ret.mean():+.3f} t={b.ret.mean()/(b.ret.std(ddof=1)/np.sqrt(len(b))):+.1f}"
print("== How unusual is a bad run? 6-day backtest, rule '3m 70-98c': win rate over every run of 50 consecutive bets ==")
b = rule(OLD, 180, .70, .98).sort_values("start"); w = b.won.rolling(50).mean().dropna()
print(f"runs: {len(w)} | median {w.median():.2f} | worst {w.min():.2f} | share of runs at or below 66%: {(w <= .66).mean():.3%} | at or below 74%: {(w <= .74).mean():.1%}")
r50 = b.ret.rolling(50).sum().dropna(); print(f"sum of returns over 50 bets ($1 stakes): median {r50.median():+.1f}, worst {r50.min():+.1f}, share negative {(r50 < 0).mean():.1%}")
print("\n== Variants: 6-day set (3,442 markets) | fresh day (360 markets, never used for tuning) ==")
V = [("current 3m: <=180s, 70-98c", dict(T=180, lo=.70, hi=.98)),
     ("current early: <=285s, 70-90c", dict(T=285, lo=.70, hi=.90)),
     ("+ held 10s", dict(T=285, lo=.70, hi=.90, persist=10)),
     ("+ held 20s", dict(T=285, lo=.70, hi=.90, persist=20)),
     ("+ held 30s", dict(T=285, lo=.70, hi=.90, persist=30)),
     ("72-90c", dict(T=285, lo=.72, hi=.90)),
     ("72-90c held 20s", dict(T=285, lo=.72, hi=.90, persist=20)),
     ("75-90c", dict(T=285, lo=.75, hi=.90)),
     ("75-90c held 20s", dict(T=285, lo=.75, hi=.90, persist=20)),
     ("70-85c held 20s", dict(T=285, lo=.70, hi=.85, persist=20)),
     ("3m 70-90c held 20s", dict(T=180, lo=.70, hi=.90, persist=20)),
     ("BTC only: 70-90c held 20s", dict(T=285, lo=.70, hi=.90, persist=20, coins=("btc",))),
     ("ETH only: 70-90c held 20s", dict(T=285, lo=.70, hi=.90, persist=20, coins=("eth",))),
     ("early 70-90c held 20s, +3c slippage", dict(T=285, lo=.70, hi=.90, persist=20, slip=.03))]
for name, kw in V:
    print(f"{name:38s} | {st(rule(OLD, **kw))} | {st(rule(NEW, **kw))}")
