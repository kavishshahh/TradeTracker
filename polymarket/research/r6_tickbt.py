"""Tick backtest of the latency idea: Binance moves, buy the matching side on Polymarket before its quote follows.
Signal at time t: Binance mid moved >= thr bps over the last `look` ms. Our order lands `lat` ms later and pays the
ask that is in the book then (as seen from this PC), plus the 7% fee curve. The position is valued at the token's
mid `hold` seconds later (mid is a fair, low-noise stand-in for holding to the result). Cents per share.
Usage: python r6_tickbt.py [file]"""
import numpy as np, collections, sys, itertools, ticks
rows = ticks.read(sys.argv[1] if len(sys.argv) > 1 else None)
t0, t1 = rows[0][0], rows[-1][0]; G = 100; n = (t1 - t0) // G + 1
print(f"recording {(t1 - t0) / 3600000:.2f} h, rows {len(rows)}")
def ffill(a):
    idx = np.where(np.isfinite(a), np.arange(len(a)), -1); idx = np.maximum.accumulate(idx)
    return np.where(idx >= 0, a[np.clip(idx, 0, None)], np.nan)
src = {}; books = collections.defaultdict(lambda: [np.full(n, np.nan), np.full(n, np.nan)]); mk = {}
for r in rows:
    i = (r[0] - t0) // G
    if r[1] in "sf":
        src.setdefault((r[1], r[2]), np.full(n, np.nan))[i] = (r[3] + r[4]) / 2
    elif r[1] == "m": mk[r[2]] = r
    elif r[1] == "b":
        b = books[r[2]]; b[0][i] = r[3] if r[3] is not None else 0.0; b[1][i] = r[5] if r[5] is not None else 1.0
src = {k: ffill(v) for k, v in src.items()}
FEE = lambda p: .07 * p * (1 - p)
def run(win, name, look, thr, lat, hold, quiet=False, require_still=None):
    out = []
    for slug, m in mk.items():
        if m[4] != win: continue
        s = src.get((name, slug[:3].upper() + "USDT"))
        if s is None or m[5] not in books or m[6] not in books: continue
        a, b = max((m[3] * 1000 + 5000 - t0) // G, look + 1), min(((m[3] + win) * 1000 - 20000 - t0) // G, n - lat - hold - 1)
        if b - a < 100: continue
        ub, ua = (ffill(x) for x in books[m[5]]); db, da = (ffill(x) for x in books[m[6]])
        i = np.arange(a, b); r = np.log(s[i] / s[i - look]) * 1e4
        for side, hit, ask, bid in ((0, r >= thr, ua, ub), (1, r <= -thr, da, db)):
            k = i[hit]
            if not len(k): continue
            keep = np.r_[True, np.diff(k) > 10]; k = k[keep]                       # one bet per burst
            e = ask[k + lat]; mid0 = (ask[k] + bid[k]) / 2; v = (ask[k + lat + hold] + bid[k + lat + hold]) / 2
            ok = np.isfinite(e) & np.isfinite(v) & (mid0 > .1) & (mid0 < .9) & (e < .97)
            if require_still is not None:                                           # quote has not moved yet
                ok &= np.abs(mid0 - (ask[k - look] + bid[k - look]) / 2) <= require_still
            out += list(zip((v - e - FEE(e))[ok] * 100, (ask[k] - bid[k])[ok] * 100, (e - ask[k])[ok] * 100, (v - mid0)[ok] * 100, np.full(ok.sum(), m[3])))
    if len(out) < 30: return None
    o = np.array(out); pnl = o[:, 0]
    u, inv = np.unique(o[:, 4], return_inverse=True); cs = np.bincount(inv, pnl - pnl.mean())
    return dict(n=len(pnl), pnl=pnl.mean(), t=pnl.mean() * len(pnl) / np.sqrt((cs ** 2).sum()), spread=o[:, 1].mean(), slip=o[:, 2].mean(), move=o[:, 3].mean())
f = lambda s: "too few" if s is None else f"n={s['n']:5d} pnl={s['pnl']:+.2f}c (t {s['t']:+.1f}) | quote moved our way {s['move']:+.2f}c, spread {s['spread']:.2f}c, ask moved before fill {s['slip']:+.2f}c"
for win in (300, 900):
    print(f"\n=== {win // 60}-minute markets, BTC+ETH; hold 5 s")
    print("baseline, any Binance tick (thr 0):", f(run(win, "s", 5, 0.0, 2, 50)))
    for name, look, thr in itertools.product(("s", "f"), (2, 5, 10), (1.0, 2.0, 3.0, 5.0)):
        for lat in (1, 2, 4, 7):
            s = run(win, name, look, thr, lat, 50)
            if s: print(f"{'spot' if name == 's' else 'perp'} moved {thr}bp in {look * G}ms, order lands +{lat * G}ms: {f(s)}")
