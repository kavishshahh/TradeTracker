"""Copy another Polymarket wallet's buys (paper).

The wallet's trades come from Polymarket's public live-activity WebSocket, which only names the taker
of each trade, and from Polygon's fill events, which also catch the wallet's resting (maker) orders
being filled. When the wallet buys into
a market we do not hold, the paper account sends a limit buy at the wallet's price plus `max_chase`.
The order is taken to reach Polymarket `order_delay_ms` after the trade showed up on the feed, plus
the market's own taker delay (the sports delay `sd` once the game has started, 250 ms on markets
flagged `itode`). It fills against the market's real ask ladder as it stood at that moment, by
Polymarket's timestamps, up to the limit. If the price has moved past the limit, nothing is bought.

Rules: only the wallet's first qualifying buy in each market is copied (they often split one bet
into many fills and sometimes buy both sides); buys at or above `max_price` are skipped (buying at
98-99.9c once a result is known needs their speed and size); fills under `min_their_usd` are
ignored. Positions are held to resolution, like the wallet does.

Traded by copy_algo.CopyTrader, never through on_snapshot. Add another wallet by subclassing with a
new `name` and `params["wallet"]`.
"""
from ..core import Strategy


class CopyWallet(Strategy):
    copy_rule = True            # traded by copy_algo.CopyTrader, not by the snapshot loop or the market scan
    min_order_usd = 1.0         # marketable orders: $1 minimum
    max_open_markets = 15
    backtest_buckets = []
    market_query = dict(kind="none")
    params = dict(wallet="", order_delay_ms=350, max_chase=0.02, max_price=0.97, min_price=0.03,
                  min_their_usd=20.0, stake_usd=1.5)

    def size(self, ctx, price):
        return max(self.params["stake_usd"], self.min_order_usd * 1.1)


# Removed 19 Nov 2026 after three days of paper trading (accounts and ledger rows purged):
#   copy_substantial_service (0x2c33...0563, in-play sports): 51 bets, 45% won, -$13.68 of $25. Copy delay.
#   copy_goool_esports (0xda3a...381f, CS2/LoL pregame): 7 bets, 2 won, -$4.61. Its screen was 80 entries
#     picked for looking good; research/screen_copy_wallets.py rejects it (t 1.3, older half +3%).
#   copy_6e82_nba (0x6e82...752c): had stopped trading; its profit was old bets settling.
# The same screen found no replacement: the two wallets that passed on the last 45 days lost money when
# copied on their bets from 45-120 days earlier. Run that script before adding a wallet here.

class CopyC8b9Politics(CopyWallet):
    """Elections/politics, about 3 new markets a day, holds about 2 weeks: more open markets, smaller bets."""
    name = "copy_c8b9_politics"
    description = "Copies the first buy in each market by wallet 0xc8b9...b836, an elections and politics trader who holds for weeks."
    origin = "wallet 0xc8b9a30184244d427169cf62485dde6041b2b836"
    max_open_markets = 18
    params = dict(CopyWallet.params, wallet="0xc8b9a30184244d427169cf62485dde6041b2b836", min_their_usd=5.0, stake_usd=1.1)
