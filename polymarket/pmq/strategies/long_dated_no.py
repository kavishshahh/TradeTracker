"""Long-dated "No"  (calibration study of resolved Polymarket markets, Nov 2026).

In Yes/No markets with a month or more to the scheduled end, "Yes" priced 35-65c won less often than its
price: buying "No" at real trade prices gained about 5c a share in markets ending Apr-Nov 2026 (551 events)
and about 6c in an unseen earlier year (666 events). Nothing was found in markets with under 30 days left.
The study used past trade prices, mostly before fees began, so the live bid/ask and today's fee are what
this paper account measures. Money is tied up for months and each bet is close to a coin flip, so a few
hundred settled events are needed before the result means anything.
=> EXPERIMENTAL. Paper only.
"""
import pandas as pd

from ..core import Strategy, Order


def _ts(x):
    v = pd.to_datetime(x, utc=True, errors="coerce", format="mixed")
    return None if pd.isna(v) else v.timestamp()


class LongDatedNo(Strategy):
    name = "long_dated_no"
    origin = "a calibration study of resolved Polymarket markets"
    description = "Buys No when Yes is priced 0.35-0.65 with 30+ days to the scheduled end."
    params = dict(lo=0.35, hi=0.65, min_days_left=30, min_age_days=4, min_volume_24h=100, max_spread=0.03, stake_usd=2.0)
    bankroll = 1000.0           # a measuring account: about 500 bets of $2, each held for months
    risk = dict(max_open_markets=600, max_order_usd=4.0, max_exposure_usd=1000.0)
    min_order_usd = 1.0         # marketable orders: $1 minimum
    max_new_per_10min = 30
    scan_every = 1800           # the listing is ~6,000 markets: read it every 30 minutes, not every 2
    market_query = dict(kind="markets", days=800, volume_num_min=5000)

    def size(self, ctx, price):
        return max(self.params["stake_usd"], self.min_order_usd * 1.1)

    def universe(self, m, now):
        p = self.params
        if [str(o).lower() for o in m.get("outcomes") or []] != ["yes", "no"]:
            return False
        if m.get("sports_type") or str(m.get("fee_type") or "").startswith("sports"):
            return False
        start, end = _ts(m.get("start")), _ts(m.get("end"))
        if start is None or end is None:
            return False
        return (now - start >= p["min_age_days"] * 86400 and end - now >= p["min_days_left"] * 86400
                and float(m.get("volume24h") or 0) >= p["min_volume_24h"])

    def prefilter(self, m, ctx):
        bid, ask = m.get("best_bid"), m.get("best_ask")
        if bid is None or ask is None:
            return False
        return self.params["lo"] - 0.03 <= (float(bid) + float(ask)) / 2 <= self.params["hi"] + 0.03

    def on_snapshot(self, s, ctx):
        p = self.params
        if None in (s.bid[0], s.ask[0], s.bid[1], s.ask[1]):
            return []
        yes = (s.bid[0] + s.ask[0]) / 2
        if not p["lo"] <= yes <= p["hi"] or s.ask[1] - s.bid[1] > p["max_spread"] + 1e-9:
            return []
        end = _ts(s.market.get("end"))
        days = (end - s.t) / 86400 if end else 0
        return [Order(1, "BUY", usd=self.size(ctx, s.ask[1]), limit=s.ask[1],
                      reason=f"No @ {s.ask[1]:.3f} (Yes mid {yes:.3f}, spread {(s.ask[1] - s.bid[1]) * 100:.1f}c, {days:.0f} days left)")]
