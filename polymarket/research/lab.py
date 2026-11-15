"""Shared research helpers: load the per-second table, model fair value from spot, simulate fills."""
import numpy as np
def ncdf(x):
    """Normal CDF (Abramowitz-Stegun 7.1.26, error < 1.5e-7)."""
    x = np.asarray(x, float); a = np.abs(x) / np.sqrt(2); t = 1 / (1 + .3275911 * a)
    e = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - .284496736) * t + .254829592) * t * np.exp(-a * a)
    return .5 * (1 + np.sign(x) * e)
def logit_fit(X, y, it=30):
    """Logistic regression by Newton steps. Returns (coef, z-scores); X needs its own constant column."""
    b = np.zeros(X.shape[1])
    for _ in range(it):
        p = 1 / (1 + np.exp(-X @ b)); H = (X * (p * (1 - p))[:, None]).T @ X
        b = b + np.linalg.solve(H, X.T @ (y - p))
    return b, b / np.sqrt(np.diag(np.linalg.inv(H)))
FEE = .07
class D: pass
def load(path="data/sec5m.npz", W=300):
    z = np.load(path, allow_pickle=True); d = D(); d.W = W
    for k in z.files: setattr(d, k, z[k])
    ok = np.isfinite(d.S0) & (d.sig > 0)
    for k in z.files: setattr(d, k, getattr(d, k)[ok])
    d.M = ok.sum(); sec = np.arange(W)
    # last known Polymarket price (size-weighted average of the latest second with prints) and its age
    idx = np.where(np.isfinite(d.avg), sec, -1); idx = np.maximum.accumulate(idx, axis=1)
    d.pm = np.where(idx >= 0, np.take_along_axis(d.avg, np.clip(idx, 0, None), 1), np.nan); d.age = np.where(idx >= 0, sec - idx, 999)
    # next second (strictly after s) that has prints: worst/avg prices there and how long until it
    nxt = np.where(np.isfinite(d.avg), sec, 10 ** 6); nxt = np.minimum.accumulate(nxt[:, ::-1], axis=1)[:, ::-1]
    nxt = np.concatenate([nxt[:, 1:], np.full((d.M, 1), 10 ** 6)], 1); has = nxt < 10 ** 6; j = np.clip(nxt, 0, W - 1)
    d.n_wait = np.where(has, nxt - sec, 999)
    d.n_avg = np.where(has, np.take_along_axis(d.avg, j, 1), np.nan); d.n_hi = np.where(has, np.take_along_axis(d.hi, j, 1), np.nan); d.n_lo = np.where(has, np.take_along_axis(d.lo, j, 1), np.nan)
    d.x = np.log(d.spot / d.S0[:, None]); d.tau = (W - sec)[None, :].astype(float)
    d.z = d.x / (d.sig[:, None] * np.sqrt(d.tau)); d.fair = ncdf(d.z)
    d.day = (d.start // 86400).astype(int)
    return d
def ret(won, f): return (won - f - FEE * f * (1 - f)) / f
def bets(d, sig_up, sig_dn, lo_s=5, hi_s=None, max_wait=3, slip=.01, worst=True, pmin=.03, pmax=.97):
    """First second in [lo_s, hi_s] where a signal fires -> buy that side at the next prints (worst print + slip).
    Returns arrays (market index, second, side, fill price, return per $)."""
    hi_s = hi_s or d.W - 10; out = []
    S = np.zeros_like(sig_up, bool); S[:, lo_s:hi_s] = True
    for side, sg in ((0, sig_up), (1, sig_dn)):
        px = (d.n_hi if worst else d.n_avg) if side == 0 else 1 - (d.n_lo if worst else d.n_avg)
        ok = sg & S & (d.n_wait <= max_wait) & np.isfinite(px) & (px + slip >= pmin) & (px + slip <= pmax)
        first = np.where(ok.any(1), ok.argmax(1), -1)
        for i in np.flatnonzero(first >= 0):
            s = first[i]; f = px[i, s] + slip; won = d.won[i] if side == 0 else 1 - d.won[i]
            out.append((i, s, side, f, ret(won, f)))
    if not out: return None
    a = np.array(out); 
    # one bet per market: the earlier signal
    o = np.lexsort((a[:, 1], a[:, 0])); a = a[o]; keep = np.r_[True, a[1:, 0] != a[:-1, 0]]
    return a[keep]
def summary(d, a):
    if a is None or len(a) < 20: return None
    r = a[:, 4]; st = d.start[a[:, 0].astype(int)]
    # cluster by window start (BTC and ETH in the same window move together)
    u, inv = np.unique(st, return_inverse=True); cm = np.bincount(inv, r) / np.bincount(inv); cn = np.bincount(inv)
    t = r.mean() / (np.sqrt(((cn * (cm - r.mean())) ** 2).sum()) / len(r))
    return dict(n=len(r), roi=r.mean(), t=t, px=a[:, 3].mean(), win=(r > 0).mean())
