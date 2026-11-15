"""Per-second research table for 5-minute up/down markets (no reliance on print order inside a second).
data/sec5m.npz: avg/lo/hi Up price and volume per second (nan when no print), Binance 1s close aligned to the window,
S0 (close just before the window), sigma (per-second vol from the 15 minutes before), won_up, coin, start."""
import numpy as np, pandas as pd, sys
src, out, W = (sys.argv + ["data/updown5m.pkl", "data/sec5m.npz", "300"])[1:4]; W = int(W)
d = pd.read_pickle(src); d = d[d.trades.map(len) >= 30].sort_values("start").reset_index(drop=True)
B = np.load("data/binance_1s.npy", allow_pickle=True).item()
M = len(d); avg = np.full((M, W), np.nan); lo = avg.copy(); hi = avg.copy(); vol = np.zeros((M, W)); spot = np.full((M, W), np.nan)
S0 = np.full(M, np.nan); sig = np.full(M, np.nan)
for i, r in enumerate(d.itertuples()):
    t = np.array([(x[0], x[2] if x[1] == 0 else 1 - x[2], x[3]) for x in r.trades if 0 <= x[0] < W], float)
    s = t[:, 0].astype(int)
    v = np.bincount(s, t[:, 2], W); pv = np.bincount(s, t[:, 1] * t[:, 2], W)
    ok = v > 0; avg[i, ok] = pv[ok] / v[ok]; vol[i] = v
    l = np.full(W, np.inf); h = np.full(W, -np.inf); np.minimum.at(l, s, t[:, 1]); np.maximum.at(h, s, t[:, 1]); lo[i, ok] = l[ok]; hi[i, ok] = h[ok]
    b = B[r.coin.upper() + "USDT"]; k = np.searchsorted(b[:, 0], r.start)
    if k < 1000 or k + W > len(b) or b[k, 0] != r.start: continue
    spot[i] = b[k:k + W, 1]; S0[i] = b[k - 1, 1]
    sig[i] = np.diff(np.log(b[k - 900:k, 1])).std()
np.savez_compressed(out, avg=avg, lo=lo, hi=hi, vol=vol, spot=spot, S0=S0, sig=sig, won=d.won_up.values.astype(float), coin=d.coin.values, start=d.start.values)
print("markets", M, "with spot", np.isfinite(S0).sum(), "seconds with prints %.2f" % np.isfinite(avg).mean())
