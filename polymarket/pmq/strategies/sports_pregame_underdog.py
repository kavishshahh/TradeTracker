"""Sports pre-game underdog  (reverse-engineered from a top sports wallet on the leaderboard).

The wallet this is modelled on made most of its money buying 0.10-0.50 priced sides of NFL / college-football
games in the last ~2h before kickoff. Calibration on 1.5k moneyline + 1.5k spread/total
markets (Jun-Nov 2026) shows pre-game longshots win more often than their price implies
(favourite-longshot bias runs the "wrong" way on Polymarket sports).
Held-out backtest: +7%/bet as taker (not significant), +30%/bet with maker fills.
=> EXPERIMENTAL. Paper-test before risking money.
"""
import pandas as pd

from ..core import Strategy, Order


def _ts(x):
    v = pd.to_datetime(x, utc=True, errors="coerce", format="mixed")
    return None if pd.isna(v) else v.timestamp()


class SportsPregameUnderdog(Strategy):
    name = "sports_pregame_underdog"
    origin = "a top sports trader on the Polymarket leaderboard"
    description = "Buys the cheaper side (0.10-0.40) of moneyline/spread/total markets 10-240 min before kickoff."
    params = dict(min_minutes=10, max_minutes=240, lo=0.10, hi=0.40, max_spread=0.03,
                  stake_frac=0.06, max_candidates=300)
    interval = 300
    backtest_buckets = ["sports_ml", "sports_line"]
    backtest_step = 600
    market_query = dict(kind="markets", days=1, sports_market_types=["moneyline"])   # moneyline only: keeps a cycle light

    def _mins(self, m, now):
        gs = _ts(m.get("game_start"))
        return None if gs is None else (gs - now) / 60

    def universe(self, m, now):
        if m.get("sports_type") not in ("moneyline", "child_moneyline", "spreads", "totals"):
            return False
        mins = self._mins(m, now)
        return mins is not None and self.params["min_minutes"] <= mins <= self.params["max_minutes"]

    def prefilter(self, m, ctx):
        ask, bid = m.get("best_ask"), m.get("best_bid")
        if ask is None or bid is None:
            return True
        lo, hi = self.params["lo"] - 0.05, self.params["hi"] + 0.05
        return lo <= float(ask) <= hi or lo <= 1 - float(bid) <= hi

    def on_snapshot(self, s, ctx):
        mins = self._mins(s.market, s.t)
        if mins is None or not (self.params["min_minutes"] <= mins <= self.params["max_minutes"]):
            return []
        best = None
        for o in (0, 1):
            a, b = s.ask[o], s.bid[o]
            if a is None or b is None or a - b > self.params["max_spread"]:
                continue
            if self.params["lo"] <= a <= self.params["hi"] and (best is None or a < s.ask[best]):
                best = o
        if best is None:
            return []
        a = s.ask[best]
        return [Order(best, "BUY", usd=self.size(ctx, a), limit=a + 0.01,
                      reason=f"underdog {s.market['outcomes'][best]} @ {a:.3f}, {mins:.0f}m to start")]
