import numpy as np, lab
d = lab.load(); print("markets", d.M, "days", np.unique(d.day).size)
# 1. Does spot-based fair value carry information the Polymarket price does not have (at 1 second)?
lg = lambda p: np.log(np.clip(p, .01, .99) / (1 - np.clip(p, .01, .99)))
for s in (30, 60, 120, 180, 240, 270):
    ok = (d.age[:, s] <= 3) & np.isfinite(d.fair[:, s])
    X = np.c_[np.ones(ok.sum()), lg(d.pm[ok, s]), lg(d.fair[ok, s])]; b, zz = lab.logit_fit(X, d.won[ok])
    print(f"sec {s:3d} n={ok.sum()} coef pm {b[1]:.2f} (z {zz[1]:.1f})  coef fair {b[2]:.2f} (z {zz[2]:.1f}) | corr(pm,fair) {np.corrcoef(d.pm[ok,s], d.fair[ok,s])[0,1]:.3f} | mean |pm-fair| {np.abs(d.pm[ok,s]-d.fair[ok,s]).mean():.3f}")
