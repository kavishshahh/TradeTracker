"""5-minute up/down leader  (from the account owner's own manual trading pattern).

In a "Bitcoin/Ethereum Up or Down" 5-minute market, once one side is clearly ahead late in the
window, buy that side and hold the few minutes to resolution.

Backtest on 3,442 BTC+ETH markets (8-14 Nov 2026, every fill; fills taken at the next print after
the signal plus 1c, real 7% crypto fee curve). Held-out last 40%:
  last 180s, 70-95c : 86% wins at 80c avg  -> +5.2% per bet (t 3.9); positive on all 6 days
  last 285s, 70-95c : 81% wins at 73c avg  -> +7.8% per bet (t 5.0)
Where the edge is: entries below ~85c. Above 90c the edge is about zero after 1c of slippage.
BTC is stronger than ETH. The last 60 seconds were slightly negative.
Not found useful: a Binance-based fair-value filter and a 30s momentum filter.

Two registered variants run as separate paper accounts so they can be compared live:
  updown_leader_3m    - the pattern as traded by hand: last 3 minutes, 70c or more.
  updown_leader_early - any time after the first 15s, 70-90c only (skips the no-edge 90c+ zone).
"""
from ..core import Strategy, Order

WINDOW = 300


def window_start(m):
    try:
        return int(m["slug"].rsplit("-", 1)[1])
    except (KeyError, IndexError, ValueError):
        return None


class UpDownLeader(Strategy):
    origin = "your own manual trades"
    interval = 1
    time_driven = True          # re-check every second: time left matters even when the book is still
    always_stream = True
    max_new_per_10min = 8
    min_order_usd = 1.0         # marketable orders on Polymarket need $1, not 5 shares
    backtest_buckets = []
    market_query = dict(kind="updown5m", coins=["btc", "eth"])
    params = dict(max_seconds_left=180, min_seconds_left=20, lo=0.70, hi=0.98, max_spread=0.03, stake_frac=0.08)

    def universe(self, m, now):
        start = window_start(m)
        return start is not None and start - 600 <= now < start + WINDOW

    def on_snapshot(self, s, ctx):
        start = window_start(s.market)
        if start is None:
            return []
        left = start + WINDOW - s.t
        p = self.params
        if not (p["min_seconds_left"] <= left <= p["max_seconds_left"]):
            return []
        for o in (0, 1):
            a, b = s.ask[o], s.bid[o]
            if a is None or b is None or a - b > p["max_spread"]:
                continue
            if p["lo"] <= a <= p["hi"]:
                return [Order(o, "BUY", usd=self.size(ctx, a), limit=min(a + 0.02, 0.99),
                              reason=f"leader {s.market['outcomes'][o]} @ {a:.2f}, {left:.0f}s left")]
        return []


class UpDownLeader3m(UpDownLeader):
    name = "updown_leader_3m"
    description = "5-minute BTC/ETH up/down: in the last 3 minutes, buy the side priced 70c or more and hold to resolution."


class UpDownLeaderEarly(UpDownLeader):
    name = "updown_leader_early"
    description = "5-minute BTC/ETH up/down: any time after the first 15s, buy the side priced 70-90c and hold to resolution."
    params = dict(UpDownLeader.params, max_seconds_left=285, hi=0.90)
