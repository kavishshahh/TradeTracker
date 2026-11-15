"""Crypto fair value with a volatility range instead of one number: fair is computed with the
lowest and the highest of the 7-day, 24-hour and 6-hour realised vol; a side is bought only if
it is cheap under BOTH (the estimate least favourable to that side)."""
import numpy as np, pandas as pd, warnings
from math import log, sqrt
warnings.filterwarnings("ignore")
import crypto_model as cm
from backtest import price_at, SPLIT
K = cm.K
VOL = {}
for sym, k in K.items():
    lr = np.log(k.c).diff()
    VOL[sym] = pd.DataFrame({"v7": lr.rolling(168).std(), "v24": lr.rolling(24).std(), "v6": lr.rolling(6).std()}).shift(1)   # closed candles only
def probs(kind, k1, k2, sym, t, start, end):
    k = K[sym]; i = k.index.searchsorted(t - 3600, side="right") - 1
    if i < 170: return None
    S = k.c.iloc[i]; v = VOL[sym].iloc[i]
    if v.isna().any(): return None
    T = max((end - t) / 3600, 1e-3); window = k[(k.index >= start) & (k.index <= t - 3600)]
    out = []
    for sig in (v.v7, min(v), max(v)):
        sd = sig * sqrt(T)
        if kind == "dip": p = 1.0 if len(window) and window.l.min() <= k1 else min(1.0, 2 * cm.N(log(k1 / S) / sd))
        elif kind == "reach": p = 1.0 if len(window) and window.h.max() >= k1 else min(1.0, 2 * cm.N(-log(k1 / S) / sd))
        elif kind == "above": p = cm.N(log(S / k1) / sd)
        elif kind == "below": p = cm.N(log(k1 / S) / sd)
        else: p = cm.N(log(k2 / S) / sd) - cm.N(log(k1 / S) / sd)
        out.append(p)
    return out
d = pd.read_pickle("data/prices.pkl"); d = d[(d.bucket == "crypto_level") & (d["hist"].map(len) > 5)]
rows = []
for r in d.itertuples():
    p = cm.parse(r.question or "")
    if not p or r.outcomes[:1] != ["Yes"]: continue
    sym, kind, k1, k2 = p; start = pd.Timestamp(r.start).timestamp(); end = pd.Timestamp(r.end).timestamp(); h = sorted(r.hist)
    for t in np.arange(max(start + 3600, h[0][0]), min(end, r.closed_ts) - 1800, 3 * 3600):
        if (end - t) / 3600 < 6: continue                      # live rule: at least 6 hours left
        pm = price_at(h, t, 1800)
        if pm is None or not .05 < pm < .95: continue
        pr = probs(kind, k1, k2, sym, int(t), start, end)
        if pr is None or pr[0] >= .999: continue
        rows.append((r.condition_id, kind, sym, t, pm, pr[0], min(pr), max(pr), r.won0, end >= SPLIT))
S = pd.DataFrame(rows, columns=["cid", "kind", "sym", "t", "p", "m7", "mlo", "mhi", "won", "test"])
def trade(S, edge, robust, max_same=None):
    yes_edge = (S.mlo if robust else S.m7) - S.p; no_edge = S.p - (S.mhi if robust else S.m7)
    sig = S[(yes_edge > edge) | (no_edge > edge)].assign(buy_yes=yes_edge > edge).sort_values("t").drop_duplicates("cid")
    q = np.where(sig.buy_yes, sig.p, 1 - sig.p); won = np.where(sig.buy_yes, sig.won, 1 - sig.won)
    f = np.minimum(q + .01, .999); r = (won - f - .07 * f * (1 - f)) / f
    return sig.assign(q=q, w=won, r=r)
def st(b): return f"n={len(b):4d} win={b.w.mean():.3f} px={b.q.mean():.3f} roi={b.r.mean():+.3f} t={b.r.mean()/(b.r.std(ddof=1)/np.sqrt(len(b))):+.1f}" if len(b) > 5 else f"n={len(b)}"
print("markets", S.cid.nunique())
for edge in (.10, .15, .20):
    for robust in (False, True):
        b = trade(S, edge, robust)
        print(f"edge {edge:.2f} {'vol-range' if robust else 'single 7d vol':13s} | train {st(b[~b.test])} | test {st(b[b.test])}")
b0, b1 = trade(S, .15, False), trade(S, .15, True)
for name, b in (("single 7d vol", b0), ("vol-range", b1)):
    b = b.assign(day=pd.to_datetime(b.t, unit="s").dt.date, side=np.where(b.buy_yes, "YES", "NO"))
    g = b.groupby("day").r.agg(["size", "sum"]); worst = g.sort_values("sum").head(3)
    print(f"\n{name}: worst days (bets, sum of returns per $1): {[(str(i), int(r['size']), round(r['sum'], 1)) for i, r in worst.iterrows()]} | by side: {b.groupby('side').r.agg(['size', 'mean']).round(3).to_dict('index')} | by kind: {b.groupby('kind').r.agg(['size','mean']).round(3).to_dict('index')}")

import json
b = trade(S, .15, True); b = b[~b.buy_yes]
def js(x): return dict(n=int(len(x)), win_rate=float(x.w.mean()), avg_price=float(np.minimum(x.q + .01, .999).mean()), roi_per_bet=float(x.r.mean()), t_stat=float(x.r.mean()/(x.r.std(ddof=1)/np.sqrt(len(x)))), avg_hold_hours=150.0)
out = dict(strategy="crypto_fair_value", train=js(b[~b.test]), test=js(b[b.test]), train_label="Jun–Sep 2026 (tuned on)", test_label="Oct–Nov 2026 (held out)",
           note="Version 2 rule: buys NO only, and only when it is cheap under both the calmest and the most volatile recent estimate. Backtest uses hourly trade prices, not order books, so it is optimistic.",
           source="Jun-Nov 2026 resolved markets, taker fills, fees, 1c slippage")
json.dump(out, open("../TradeTracker/polymarket/backtests/crypto_fair_value.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print("\nNO-only vol-range:", {k: {a: round(v, 3) for a, v in out[k].items()} for k in ("train", "test")})
