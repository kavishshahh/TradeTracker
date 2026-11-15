"""How fast does the 'spot moved, odds did not' profit disappear as the fill is delayed (in tape seconds)?
And the raw cross-correlation of spot moves with later/earlier odds moves."""
import numpy as np, lab
d = lab.load(); W = d.W
def shift(a, k): return np.concatenate([np.full((a.shape[0], k), np.nan), a[:, :-k]], 1) if k > 0 else a
def lead(a, k): return np.concatenate([a[:, k:], np.full((a.shape[0], k), np.nan)], 1) if k > 0 else a
k = 2; dz = d.z - shift(d.z, k); dp = d.pm - shift(d.pm, k); base = (d.age <= 2) & (shift(d.age, k) <= 2)
up = base & (dz >= .5) & (dp <= .03) & (d.pm >= .2) & (d.pm <= .8); dn = base & (dz <= -.5) & (dp >= -.03) & (d.pm >= .2) & (d.pm <= .8)
keep = {n: getattr(d, n).copy() for n in ("n_hi", "n_lo", "n_avg", "n_wait")}
print("rule: spot moved 0.5 sigma-units in 2 s, odds moved < 3c, side priced 20-80c")
for L in (0, 1, 2, 3, 5, 8, 12, 20):
    for n in keep: setattr(d, n, lead(keep[n], L))
    s = lab.summary(d, lab.bets(d, up, dn, lo_s=10, hi_s=W - 25))
    print(f"fill delayed {L:2d}s more: n={s['n']} roi={s['roi']:+.3f} t={s['t']:+.1f} px={s['px']:.3f} win={s['win']:.3f}")
for n in keep: setattr(d, n, keep[n])
# cross-correlation: 1-second spot move (in fair-value terms) vs odds change at other lags
df = d.fair - shift(d.fair, 1)
mid = (d.tau > 30) & (d.tau < 270)
print("\ncorr of spot-implied 1s change at t with odds 1s change at t+lag (odds = last print average):")
for lag in range(-3, 9):
    dpm = lead(d.pm, lag) - lead(d.pm, lag - 1) if lag >= 1 else shift(d.pm, -lag) - shift(d.pm, -lag + 1)
    ok = mid & np.isfinite(df) & np.isfinite(dpm) & (np.abs(df) > 0)
    print(f"  lag {lag:+d}s: {np.corrcoef(df[ok], dpm[ok])[0, 1]:+.3f}")
