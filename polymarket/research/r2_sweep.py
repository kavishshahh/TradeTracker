"""Sweep of spot-vs-odds rules on 5-minute markets. Decision at the end of second s uses prints up to s and the
Binance price at that moment; the fill is the WORST print of the next second with trades (within 3 s) + 1c, plus fee.
Train = first 60% of windows, test = the rest. Rules are ranked on train only."""
import numpy as np, itertools, lab, sys
d = lab.load(*(sys.argv[1:3] if len(sys.argv) > 2 else ["data/sec5m.npz"]), **(dict(W=int(sys.argv[3])) if len(sys.argv) > 3 else {}))
W = d.W; cut = np.sort(np.unique(d.start))[int(.6 * np.unique(d.start).size)]
tr, te = d.start < cut, d.start >= cut
def shift(a, k): return np.concatenate([np.full((a.shape[0], k), np.nan), a[:, :-k]], 1)
fresh = d.age <= 2
res = []
def run(name, up, dn, **kw):
    a = lab.bets(d, up, dn, **kw)
    if a is None: return
    i = a[:, 0].astype(int); s1, s2 = lab.summary(d, a[tr[i]]), lab.summary(d, a[te[i]])
    if s1 and s2: res.append((name, s1, s2))
# A. fair-value gap
for g, (t0, t1), (p0, p1), zmin in itertools.product((.05, .08, .12, .16, .2, .25), ((.1, .5), (.3, .7), (.5, .9), (.7, .97), (.1, .97)), ((.03, .97), (.2, .8), (.5, .97), (.03, .5)), (0, .5, 1.0)):
    gap = d.fair - d.pm; base = fresh
    up = base & (gap >= g) & (d.pm >= p0) & (d.pm <= p1) & (d.z >= zmin)
    dn = base & (gap <= -g) & (1 - d.pm >= p0) & (1 - d.pm <= p1) & (-d.z >= zmin)
    run(f"A gap>={g} t={t0}-{t1} side px {p0}-{p1} |z|>={zmin}", up, dn, lo_s=int(t0 * W), hi_s=int(t1 * W))
# B. spot moved over k seconds, odds did not follow
for k, zt, pmv, (t0, t1), (p0, p1) in itertools.product((1, 2, 3, 5, 10, 20), (.3, .5, .8, 1.2), (.01, .03, .06), ((.1, .5), (.5, .9), (.7, .97), (.1, .97)), ((.03, .97), (.2, .8), (.5, .97))):
    dz = d.z - shift(d.z, k); dp = d.pm - shift(d.pm, k); base = fresh & (shift(d.age, k) <= 2)
    up = base & (dz >= zt) & (dp <= pmv) & (d.pm >= p0) & (d.pm <= p1)
    dn = base & (dz <= -zt) & (dp >= -pmv) & (1 - d.pm >= p0) & (1 - d.pm <= p1)
    run(f"B dz{k}s>={zt} dpm<={pmv} t={t0}-{t1} side px {p0}-{p1}", up, dn, lo_s=max(int(t0 * W), k + 1), hi_s=int(t1 * W))
# C. spot crossed the start price in the last k seconds (sign flip) while odds still favour the old side
for k, pth, (t0, t1) in itertools.product((1, 2, 3, 5, 10), (.5, .55, .6, .7), ((.3, .7), (.5, .9), (.7, .97), (.85, .98))):
    x0 = shift(d.x, k); up = fresh & (d.x > 0) & (x0 < 0) & (d.pm <= 1 - pth + .0); dn = fresh & (d.x < 0) & (x0 > 0) & (d.pm >= pth)
    run(f"C cross{k}s old-side>={pth} t={t0}-{t1}", up, dn, lo_s=max(int(t0 * W), k + 1), hi_s=int(t1 * W))
print("rules with enough bets:", len(res))
res.sort(key=lambda r: -r[1]["t"])
f = lambda s: f"n={s['n']:4d} roi={s['roi']:+.3f} t={s['t']:+.1f} px={s['px']:.2f} win={s['win']:.2f}"
print("\nTOP 20 ON TRAIN -> how they did on TEST")
for name, s1, s2 in res[:20]: print(f"{name:55s} | train {f(s1)} | test {f(s2)}")
tt = np.array([r[2]["roi"] for r in res[:50]]); print(f"\ntop-50-on-train: mean test roi {tt.mean():+.3f}, share positive on test {(tt > 0).mean():.2f}")
al = np.array([r[2]["roi"] for r in res]); print(f"all rules: mean test roi {al.mean():+.3f}, share positive on test {(al > 0).mean():.2f}, mean train roi {np.mean([r[1]['roi'] for r in res]):+.3f}")
import pickle; pickle.dump(res, open(f"data/sweep_{W}.pkl", "wb"))
