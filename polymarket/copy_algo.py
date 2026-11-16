"""Paper trader that copies other wallets' buys (pmq/strategies/copy_wallet.py). Paper only.

Flow:
  1. Polymarket's public live-activity WebSocket pushes every trade on the exchange (about 30 a
     second) with the trader's wallet. Trades by a copied wallet are picked out as they arrive.
  2. On a qualifying buy in a market the account does not hold, the market's settings come from
     `GET clob.polymarket.com/clob-markets/{condition_id}`: outcomes and tokens, taker fee rate,
     game start, the sports order delay (`sd`, seconds) and the crypto taker delay flag (`itode`).
  3. The copy order "arrives" at Polymarket at: the time the trade reached the feed + how late the feed
     message reached this machine + `order_delay_ms` + the market's taker delay (`sd` seconds once
     the game has started, 250 ms on `itode` markets).
  4. A short-lived order-book WebSocket for that token gives the book with Polymarket's own
     timestamps. The order fills against the asks as they stood at the arrival time, up to the
     wallet's price plus `max_chase`, with the taker fee. If the asks moved past that, nothing is bought.
"""
import asyncio
import json
import logging
import time
from datetime import datetime

import websockets

from feed import POLY_WS
from pmq import api
from pmq.core import Context, Fill, taker_fee
from store import iso

log = logging.getLogger("poly")

RTDS_WS = "wss://ws-live-data.polymarket.com"
ITODE_MS = 250                # taker delay on markets flagged `itode` (crypto up/down)
BOOK_TIMEOUT = 15             # seconds to wait for the book to pass the arrival time
SEEN_KEEP = 20000             # markets remembered as already considered


def _ts(v):
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp() if v else None
    except ValueError:
        return None


class CopyTrader:
    def __init__(self, worker):
        self.w = worker
        self.strategies = [s for s in worker.strategies if getattr(s, "copy_rule", False) and not s.halted]
        self.by_wallet = {}
        for s in self.strategies:
            self.by_wallet.setdefault(s.params["wallet"].lower(), []).append(s)
        self.seen = {s.name: {} for s in self.strategies}      # cid -> time first considered
        self.tasks = set()
        self.connected = False
        self.messages = 0
        self.last_message = 0.0
        self.stopping = False

    @property
    def active(self):
        return bool(self.strategies)

    def skip(self, s, why, **detail):
        st = self.w.stats[s.name]
        st["skipped"][why] = st["skipped"].get(why, 0) + 1
        log.info("[%s] copy skipped: %s | %s", s.name, why, {k: v for k, v in detail.items() if k != "question"} | {"q": str(detail.get("question", ""))[:60]})
        if detail:
            st["last_skip"] = dict(at=iso(), why=why, **detail)

    def _spawn(self, coro):
        task = asyncio.create_task(coro)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    # ------------------------------------------------------------ feed
    async def run(self):
        if not self.active:
            return await asyncio.Event().wait()        # nothing to copy: idle until cancelled
        delay = 1
        while not self.stopping and not self.w.stopping:
            try:
                async with websockets.connect(RTDS_WS, max_size=None, ping_interval=None, open_timeout=20) as ws:
                    await ws.send(json.dumps({"action": "subscribe", "subscriptions": [{"topic": "activity", "type": "trades"}]}))
                    self.connected, delay = True, 1
                    try:
                        while not self.stopping and not self.w.stopping:
                            try:
                                raw = await asyncio.wait_for(ws.recv(), 10)
                            except asyncio.TimeoutError:
                                await ws.send("PING")
                                continue
                            if not raw or raw == "PONG":
                                continue
                            recv = time.time() * 1000
                            self.messages += 1
                            self.last_message = recv / 1000
                            try:
                                d = json.loads(raw)
                            except ValueError:
                                continue
                            p = d.get("payload") or {}
                            group = self.by_wallet.get((p.get("proxyWallet") or "").lower())
                            if group:
                                for s in group:
                                    try:
                                        self.on_trade(s, p, int(d.get("timestamp") or 0), recv)
                                    except Exception as exc:
                                        self.w.errors[s.name] = f"{type(exc).__name__}: {str(exc)[:160]}"
                    finally:
                        self.connected = False
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("activity_feed_reconnect error=%s", type(exc).__name__)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30)

    # ------------------------------------------------------------ signal
    def on_trade(self, s, p, feed_ms, recv):
        w, prm, st = self.w, s.params, self.w.stats[s.name]
        st["evaluations"] += 1                         # wallet trades seen
        cid, price = p.get("conditionId"), float(p.get("price") or 0)
        usd = price * float(p.get("size") or 0)
        detail = dict(question=p.get("title", ""), outcome=p.get("outcome"), their_price=price, their_usd=round(usd, 2))
        if p.get("side") != "BUY" or not cid:
            return
        if usd < prm["min_their_usd"]:
            return                                     # dust fills: not counted as a skip
        seen = self.seen[s.name]
        if cid in seen:
            return                                     # only their first qualifying buy per market
        seen[cid] = time.time()
        if len(seen) > SEEN_KEEP:
            for k in sorted(seen, key=seen.get)[: SEEN_KEEP // 4]:
                del seen[k]
        acc = w.accounts[s.name]
        if acc.pf.held(cid):
            return
        if price >= prm["max_price"] or price <= prm["min_price"]:
            return self.skip(s, "price outside range", **detail)
        if w.lease and not w.lease.fresh():
            return
        if len({k[0] for k in acc.pf.pos}) >= s.max_open_markets:
            return self.skip(s, "max open markets", **detail)
        st["signals"] += 1
        lag = recv - feed_ms if feed_ms and recv >= feed_ms else 0      # this machine's clock may run behind
        sig = dict(s=s, p=p, cid=cid, token=p.get("asset"), outcome=int(p.get("outcomeIndex") or 0), price=price,
                   usd=usd, feed_ms=feed_ms or recv, lag=lag, detail=detail)
        self._spawn(self.copy(sig))

    # ------------------------------------------------------------ fill
    async def copy(self, o):
        s = o["s"]
        try:
            info = await asyncio.to_thread(api._req, "GET", f"{api.CLOB}/clob-markets/{o['cid']}", 2)
        except Exception as exc:
            return self.skip(s, "market info failed", error=type(exc).__name__, **o["detail"])
        if not info or not info.get("ao", True):
            return self.skip(s, "market not accepting orders", **o["detail"])
        game_start = _ts(info.get("gst"))
        in_play = bool(game_start and o["feed_ms"] / 1000 >= game_start)
        sport_delay = float(info.get("sd") or 0) * 1000 if in_play else 0
        taker_delay = max(sport_delay, ITODE_MS if info.get("itode") else 0)
        arrive = o["feed_ms"] + o["lag"] + s.params["order_delay_ms"] + taker_delay
        o.update(info=info, in_play=in_play, taker_delay=taker_delay, arrive=arrive)
        book, book_ts = await self.book_at(o["token"], arrive)
        if book is None:
            return self.skip(s, "no book", **o["detail"])
        o["book_late_ms"] = max(0, book_ts - arrive)
        self.fill(o, book)

    async def book_at(self, token, arrive):
        """Ask ladder {price: size} as of Polymarket time `arrive` (ms) and the time of that state.
        If the first snapshot is already later than `arrive`, that snapshot is used."""
        book, at = None, 0
        try:
            async with websockets.connect(POLY_WS, max_size=None, ping_interval=None, open_timeout=10) as ws:
                await ws.send(json.dumps({"assets_ids": [token], "type": "market"}))
                end = time.time() + BOOK_TIMEOUT
                while time.time() < end:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), max(0.1, end - time.time()))
                    except asyncio.TimeoutError:
                        break
                    if raw == "PONG":
                        continue
                    data = json.loads(raw)
                    for e in data if isinstance(data, list) else [data]:
                        ts = int(e.get("timestamp") or 0)
                        kind = e.get("event_type")
                        if kind == "book" and e.get("asset_id") == token:
                            if book is not None and ts > arrive:
                                return book, at
                            book = {float(x["price"]): float(x["size"]) for x in e.get("asks", [])}
                            at = ts
                            if ts >= arrive:
                                return book, at
                        elif kind == "price_change" and book is not None:
                            changes = [c for c in e.get("price_changes", []) if c.get("asset_id") == token and c.get("side") != "BUY"]
                            if not changes:
                                continue
                            if ts > arrive:
                                return book, at
                            for c in changes:
                                price, size = float(c["price"]), float(c["size"])
                                if size <= 0:
                                    book.pop(price, None)
                                else:
                                    book[price] = size
                            at = ts
        except Exception as exc:
            log.warning("copy_book_failed error=%s", type(exc).__name__)
        return book, at

    def fill(self, o, asks):
        w, s, info = self.w, o["s"], o["info"]
        acc, prm = w.accounts[s.name], s.params
        if acc.pf.held(o["cid"]):
            return
        limit = min(o["price"] + prm["max_chase"], 0.99)
        ladder = sorted((p, q) for p, q in asks.items() if p <= limit + 1e-9)
        best = min(asks) if asks else None
        detail = dict(o["detail"], limit=round(limit, 3), top_asks=sorted(asks.items())[:3], in_play=o["in_play"])
        if not ladder:
            return self.skip(s, "price moved before the order arrived", **detail)
        ctx = Context(acc.pf, now=o["arrive"] / 1000, data=None, mode="paper")
        budget = min(s.size(ctx, ladder[0][0]), acc.pf.cash * 0.95, acc.pf.start_cash * 0.8 - acc.pf.exposure())
        if budget < s.min_order_usd:
            return self.skip(s, "no cash", **detail)
        shares = cost = 0.0
        for p, q in ladder:                            # walk the asks up to the limit
            take = min(q, (budget - cost) / p)
            if take <= 0:
                break
            shares += take
            cost += take * p
        if cost < s.min_order_usd:
            return self.skip(s, "too little size under the limit", **detail)
        avg = cost / shares
        rate = float((info.get("fd") or {}).get("r") or 0)
        fee = taker_fee(rate, avg, shares)
        tokens = info.get("t") or []
        outcomes = [t.get("o") for t in tokens] or [o["p"].get("outcome")]
        token_ids = [t.get("t") for t in tokens] or [o["token"]]
        outcome = token_ids.index(o["token"]) if o["token"] in token_ids else o["outcome"]
        market = dict(question=o["p"].get("title", ""), outcomes=outcomes, token_ids=token_ids,
                      event_slug=o["p"].get("eventSlug"), end=info.get("gst"))
        reason = (f"they bought {o['p'].get('outcome')} @ {o['price']:.3f} (${o['usd']:.0f}); "
                  f"{'in-play' if o['in_play'] else 'pre-game'}; feed lag {o['lag']:.0f}ms + order {prm['order_delay_ms']}ms"
                  f" + taker delay {o['taker_delay']:.0f}ms; best ask then {best:.3f}; book {o['book_late_ms']:.0f}ms after arrival")
        f = Fill(o["arrive"] / 1000, o["cid"], outcome, "BUY", round(shares, 4), round(avg, 6), fee, reason, market["question"])
        acc.record_fill(f, market)
        log.info("[%s] PAPER BUY %.2f '%s' @ %.3f ($%.2f, fee %.4f) | %s | %s", s.name, f.shares, outcomes[outcome],
                 f.price, cost, fee, market["question"][:70], reason)
        self._spawn(w.safe_save(s.name))
