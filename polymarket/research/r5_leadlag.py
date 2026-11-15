"""Sub-second lead-lag from the tick recording: Binance spot / perp mid vs the Polymarket Up-token quote.
All times are local receive times at this PC. Grid = 100 ms."""
import numpy as np, collections, sys, ticks
rows = ticks.read(sys.argv[1] if len(sys.argv) > 1 else None)
t0, t1 = rows[0][0], rows[-1][0]; G = 100; n = (t1 - t0) // G + 1
print(f"recording {(t1 - t0) / 60000:.1f} min, rows {len(rows)}")
def grid(ev):   # ev: list of (t, value) -> last value at each grid point
    a = np.full(n, np.nan)
    for t, v in ev: a[(t - t0) // G] = v
    idx = np.where(np.isfinite(a), np.arange(n), -1); idx = np.maximum.accumulate(idx)
    return np.where(idx >= 0, a[np.clip(idx, 0, None)], np.nan)
ser = collections.defaultdict(list); mk = {}
for r in rows:
    if r[1] in "sf": ser[(r[1], r[2])].append((r[0], (r[3] + r[4]) / 2))
    elif r[1] == "m": mk[r[2]] = r
    elif r[1] == "b" and r[3] is not None and r[5] is not None: ser[("b", r[2])].append((r[0], (r[3] + r[5]) / 2, r[3], r[5], r[7]))
delay = [r[0] - r[7] for r in rows if r[1] == "b" and r[7]]
print("Polymarket book update: local receive minus server timestamp (ms): median %.0f p10 %.0f p90 %.0f" % (np.median(delay), np.percentile(delay, 10), np.percentile(delay, 90)))
for coin, sym in (("btc", "BTCUSDT"), ("eth", "ETHUSDT")):
    spot, perp = grid(ser[("s", sym)]), grid(ser[("f", sym)])
    for win in (300, 900):
        acc = collections.defaultdict(list)
        for slug, m in mk.items():
            if not slug.startswith(coin) or m[4] != win: continue
            ev = [(e[0], e[1]) for e in ser.get(("b", m[5]), []) if m[3] * 1000 + 5000 <= e[0] <= (m[3] + win) * 1000 - 20000]
            if len(ev) < 200: continue
            pm = grid(ev); a, b = (ev[0][0] - t0) // G, (ev[-1][0] - t0) // G
            for name, src in (("spot", spot), ("perp", perp)):
                for step in (2, 5, 10):                      # 200 ms, 500 ms, 1 s changes
                    ds = np.log(src[a + step:b:step] / src[a:b - step:step]); dp = pm[a + step:b:step] - pm[a:b - step:step]
                    live = (pm[a:b - step:step] > .1) & (pm[a:b - step:step] < .9)
                    for lag in range(-5, 31):
                        x, y = (ds[:len(ds) - lag], dp[lag:]) if lag >= 0 else (ds[-lag:], dp[:lag])
                        lv = live[lag:] if lag >= 0 else live[:lag]
                        ok = np.isfinite(x) & np.isfinite(y) & lv
                        acc[(name, step, lag)].append((np.sum(x[ok] * y[ok]), np.sum(x[ok] ** 2), np.sum(y[ok] ** 2), ok.sum()))
        if not acc: continue
        print(f"\n{coin} {win // 60}m markets: corr( Binance move in a bin , Polymarket Up-quote move `lag` bins later )")
        for name in ("spot", "perp"):
            for step in (2, 5, 10):
                c = {}
                for lag in range(-5, 31):
                    v = np.array(acc[(name, step, lag)]).sum(0); c[lag] = v[0] / np.sqrt(v[1] * v[2])
                best = max(c, key=c.get)
                print(f"  {name} bin {step * G:4d}ms: peak lag {best * step * G:+5d}ms (corr {c[best]:+.3f}) | " + " ".join(f"{l * step * G / 1000:+.1f}s:{c[l]:+.2f}" for l in (-2, -1, 0, 1, 2, 3, 4, 6, 8, 12)))
