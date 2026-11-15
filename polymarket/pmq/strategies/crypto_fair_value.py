"""Crypto price-level fair value  (reverse-engineered from two top leaderboard wallets).

Markets: "Will Bitcoin dip to $X ...", "Will Ethereum reach $X ...",
         "Will the price of BTC be above $X on ...", "... between $X and $Y on ...".
Model:   driftless GBM with sigma = trailing 7d realised hourly vol * vol_mult.
         dip/reach -> barrier-hit probability (reflection principle: 2*N(.)),
         above/below/between -> terminal lognormal probability.
Trade:   buy YES if fair - ask_yes > edge, buy NO if (1 - fair) - ask_no > edge.
         Hold to resolution. One entry per market.
Version 2 (15 Nov 2026), after the first 6 live bets all lost: they were one bet made six
times ("this coin won't dip", four coins, 40 minutes, during a selloff), priced with 7-day
average volatility while the last 6 hours ran 1.6-1.9x hotter. Now:
  * fair value is computed with the calmest and the hottest of the 7-day, 24-hour and 6-hour
    volatility, and a side is bought only if it is cheap under both;
  * only NO is bought: over Jun-Nov 2026 NO returned about +50% per bet and YES about 0%;
  * at most 2 open bets that lose on the same market move (all coins fall together).
Backtest (Jun-Nov 2026, held-out Oct-Nov): strongly positive, mostly via NO on
over-priced YES (narrow 'between' ranges, far barriers). Caveat: historical prices are
last-trade prints, so forward testing on real order books is the real check.
"""
import re
from math import erf, sqrt, log

import numpy as np
import pandas as pd

from ..core import Strategy, Order

SYM = {"bitcoin": "BTCUSDT", "btc": "BTCUSDT", "ethereum": "ETHUSDT", "eth": "ETHUSDT",
       "solana": "SOLUSDT", "xrp": "XRPUSDT"}
_N = lambda x: 0.5 * (1 + erf(x / sqrt(2)))


def _num(s):
    s = s.replace(",", "").lower()
    mult = 1000 if s.endswith("k") else 1
    return float(s.rstrip("k")) * mult


def parse(q):
    ql = q.lower()
    if "up or down" in ql:
        return None
    if re.search(r"\bbitcoin\s+(cash|sv|gold)\b|\bethereum\s+classic\b|\b(bch|bsv)\b", ql):
        return None       # different coins that contain "bitcoin"/"ethereum"
    sym = next((v for k, v in SYM.items() if re.search(rf"\b{k}\b", ql)), None)
    px = re.findall(r"\$([\d,]+(?:\.\d+)?k?)", ql)
    if not sym or not px:
        return None
    if "between" in ql and len(px) >= 2:
        return sym, "between", _num(px[0]), _num(px[1])
    if re.search(r"\bdip\b", ql):
        return sym, "dip", _num(px[0]), None
    if re.search(r"\breach\b", ql):
        return sym, "reach", _num(px[0]), None
    if re.search(r"\babove\b|greater than|higher than", ql):
        return sym, "above", _num(px[0]), None
    if re.search(r"\bbelow\b|less than|lower than", ql):
        return sym, "below", _num(px[0]), None
    return None


def _ts(x):
    v = pd.to_datetime(x, utc=True, errors="coerce", format="mixed")
    return None if pd.isna(v) else v.timestamp()


def fair_prob(kind, k1, k2, S, sig_h, hours_left, lo_seen=None, hi_seen=None):
    sd = sig_h * sqrt(max(hours_left, 1e-3))
    if kind == "dip":
        if lo_seen is not None and lo_seen <= k1:
            return 1.0
        return min(1.0, 2 * _N(log(k1 / S) / sd))
    if kind == "reach":
        if hi_seen is not None and hi_seen >= k1:
            return 1.0
        return min(1.0, 2 * _N(-log(k1 / S) / sd))
    if kind == "above":
        return _N(log(S / k1) / sd)
    if kind == "below":
        return _N(log(k1 / S) / sd)
    if kind == "between":
        return _N(log(k2 / S) / sd) - _N(log(k1 / S) / sd)


class CryptoFairValue(Strategy):
    name = "crypto_fair_value"
    origin = "two top crypto-level traders on the Polymarket leaderboard"
    description = "Prices crypto level/touch markets with a volatility model; buys NO when YES is overpriced by more than the edge."
    account_version = 2
    halted = True             # paused 15 Nov 2026 to focus on the up/down markets
    params = dict(edge=0.15, vol_mult=1.0, min_hours_left=6, max_hours_left=24 * 30,
                  min_price=0.05, max_price=0.95, stake_frac=0.08, max_candidates=1500,
                  buy_yes=0, max_same_direction=2)
    interval = 300
    spot_driven = True        # re-evaluate every market when the underlying price moves
    backtest_buckets = ["crypto_level"]
    backtest_step = 3 * 3600
    market_query = dict(kind="events", tag_slug="crypto-prices", days=31)

    def universe(self, m, now):
        if not m.get("outcomes") or m["outcomes"][0] != "Yes":
            return False
        p = parse(m.get("question", ""))
        end = _ts(m.get("end"))
        if not p or not end:
            return False
        h = (end - now) / 3600
        return self.params["min_hours_left"] <= h <= self.params["max_hours_left"]

    def _fair(self, m, t, ctx):
        """Lowest and highest model probability that Yes wins across the volatility range, plus a
        short description; or None when the market cannot be priced."""
        p = parse(m["question"])
        end, start = _ts(m["end"]), _ts(m["start"])
        if not p or not end:
            return None
        sym, kind, k1, k2 = p
        hours_left = (end - t) / 3600
        if not (self.params["min_hours_left"] <= hours_left <= self.params["max_hours_left"]):
            return None
        k = ctx.data.klines(sym, t, 7 * 86400)
        if k is None or len(k) < 100:
            return None
        lr = np.log(k.c).diff().dropna()
        vols = [float(v) * self.params["vol_mult"] for v in (lr.std(), lr.iloc[-24:].std(), lr.iloc[-6:].std()) if v == v and v > 0]
        if not vols:
            return None
        S = ctx.data.spot(sym) if ctx.mode != "backtest" else float(k.c.iloc[-1])
        if hasattr(ctx.data, "extremes"):
            # live: every price since the market opened, including the current hour and the stream
            lo, hi = ctx.data.extremes(sym, start or 0)
            lo, hi = min(lo, S), max(hi, S)
        else:
            seen = k[k.index >= (start or 0)]
            lo = min(seen.l.min(), S) if len(seen) else S
            hi = max(seen.h.max(), S) if len(seen) else S
        fairs = [fair_prob(kind, k1, k2, S, v, hours_left, lo, hi) for v in vols]
        if any(f is None for f in fairs) or max(fairs) >= 0.999:
            return None
        return min(fairs), max(fairs), f"{kind} {sym} K={k1:g} S={S:.2f}"

    @staticmethod
    def direction(question, outcome):
        """+1 if the bet wins when the coin goes up or holds, -1 if it wins when it falls, 0 for range bets."""
        p = parse(question or "")
        if not p:
            return None
        kind = p[1]
        yes = {"reach": 1, "above": 1, "dip": -1, "below": -1}.get(kind, 0)
        return yes if outcome == 0 else -yes

    def prefilter(self, m, ctx):
        """Cheap shortlist from the listing's own quotes, so only promising books are fetched."""
        r = self._fair(m, ctx.now, ctx)
        if not r:
            return False
        lo_f, hi_f, loose = r[0], r[1], self.params["edge"] - 0.10
        ask, bid = m.get("best_ask"), m.get("best_bid")
        if ask is None and bid is None:
            return True
        return (bid is not None and float(bid) - hi_f > loose) or \
               (bool(self.params["buy_yes"]) and ask is not None and lo_f - float(ask) > loose)

    def on_snapshot(self, s, ctx):
        r = self._fair(s.market, s.t, ctx)
        if not r:
            return []
        lo_f, hi_f, desc = r
        e, lo_p, hi_p = self.params["edge"], self.params["min_price"], self.params["max_price"]
        # value of each outcome under the estimate least favourable to it
        sides = [(1, 1 - hi_f)] + ([(0, lo_f)] if self.params["buy_yes"] else [])
        for o, f in sides:
            a = s.ask[o]
            if a is None or not (lo_p <= a <= hi_p) or f - a <= e:
                continue
            d = self.direction(s.market["question"], o)
            same = sum(1 for (cid, out), pos in ctx.portfolio.pos.items() if self.direction(pos.get("question"), out) == d)
            if same >= self.params["max_same_direction"]:
                continue          # already holding enough bets that lose on the same move
            return [Order(o, "BUY", usd=self.size(ctx, a), limit=min(f - e / 2, 0.99),
                          reason=f"{desc} fair {'No' if o else 'Yes'}>={f:.3f} ask={a:.3f}")]
        return []
