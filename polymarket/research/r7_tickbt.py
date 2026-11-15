"""Latency idea on the tick recording, in EXCHANGE time (Polymarket book timestamps, Binance event times), so slow
delivery of either feed to this PC cannot fake an edge.
Signal at time t: Binance moved >= thr bps over the last `look` ms. Our order reaches Polymarket `lat` ms after the
Binance move happened (that budget covers: Binance -> us, deciding, us -> Polymarket) and pays the ask in the book at
that moment + the 7% fee curve. Valued at the token's mid `hold` s later. Cents per share. Grid 50 ms.
Usage: python r7_tickbt.py [file]"""
import numpy as np, collections, sys, itertools, ticks
rows = ticks.read(sys.argv[1] if len(sys.argv) > 1 else None)
G = 50
ts = [r[5] for r in rows if r[1] == "f"]; t0, t1 = min(ts), max(ts); n = (t1 - t0) // G + 2
print(f"recording {(t1 - t0) / 3600000:.2f} h, rows {len(rows)}")
def ffill(a):
    idx = np.where(np.isfinite(a), np.arange(len(a)), -1); idx = np.maximum.accumulate(idx)
    return np.where(idx >= 0, a[np.clip(idx, 0, None)], np.nan)
src = {}; books = {}; mk = {}
def put(arr, t, v):
    i = (t - t0) // G
    if 0 <= i < n: arr[i] = v
for r in rows:
    if r[1] == "f": put(src.setdefault(("f", r[2]), np.full(n, np.nan)), r[5], (r[3] + r[4]) / 2)
    elif r[1] == "S": put(src.setdefault(("s", r[2]), np.full(n, np.nan)), r[4], r[3])
    elif r[1] == "m": mk[r[2]] = r
    elif r[1] == "b" and r[7]:
        b = books.setdefault(r[2], [np.full(n, np.nan), np.full(n, np.nan)])
        put(b[0], r[7], r[3] if r[3] is not None else 0.0); put(b[1], r[7], r[5] if r[5] is not None else 1.0)
src = {k: ffill(v) for k, v in src.items()}; books = {k: [ffill(x) for x in v] for k, v in books.items()}
FEE = lambda p: .07 * p * (1 - p)
ms = lambda x: int(round(x / G))
def run(win, name, look, thr, lat, hold=5000, still=None, coins=("btc", "eth"), lo=.1, hi=.9):
    look, lat, hold = ms(look), ms(lat), ms(hold); out = []
    for slug, m in mk.items():
        if m[4] != win or slug[:3] not in coins: continue
        s = src.get((name, slug[:3].upper() + "USDT"))
        if s is None or m[5] not in books or m[6] not in books: continue
        a, b = max((m[3] * 1000 + 5000 - t0) // G, look + 1), min(((m[3] + win) * 1000 - 20000 - t0) // G, n - lat - hold - 1)
        if b - a < 200: continue
        i = np.arange(a, b); r = np.log(s[i] / s[i - look]) * 1e4
        for side, hit, tok in ((0, r >= thr, m[5]), (1, r <= -thr, m[6])):
            bid, ask = books[tok]; k = i[hit]
            if not len(k): continue
            k = k[np.r_[True, np.diff(k) > ms(1000)]]                                # one bet per burst
            e = ask[k + lat]; mid0 = (ask[k] + bid[k]) / 2; v = (ask[k + lat + hold] + bid[k + lat + hold]) / 2
            ok = np.isfinite(e) & np.isfinite(v) & (mid0 > lo) & (mid0 < hi) & (e < .97) & (ask[k] - bid[k] <= .05)
            if still is not None: ok &= (mid0 - (ask[k - look] + bid[k - look]) / 2) <= still
            out += list(zip((v - e - FEE(e))[ok] * 100, (e - ask[k])[ok] * 100, (v - mid0)[ok] * 100, np.full(ok.sum(), m[3]), e[ok]))
    if len(out) < 40: return None
    o = np.array(out); pnl = o[:, 0]; u, inv = np.unique(o[:, 3], return_inverse=True)
    cs = np.bincount(inv, pnl - pnl.mean()); t = pnl.sum() / np.sqrt((cs ** 2).sum()) if len(u) > 3 else float("nan")
    return dict(n=len(pnl), pnl=pnl.mean(), t=t, slip=o[:, 1].mean(), move=o[:, 2].mean(), px=o[:, 4].mean(), windows=len(u))
f = lambda s: "too few" if s is None else f"n={s['n']:5d} in {s['windows']:3d} windows | pnl {s['pnl']:+.2f}c/share (t {s['t']:+.1f}) | quote moved our way {s['move']:+.2f}c in 5 s, ask already moved {s['slip']:+.2f}c | avg price {s['px']:.2f}"
if __name__ == "__main__":
    for win in (300, 900):
        print(f"\n=== {win // 60}-minute markets")
        print("baseline: buy at random Binance ticks, +300 ms:", f(run(win, "f", 500, -1e9, 300)))
        for name, look, thr in itertools.product(("f", "s"), (200, 500, 1000), (1.0, 2.0, 3.0)):
            for lat in (50, 150, 300, 500, 800, 1500):
                s = run(win, name, look, thr, lat)
                if s: print(f"{'perp' if name == 'f' else 'spot'} moved {thr}bp in {look:4d}ms, order arrives +{lat:4d}ms: {f(s)}")
