"""Core objects shared by backtest and paper/live runners.

A strategy only ever sees `Snapshot`s (one market, both outcomes' best bid/ask at time t)
and a `Context` (clock, portfolio, external data). It returns `Order`s. The runner decides
how orders get filled: synthetic spread in backtests, real order-book walk in paper trading,
real CLOB orders in live mode. This keeps one strategy file valid in all three modes.
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Snapshot:
    market: dict           # parsed Gamma market (see api._parse_market)
    t: float               # unix seconds
    bid: list              # best bid per outcome index  [bid0, bid1]
    ask: list              # best ask per outcome index  [ask0, ask1]
    ask_depth: list = field(default_factory=lambda: [None, None])  # full ask ladders when live
    last_trade: Optional[list] = None   # live only: per outcome, (price of the last real trade, its age in seconds) or None

    def mid(self, i):
        b, a = self.bid[i], self.ask[i]
        if b is None or a is None:
            return a if b is None else b
        return (a + b) / 2


@dataclass
class Order:
    outcome: int           # outcome index (0 = first outcome, usually "Yes")
    side: str              # "BUY" or "SELL"
    usd: float = 0.0       # notional for BUY
    shares: float = 0.0    # quantity for SELL (0 = all)
    limit: float = 1.0     # worst acceptable price
    reason: str = ""


@dataclass
class Fill:
    t: float
    cid: str
    outcome: int
    side: str
    shares: float
    price: float
    fee: float
    reason: str
    question: str = ""


def taker_fee(rate, price, shares):
    """Polymarket taker fee: rate * p * (1-p) per share (makers pay nothing)."""
    return round(rate * price * (1 - price) * shares, 5)


class Portfolio:
    def __init__(self, cash):
        self.start_cash = cash
        self.cash = cash
        self.pos = {}          # (cid, outcome) -> dict(shares, cost, question, opened)
        self.fills = []
        self.settled = []      # dicts with realised pnl per position

    def held(self, cid, outcome=None):
        if outcome is None:
            return any(k[0] == cid and v["shares"] > 1e-9 for k, v in self.pos.items())
        p = self.pos.get((cid, outcome))
        return p["shares"] if p else 0.0

    def exposure(self):
        return sum(v["cost"] for v in self.pos.values())

    def apply(self, f: Fill):
        k = (f.cid, f.outcome)
        p = self.pos.setdefault(k, dict(shares=0.0, cost=0.0, question=f.question, opened=f.t))
        if f.side == "BUY":
            self.cash -= f.shares * f.price + f.fee
            p["shares"] += f.shares
            p["cost"] += f.shares * f.price + f.fee
        else:
            frac = f.shares / p["shares"] if p["shares"] else 0
            proceeds = f.shares * f.price - f.fee
            self.cash += proceeds
            realised = proceeds - p["cost"] * frac
            self.settled.append(dict(t=f.t, cid=f.cid, outcome=f.outcome, question=p["question"],
                                     cost=p["cost"] * frac, payout=proceeds, pnl=realised, how="sold"))
            p["cost"] *= (1 - frac)
            p["shares"] -= f.shares
            if p["shares"] <= 1e-9:
                del self.pos[k]
        self.fills.append(f)

    def settle(self, cid, payouts, t):
        """payouts: list of per-share payout per outcome (e.g. [1.0, 0.0])."""
        for (c, o), p in list(self.pos.items()):
            if c != cid:
                continue
            pay = p["shares"] * payouts[o]
            self.cash += pay
            self.settled.append(dict(t=t, cid=cid, outcome=o, question=p["question"], cost=p["cost"],
                                     payout=pay, pnl=pay - p["cost"], how="resolved"))
            del self.pos[(c, o)]

    def equity(self, marks):
        """marks: (cid, outcome) -> price used to value open positions."""
        return self.cash + sum(p["shares"] * marks.get(k, p["cost"] / max(p["shares"], 1e-9))
                               for k, p in self.pos.items())


class Context:
    def __init__(self, portfolio, now=0.0, data=None, mode="backtest"):
        self.portfolio = portfolio
        self.now = now
        self.data = data          # mode-specific data provider (klines etc.)
        self.mode = mode


class Strategy:
    """Subclass and override. Keep strategies stateless beyond self.params where possible."""
    name = "base"
    description = ""
    origin = ""               # which wallets this was reverse-engineered from
    params = {}
    interval = 300            # live: seconds between evaluations
    account_version = 1       # bump when the rules change: the paper account restarts and the old one is archived
    backtest_buckets = []     # which price-path buckets in data/prices.pkl to replay
    backtest_step = 3600      # backtest: seconds between evaluations
    market_query = dict(kind="markets", days=7)   # live: which Gamma slice to scan (see api.market_query)

    def __init__(self, **overrides):
        self.params = {**self.params, **overrides}

    def universe(self, m, now) -> bool:
        """Cheap metadata filter: should this market be watched at all?"""
        return True

    def prefilter(self, m, ctx) -> bool:
        """Optional shortlist using the listing's own best bid/ask, before books are fetched."""
        return True

    def on_snapshot(self, s: Snapshot, ctx: Context) -> list:
        return []

    def size(self, ctx, price):
        """Default sizing: fixed fraction of starting bankroll, at least the 5-share minimum."""
        if ctx.mode == "backtest" and "_stake_override" in self.params:
            usd = self.params["_stake_override"]
        else:
            usd = self.params.get("stake_frac", 0.05) * ctx.portfolio.start_cash
        if getattr(self, "min_order_usd", None):       # marketable orders: a dollar minimum, not 5 shares
            return max(usd, self.min_order_usd * 1.1)
        return max(usd, 5 * price * 1.02)
