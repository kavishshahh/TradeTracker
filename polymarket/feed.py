"""Live market data: Polymarket order-book WebSocket and Binance price WebSocket.

Both feeds push updates; nothing here polls. `Books` keeps a local copy of every subscribed
order book (snapshot on subscribe, then per-level changes) and reports which tokens changed.
"""
import asyncio
import json
import logging
import time

import websockets

log = logging.getLogger(__name__)

POLY_WS = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
BINANCE_WS = "wss://data-stream.binance.vision/stream?streams="
CHUNK = 400               # tokens per Polymarket connection


class Books:
    def __init__(self):
        self.b = {}           # token -> {"bids": {price: size}, "asks": {price: size}}
        self.top = {}         # token -> (best bid, best ask) last seen; decisions only depend on these
        self.trades = {}      # token -> (price, received at) of the last real trade
        self.dirty = set()
        self.event = asyncio.Event()
        self.last_message = 0.0
        self.messages = 0

    def reset(self):
        self.b.clear()
        self.top.clear()

    def _touch(self, token):
        self.dirty.add(token)
        self.event.set()

    def on_event(self, e):
        kind = e.get("event_type")
        if kind == "book":
            self.b[e["asset_id"]] = dict(
                bids={float(x["price"]): float(x["size"]) for x in e.get("bids", [])},
                asks={float(x["price"]): float(x["size"]) for x in e.get("asks", [])})
            self._touch(e["asset_id"])
        elif kind == "last_trade_price":
            try:
                self.trades[e["asset_id"]] = (float(e["price"]), time.time())
                self._touch(e["asset_id"])
            except (KeyError, TypeError, ValueError):
                pass
        elif kind == "price_change":
            for c in e.get("price_changes", []):
                book = self.b.get(c["asset_id"])
                if book is None:
                    continue          # no snapshot yet: wait for it rather than guess
                side = book["bids"] if c["side"] == "BUY" else book["asks"]
                price, size = float(c["price"]), float(c["size"])
                if size <= 0:
                    side.pop(price, None)
                else:
                    side[price] = size
                # Wake on a new top of book, or on a size change at or just behind the best ask (a fill
                # can be refused for lack of size there). Deeper changes cannot change a decision.
                top = (c.get("best_bid"), c.get("best_ask"))
                try:
                    near_ask = c["side"] != "BUY" and price <= float(c["best_ask"]) + 0.02
                except (KeyError, TypeError, ValueError):
                    near_ask = True
                if near_ask or self.top.get(c["asset_id"]) != top or top == (None, None):
                    self.top[c["asset_id"]] = top
                    self._touch(c["asset_id"])

    def take_dirty(self):
        out, self.dirty = self.dirty, set()
        self.event.clear()
        return out

    def last_trade(self, token, other, now):
        """Most recent real trade for this outcome as (price, age seconds). A trade in the opposite
        outcome at p is the same information as this one at 1 - p."""
        own, opp = self.trades.get(token), self.trades.get(other)
        cands = [x for x in (own, (1 - opp[0], opp[1]) if opp else None) if x]
        if not cands:
            return None
        price, at = max(cands, key=lambda x: x[1])
        return price, now - at

    def best_bid(self, token):
        book = self.b.get(token)
        return max(book["bids"]) if book and book["bids"] else None

    def asks(self, token):
        """Ask ladder best-first as [(price, size)], or None when no snapshot has arrived."""
        book = self.b.get(token)
        return None if book is None else sorted(book["asks"].items())


class BookFeed:
    """Keeps `Books` in sync for a changing set of tokens, reconnecting on any failure."""
    def __init__(self, books):
        self.books = books
        self.tokens = []
        self.tasks = []
        self.live = set()         # connections of the current token set that are open
        self._stop = None         # tells the current connections to end
        self.stopping = False

    @property
    def connected(self):
        return len(self.live)

    async def set_tokens(self, tokens):
        tokens = sorted(set(tokens))
        if tokens == self.tokens:
            return
        # A cancel can be swallowed (asyncio.wait_for on Python 3.11 when a message arrives at the same
        # moment), so the old connections also get a stop flag and the wait for them is bounded. Waiting
        # without a limit once froze the market refresh for good.
        if self._stop is not None:
            self._stop.set()
        for t in self.tasks:
            t.cancel()
        if self.tasks:
            _, pending = await asyncio.wait(self.tasks, timeout=5)
            if pending:
                log.warning("book_feed_slow_close connections=%d", len(pending))
        self.tokens, self.live, self._stop = tokens, set(), asyncio.Event()
        self.books.reset()
        self.tasks = [asyncio.create_task(self._run(tokens[i:i + CHUNK], self._stop, self.live))
                      for i in range(0, len(tokens), CHUNK)]

    async def _run(self, tokens, stop, live):
        delay, me = 1, object()
        while not self.stopping and not stop.is_set():
            try:
                async with websockets.connect(POLY_WS, max_size=None, ping_interval=None, open_timeout=20) as ws:
                    await ws.send(json.dumps({"assets_ids": tokens, "type": "market"}))
                    live.add(me)
                    delay = 1
                    try:
                        while not self.stopping and not stop.is_set():
                            try:
                                raw = await asyncio.wait_for(ws.recv(), 10)
                            except asyncio.TimeoutError:
                                await ws.send("PING")
                                continue
                            if stop.is_set():
                                break             # replaced by a newer token set: its books are not ours
                            if raw == "PONG":
                                continue
                            data = json.loads(raw)
                            self.books.last_message = time.time()
                            for e in data if isinstance(data, list) else [data]:
                                self.books.messages += 1
                                self.books.on_event(e)
                    finally:
                        live.discard(me)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if stop.is_set():
                    return
                log.warning("book_feed_reconnect error=%s", type(exc).__name__)
                # Stale levels must not be traded on: drop this connection's books until re-snapshotted.
                for t in tokens:
                    self.books.b.pop(t, None)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30)


class SpotFeed:
    """Latest trade price per Binance symbol, pushed about once a second."""
    def __init__(self, symbols):
        self.symbols = symbols
        self.price = {}
        self.at = {}
        self.event = asyncio.Event()
        self.range = {}       # sym -> {10-minute bucket start: [low, high]} for the last few hours

    def extremes(self, sym, start):
        """(low, high) seen on the stream in buckets that end after `start`; (inf, -inf) if none."""
        rows = [v for b, v in self.range.get(sym, {}).items() if b + 600 > start]
        return (min(v[0] for v in rows), max(v[1] for v in rows)) if rows else (float("inf"), float("-inf"))

    def get(self, sym, max_age=30):
        if sym in self.price and time.time() - self.at[sym] <= max_age:
            return self.price[sym]
        return None

    async def run(self):
        url = BINANCE_WS + "/".join(f"{s.lower()}@miniTicker" for s in self.symbols)
        delay = 1
        while True:
            try:
                async with websockets.connect(url, open_timeout=20) as ws:
                    delay = 1
                    async for raw in ws:
                        d = json.loads(raw).get("data", {})
                        if "s" in d:
                            now = time.time()
                            self.price[d["s"]] = float(d["c"])
                            self.at[d["s"]] = now
                            # miniTicker carries the last price each second; keep its range per 10 minutes
                            buckets = self.range.setdefault(d["s"], {})
                            b = int(now // 600) * 600
                            lo_hi = buckets.setdefault(b, [float(d["c"]), float(d["c"])])
                            lo_hi[0], lo_hi[1] = min(lo_hi[0], float(d["c"])), max(lo_hi[1], float(d["c"]))
                            if len(buckets) > 24:
                                for old in sorted(buckets)[:-24]:
                                    del buckets[old]
                            self.event.set()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("spot_feed_reconnect error=%s", type(exc).__name__)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30)
