"""Paper trader for the latency rule (pmq/strategies/updown_latency.py). Paper only.

Flow:
  1. The Binance perp feed pushes every quote change. A move of `move_bp` over `look_ms` is a signal.
  2. For the current 5-minute market of that coin, a limit order is noted: the side that matches the
     move, priced at the ask the worker sees now plus `max_chase`.
  3. The order "arrives" at Polymarket `order_delay_ms` after the worker received the Binance move.
     Polymarket's book updates reach the worker late, so the fill is decided afterwards, against the
     book as it stood at the arrival moment by Polymarket's own timestamps (feed.Books.top_at).
  4. If the ask at that moment is within the limit, the paper account buys at that ask (limited by
     the size offered there, with the taker fee). If the quote had already moved, nothing is bought.
"""
import asyncio
import collections
import logging
import time

from feed import PerpFeed
from pmq.core import Context, Fill, taker_fee
from pmq.strategies.updown_leader import WINDOW, window_start
from store import iso

log = logging.getLogger("poly")

RESOLVE_EVERY = 0.05          # seconds between checks of waiting orders
FEED_MARGIN_MS = 300          # the book feed must have passed the arrival time by this much
GIVE_UP_MS = 8000             # ...or the order is dropped as "book feed late"
SIGNAL_GAP_MS = 1000          # one signal per coin per second per algo
MAX_OPEN_MARKETS = 12


class LatencyTrader:
    def __init__(self, worker):
        self.w = worker
        self.strategies = [s for s in worker.strategies if getattr(s, "latency_rule", False) and not s.halted]
        self.symbols = sorted({c.upper() + "USDT" for s in self.strategies for c in s.market_query["coins"]})
        self.feed = PerpFeed(self.symbols, self.on_tick)
        self.quotes = {sym: collections.deque() for sym in self.symbols}     # (exchange ms, mid)
        self.last_signal = {}
        self.pending = []
        self.tasks = set()

    @property
    def active(self):
        return bool(self.strategies)

    def tracked_tokens(self):
        return {tok for s in self.strategies for m in self.w.universe[s.name].values() for tok in m["token_ids"]}

    # ------------------------------------------------------------ signal
    def on_tick(self, sym, ts, mid, recv):
        q = self.quotes.get(sym)
        if q is None or not ts:
            return
        q.append((ts, mid))
        look = max(s.params["look_ms"] for s in self.strategies)
        while len(q) > 1 and q[0][0] < ts - look - 2000:
            q.popleft()
        for s in self.strategies:
            p = s.params
            ref = None
            for row in reversed(q):                       # newest quote at least look_ms old
                if row[0] <= ts - p["look_ms"]:
                    ref = row
                    break
            if ref is None or ref[0] < ts - p["look_ms"] - 500:
                continue
            bp = (mid / ref[1] - 1) * 1e4
            if abs(bp) < p["move_bp"]:
                continue
            key = (s.name, sym)
            if ts - self.last_signal.get(key, 0) < SIGNAL_GAP_MS:
                continue
            self.last_signal[key] = ts
            try:
                self.signal(s, sym, bp, ts, recv)
            except Exception as exc:
                self.w.errors[s.name] = f"{type(exc).__name__}: {str(exc)[:160]}"

    def skip(self, s, why, **detail):
        st = self.w.stats[s.name]
        st["skipped"][why] = st["skipped"].get(why, 0) + 1
        if detail:
            st["last_skip"] = dict(at=iso(), why=why, **detail)

    def signal(self, s, sym, bp, ts, recv):
        w, p, st = self.w, s.params, self.w.stats[s.name]
        st["evaluations"] += 1
        now = recv / 1000
        if not w.feed_ok() or (w.lease and not w.lease.fresh()):
            return
        age = recv - ts
        if age < 0:                       # this machine's clock is behind the exchange's: use the usual age
            age = p["binance_age_ms"]
        if age > p["max_signal_age_ms"]:
            return self.skip(s, "binance update arrived late")
        coin = sym[:3].lower()
        market = None
        for m in w.universe[s.name].values():
            start = window_start(m)
            if m.get("slug", "").startswith(coin + "-") and start is not None and start <= now < start + WINDOW:
                market = m
                break
        if market is None:
            return
        start = window_start(market)
        if now - start < p["min_seconds_in"] or start + WINDOW - now < p["min_seconds_left"]:
            return
        acc = w.accounts[s.name]
        cid = market["condition_id"]
        if acc.pf.held(cid) or any(o["cid"] == cid and o["s"] is s for o in self.pending):
            return
        acc.recent_entries = [t for t in acc.recent_entries if now - t < 600]
        if len(acc.recent_entries) >= s.max_new_per_10min:
            return self.skip(s, "pacing")
        outcome = 0 if bp > 0 else 1
        token = market["token_ids"][outcome]
        ladder = w.books.asks(token)
        bid = w.books.best_bid(token)
        if not ladder or bid is None:
            return
        ask = ladder[0][0]
        if not (p["lo"] <= ask <= p["hi"]) or ask - bid > p["max_spread"]:
            return
        st["signals"] += 1
        self.pending.append(dict(s=s, m=market, cid=cid, outcome=outcome, token=token, bp=bp, age=age, ask_seen=ask,
                                 limit=ask + p["max_chase"], arrive=ts + age + p["order_delay_ms"],
                                 give_up=recv + GIVE_UP_MS))

    # ------------------------------------------------------------ fill
    def resolve(self, o):
        """Decide a waiting order against the book as it stood when the order arrived."""
        w, s, m = self.w, o["s"], o["m"]
        acc, p = w.accounts[s.name], s.params
        detail = dict(question=m["question"], outcome=m["outcomes"][o["outcome"]], limit=round(o["limit"], 3),
                      reason=f"perp {o['bp']:+.1f}bp, ask seen {o['ask_seen']:.2f}")
        top = w.books.top_at(o["token"], o["arrive"])
        if top is None:
            return self.skip(s, "no book at arrival", **detail)
        bid, ask, size = top
        if ask is None or ask > o["limit"] + 1e-9:
            return self.skip(s, "quote moved before the order arrived", top_asks=[[ask, size]], **detail)
        if acc.pf.held(o["cid"]):
            return
        if len({k[0] for k in acc.pf.pos}) >= MAX_OPEN_MARKETS:
            return self.skip(s, "max open markets", **detail)
        ctx = Context(acc.pf, now=o["arrive"] / 1000, data=None, mode="paper")
        usd = min(s.size(ctx, ask), acc.pf.cash * 0.999, acc.pf.start_cash * 0.8 - acc.pf.exposure())
        shares = min(usd / ask, size) if usd > 0 else 0
        rate = m.get("fee_rate", 0.0)
        if shares * ask + taker_fee(rate, ask, shares) > acc.pf.cash:
            shares = (acc.pf.cash - 0.01) / (ask * (1 + rate * (1 - ask)))
        if shares * ask < s.min_order_usd:
            return self.skip(s, "below min size", top_asks=[[ask, size]], **detail)
        reason = (f"perp {o['bp']:+.1f}bp in {p['look_ms']}ms, seen after {o['age']:.0f}ms, order +{p['order_delay_ms']}ms; "
                  f"ask seen {o['ask_seen']:.2f}, ask at arrival {ask:.2f}")
        fill = Fill(o["arrive"] / 1000, o["cid"], o["outcome"], "BUY", round(shares, 4), round(ask, 6),
                    taker_fee(rate, ask, shares), reason, m.get("question", ""))
        acc.record_fill(fill, m)
        log.info("[%s] PAPER BUY %.2f '%s' @ %.3f ($%.2f, fee %.4f) | %s | %s", s.name, fill.shares,
                 m["outcomes"][fill.outcome], fill.price, fill.shares * fill.price, fill.fee, m["question"][:70], reason)
        task = asyncio.create_task(w.safe_save(s.name))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def resolve_loop(self):
        while not self.w.stopping:
            await asyncio.sleep(RESOLVE_EVERY)
            if not self.pending:
                continue
            now_ms, waiting = time.time() * 1000, []
            for o in self.pending:
                if self.w.books.last_ts >= o["arrive"] + FEED_MARGIN_MS:
                    try:
                        self.resolve(o)
                    except Exception as exc:
                        self.w.errors[o["s"].name] = f"{type(exc).__name__}: {str(exc)[:160]}"
                elif now_ms >= o["give_up"]:
                    self.skip(o["s"], "book feed late")
                else:
                    waiting.append(o)
            self.pending = waiting

    async def run(self):
        if not self.active:
            return await asyncio.Event().wait()        # nothing to trade: idle until cancelled
        await asyncio.gather(self.feed.run(), self.resolve_loop())
