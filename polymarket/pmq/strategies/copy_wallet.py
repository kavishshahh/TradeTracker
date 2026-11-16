"""Copy another Polymarket wallet's buys (paper).

The wallet's trades come from Polymarket's public live-activity WebSocket. When the wallet buys into
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


class CopySubstantialService(CopyWallet):
    """Wallet checked on 16 Nov 2026: +$6.1M all-time on $1.44B volume (about 0.4%), +$3.1M in the
    last month, worst drawdown -$4.6M. Mostly sports, about half bought during games. Expected to
    lose to copy delay; this account measures by how much."""
    name = "copy_substantial_service"
    description = "Copies the first buy in each market by Substantial-Service (0x2c33...0563), a large sports trader, at the price we could actually get after the delay."
    origin = "wallet 0x2c335066fe58fe9237c3d3dc7b275c2a034a0563"
    params = dict(CopyWallet.params, wallet="0x2c335066fe58fe9237c3d3dc7b275c2a034a0563")


# Three slower pregame wallets screened on 17 Nov 2026 (copy backtest on 80 recent first entries each,
# price-history price 10 min later plus 1c: about +61% / +28% / +24% per bet, wide error bars and
# picked for looking good, so paper only). Their typical fill is $11-22, so the size filter is $5.

class CopyC8b9Politics(CopyWallet):
    """Elections/politics, about 3 new markets a day, holds about 2 weeks: more open markets, smaller bets."""
    name = "copy_c8b9_politics"
    description = "Copies the first buy in each market by wallet 0xc8b9...b836, an elections and politics trader who holds for weeks."
    origin = "wallet 0xc8b9a30184244d427169cf62485dde6041b2b836"
    max_open_markets = 18
    params = dict(CopyWallet.params, wallet="0xc8b9a30184244d427169cf62485dde6041b2b836", min_their_usd=5.0, stake_usd=1.1)


class CopyGooolEsports(CopyWallet):
    """CS2/LoL before the match, about 6 new markets a day."""
    name = "copy_goool_esports"
    description = "Copies the first buy in each market by Gooooooollllllllll (0xda3a...381f), a CS2 and League of Legends pregame trader."
    origin = "wallet 0xda3a9b7afff7b44ad4fd75308723194e0a11381f"
    params = dict(CopyWallet.params, wallet="0xda3a9b7afff7b44ad4fd75308723194e0a11381f", min_their_usd=5.0)


class Copy6e82Nba(CopyWallet):
    """NBA/WNBA before the game, about 2 new markets a day."""
    name = "copy_6e82_nba"
    description = "Copies the first buy in each market by wallet 0x6e82...752c, an NBA pregame trader."
    origin = "wallet 0x6e82b93eb57b01a63027bd0c6d2f3f04934a752c"
    params = dict(CopyWallet.params, wallet="0x6e82b93eb57b01a63027bd0c6d2f3f04934a752c", min_their_usd=5.0)
