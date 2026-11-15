"""Backtest late-window rules on 5-minute BTC/ETH up/down markets, using every fill.

Signal second s (seconds since the 5-minute window opened). A side's price at s = last print
at or before s (ignored if older than 20 s). Entry fill = the first print in (s, s+10], i.e. what
someone actually paid right after the signal; skipped if none, or if it is > 3c worse than the signal.
Cost = taker fee rate*p*(1-p) per share. Hold to resolution. One entry per market.

Rules
  price : your pattern. time left <= T, leading side priced in [lo, hi].
  model : fair P(side) from Binance (distance from the window's opening price, in volatility
          units for the time left); enter when fair - price - fee >= edge.
  both  : your pattern, but only when the model agrees (fair >= price + margin).
"""
import itertools
from math import erf, sqrt
import numpy as np
import pandas as pd

N = np.vectorize(lambda x: 0.5 * (1 + erf(x / sqrt(2))))
SYM = {"btc": "BTCUSDT", "eth": "ETHUSDT"}


def prepare():
    d = pd.read_pickle("data/updown5m.pkl")
    d = d[d.trades.map(len) >= 30].sort_values("start").reset_index(drop=True)
    spot = np.load("data/binance_1s.npy", allow_pickle=True).item()
    series = {}
    for sym, a in spot.items():
        t0 = int(a[0, 0]); full = np.full(int(a[-1, 0]) - t0 + 1, np.nan); full[(a[:, 0] - t0).astype(int)] = a[:, 1]
        full = pd.Series(full).ffill().to_numpy()
        lr = np.diff(np.log(full), prepend=np.log(full[0]))
        vol = pd.Series(lr).rolling(900).std().to_numpy()          # per-second sigma over the prior 15 min
        series[sym] = (t0, full, vol)
    rows = []
    secs = np.arange(0, 300)
    for r in d.itertuples():
        t = np.array([(x[0], x[2] if x[1] == 0 else 1 - x[2]) for x in r.trades], float)   # (sec, up price)
        idx = np.searchsorted(t[:, 0], secs, side="right") - 1
        up = np.where(idx >= 0, t[np.clip(idx, 0, None), 1], np.nan)
        age = np.where(idx >= 0, secs - t[np.clip(idx, 0, None), 0], 999)
        up[age > 20] = np.nan
        nxt_i = np.searchsorted(t[:, 0], secs, side="right")
        ok = (nxt_i < len(t)) & (t[np.clip(nxt_i, 0, len(t) - 1), 0] <= secs + 10)
        nxt = np.where(ok, t[np.clip(nxt_i, 0, len(t) - 1), 1], np.nan)
        t0, px, vol = series[SYM[r.coin]]
        i0 = r.start - t0
        if i0 < 900 or i0 + 300 >= len(px):
            continue
        s0, sig = px[i0], vol[i0]
        fair = N(np.log(px[i0:i0 + 300] / s0) / (sig * np.sqrt(300 - secs) + 1e-12))
        rows.append(dict(coin=r.coin, start=r.start, won_up=r.won_up, fee=r.fee_rate, up=up, nxt=nxt, fair=fair))
    return rows


def run_rule(rows, kind, T, lo, hi, edge=0.0, mom=None):
    out = []
    for r in rows:
        win = np.arange(300 - T, 296)
        for side in (0, 1):
            p = r["up"][win] if side == 0 else 1 - r["up"][win]
            f = r["fair"][win] if side == 0 else 1 - r["fair"][win]
            fee = r["fee"] * p * (1 - p)
            if kind == "price":
                hit = (p >= lo) & (p <= hi)
            elif kind == "model":
                hit = (p >= lo) & (p <= hi) & (f - p - fee >= edge)
            else:
                hit = (p >= lo) & (p <= hi) & (f >= p + edge)
            if mom is not None:
                prev = r["up"][win - 30] if side == 0 else 1 - r["up"][win - 30]
                hit &= (p - prev) >= mom
            k = np.flatnonzero(hit)
            if not len(k):
                continue
            s = win[k[0]]
            fill = r["nxt"][s] if side == 0 else 1 - r["nxt"][s]
            if np.isnan(fill) or fill > p[k[0]] + 0.03 or fill >= 0.995:
                continue
            won = r["won_up"] if side == 0 else 1 - r["won_up"]
            out.append((r["start"], r["coin"], s, fill, won, (won - fill - r["fee"] * fill * (1 - fill)) / fill))
            break
    return pd.DataFrame(out, columns=["start", "coin", "sec", "fill", "won", "ret"])


def stats(b):
    if len(b) < 5:
        return dict(n=len(b))
    return dict(n=len(b), win=b.won.mean(), px=b.fill.mean(), roi=b.ret.mean(), t=b.ret.mean() / (b.ret.std(ddof=1) / np.sqrt(len(b))))


if __name__ == "__main__":
    rows = prepare()
    cut = rows[int(len(rows) * 0.6)]["start"]
    days = (rows[-1]["start"] - rows[0]["start"]) / 86400
    print(f"markets {len(rows)} over {days:.1f} days; train before {pd.Timestamp(cut, unit='s')}, test after")
    grid = []
    for T, lo, hi in itertools.product([180, 120, 90, 60, 30, 15], [.6, .7, .8, .9, .95], [.9, .95, .98, .99]):
        if lo < hi:
            grid.append(("price", T, lo, hi, 0.0, None))
    for T, lo, hi, mom in itertools.product([180, 120, 60], [.7, .8], [.95, .99], [0.0, 0.05]):
        grid.append(("price", T, lo, hi, 0.0, mom))
    for T, lo, hi, e in itertools.product([180, 120, 60, 30], [.5, .7], [.95, .99], [.03, .05, .08, .12]):
        grid.append(("model", T, lo, hi, e, None))
    for T, lo, hi, e in itertools.product([180, 120, 60], [.7, .8], [.95, .99], [0.0, .03, .06]):
        grid.append(("both", T, lo, hi, e, None))
    res = []
    for g in grid:
        b = run_rule(rows, *g)
        tr, te = stats(b[b.start < cut]), stats(b[b.start >= cut])
        res.append(dict(kind=g[0], T=g[1], lo=g[2], hi=g[3], edge=g[4], mom=g[5], n_tr=tr.get("n"), win_tr=tr.get("win"), roi_tr=tr.get("roi"), t_tr=tr.get("t"),
                        n_te=te.get("n"), win_te=te.get("win"), px_te=te.get("px"), roi_te=te.get("roi"), t_te=te.get("t")))
    R = pd.DataFrame(res)
    R.to_csv("results/updown_grid.csv", index=False)
    pd.set_option("display.width", 220); pd.set_option("display.max_rows", 200)
    print("\n== Your pattern and neighbours (price rule, no filters) ==")
    print(R[(R.kind == "price") & R.mom.isna() & R.hi.isin([.95, .99]) & R.lo.isin([.6, .7, .8, .9])].round(3).drop(columns=["edge", "mom"]).to_string(index=False))
    for kind in ("price", "model", "both"):
        k = R[(R.kind == kind) & (R.n_tr >= 100)].sort_values("roi_tr", ascending=False).head(6)
        print(f"\n== Best '{kind}' rules on the training period, with their held-out result ==")
        print(k.round(3).to_string(index=False))
