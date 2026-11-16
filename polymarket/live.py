"""Real orders for the latency rule. OFF unless POLY_LIVE=1 and the session key are set on the host.

What it does: every time the paper trader (latency_algo.py) notes an order for LIVE_STRATEGY, the
same order is sent to Polymarket at once as a fill-and-kill buy with a price cap. Paper and real
are then compared signal by signal: how long the real order took, whether it filled, at what price.

Keys: this uses a Polymarket *session key* (see live_setup.py). A session key can place and cancel
orders for the account wallet but cannot withdraw. Nothing secret is stored in this repository.

Environment (set on the host, never in code):
  POLY_LIVE=1                 switch. Anything else: this file does nothing.
  POLY_SESSION_KEY            private key of the session signer
  POLY_WALLET                 the account (deposit) wallet address
  POLY_LIVE_USD=1             dollars per order
  POLY_LIVE_MAX_ORDERS_DAY=60 orders sent per UTC day
  POLY_LIVE_MAX_OPEN=4        bets open at the same time
  POLY_LIVE_DAY_LOSS=15       stop for the day after losing this many dollars (settled bets)
  POLY_LIVE_TOTAL_LOSS=15     stop for good after losing this much in total, until the state is reset
Defaults are sized for a $20 account: $1 a bet, so at least 15 bets even if every one loses.
The listed minimum for resting orders is 5 shares. If Polymarket refuses a $1 order for its size,
this switches by itself to 5 shares per order ($1.50-$4.55) and says so in the log.

State and the order log live in Firestore `poly_live/state` (one write per order and per result).
"""
import asyncio
import logging
import math
import os
import threading
import time

import requests

from pmq import api
from store import iso

log = logging.getLogger("poly")

LIVE_STRATEGY = "updown_latency_2bp"
GEOBLOCK = "https://polymarket.com/api/geoblock"   # Polymarket's own check of the caller's location
API_OPEN = {"IE", "JP", "NL", "KR", "MT"}             # website close-only, API not restricted (Polymarket docs, Nov 2026)
LO, HI = 0.30, 0.90            # only sides priced in this band (cheap sides lost on paper)
KEEP_WARM_EVERY = 10           # seconds; keeps the connection to Polymarket open and reads the balance
SETTLE_EVERY = 60
KEEP_ORDERS = 300              # order records kept in the state document


def _env_float(name, default):
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return float(default)


def day():
    return time.strftime("%Y-%m-%d", time.gmtime())


class LiveTrader:
    def __init__(self, worker):
        self.w = worker
        self.wanted = os.environ.get("POLY_LIVE") == "1"
        self.ready = False            # client connected and state loaded
        self.client = None
        self.loop = None              # orders run on their own thread and event loop (see run)
        self.usd = max(1.0, _env_float("POLY_LIVE_USD", 1))
        self.max_orders = int(_env_float("POLY_LIVE_MAX_ORDERS_DAY", 60))
        self.day_loss = _env_float("POLY_LIVE_DAY_LOSS", 15)
        self.total_loss = _env_float("POLY_LIVE_TOTAL_LOSS", 15)
        self.max_open = int(_env_float("POLY_LIVE_MAX_OPEN", 4))
        self.balance = None
        self.busy = set()             # condition ids with an order in flight
        self.tasks = set()
        self.d = dict(day=day(), orders_today=0, pnl_today=0.0, pnl_total=0.0, spent_total=0.0, n_orders=0,
                      n_filled=0, n_settled=0, n_wins=0, open={}, orders=[], stopped=None, five_shares=False, summary={})

    # ------------------------------------------------------------ setup
    def doc(self):
        return self.w.db.collection("poly_live").document("state")

    async def start(self):
        """Connect. Any failure leaves live trading off; the paper worker is not affected."""
        if not self.wanted:
            return
        key, wallet = os.environ.get("POLY_SESSION_KEY"), os.environ.get("POLY_WALLET")
        if not key or not wallet or self.w.lease is None:
            log.warning("live: POLY_LIVE=1 but POLY_SESSION_KEY / POLY_WALLET missing (or dry run); staying off")
            return
        try:
            logging.getLogger("httpx").setLevel(logging.WARNING)      # one line per request otherwise
            geo = await asyncio.to_thread(lambda: requests.get(GEOBLOCK, timeout=15).json())
            # This endpoint describes the website. A few countries (Ireland, Netherlands, Japan...) are
            # closed on the website but open for API orders, so only the known API-restricted ones stop here.
            # Anywhere else, the first refused order turns live trading off (see send()).
            if geo.get("blocked") and geo.get("country") not in API_OPEN:
                log.error("live: Polymarket does not accept orders from this server's location (%s %s); staying off. "
                          "Paper trading continues.", geo.get("country"), geo.get("region"))
                return
            log.info("live: server location %s %s", geo.get("country"), geo.get("region"))
            from polymarket import AsyncSecureClient
            saved = await asyncio.to_thread(lambda: self.doc().get().to_dict())
            if saved:
                self.d.update(saved)
            self.client = await AsyncSecureClient.create(private_key=key, wallet=wallet)
            bal = await self.client.get_balance_allowance(asset_type="COLLATERAL")
            self.balance = bal.balance / 1e6
            self.ready = True
            log.info("live: ON wallet=%s type=%s balance=%.2f | %s per order, max %d orders/day, %d open, stop at -$%.0f/day, -$%.0f total",
                     wallet[:8], self.client.wallet_type, self.balance, "5 shares" if self.d["five_shares"] else f"${self.usd:.2f}",
                     self.max_orders, self.max_open, self.day_loss, self.total_loss)
        except Exception as exc:
            log.error("live: could not start (%s: %s); staying off", type(exc).__name__, str(exc)[:200])

    def roll_day(self):
        if self.d["day"] != day():
            self.d.update(day=day(), orders_today=0, pnl_today=0.0)

    def blocked(self):
        """Reason no order may be sent now, or None."""
        self.roll_day()
        if self.d.get("stopped"):
            return self.d["stopped"]
        if self.d["pnl_total"] <= -self.total_loss:
            self.d["stopped"] = f"total loss limit reached ({self.d['pnl_total']:.2f})"
            return self.d["stopped"]
        if self.d["pnl_today"] <= -self.day_loss:
            return "daily loss limit"
        if self.d["orders_today"] >= self.max_orders:
            return "daily order limit"
        if len(self.d["open"]) + len(self.busy) >= self.max_open:
            return "max open"
        if self.balance is not None and self.balance < self.amount(HI) + 0.25:
            return "balance too low (claim winnings or add funds)"
        return None

    # ------------------------------------------------------------ orders
    def amount(self, limit):
        """Dollars to spend on one order capped at price `limit`."""
        if self.d["five_shares"]:
            return math.ceil(5 * limit * 100) / 100               # enough for 5 shares even at the cap price
        return round(self.usd, 2)

    def summarize(self):
        """Timing and fill figures over the kept order records: the point of the live test."""
        rows = [r for r in self.d["orders"] if r.get("ms") is not None]
        if not rows:
            return {}
        def pct(vals, q):
            vals = sorted(vals)
            return vals[min(len(vals) - 1, int(q * len(vals)))]
        ms, wait = [r["ms"] for r in rows], [r["wait_ms"] for r in rows]
        filled = [r for r in rows if r.get("price")]
        judged = [r for r in rows if "paper" in r]
        both = [r for r in filled if isinstance(r.get("paper"), (int, float))]
        out = dict(orders=len(rows), filled=len(filled), fill_rate=round(len(filled) / len(rows), 3),
                   answer_ms=dict(min=min(ms), median=pct(ms, 0.5), p90=pct(ms, 0.9), max=max(ms)),
                   post_ms=dict(median=pct([r.get("post_ms", r["ms"]) for r in rows], 0.5)),
                   send_wait_ms=dict(median=pct(wait, 0.5), p90=pct(wait, 0.9)),
                   paper_filled=sum(1 for r in judged if r["paper"] != "miss"),
                   paper_missed=sum(1 for r in judged if r["paper"] == "miss"),
                   real_filled_paper_missed=sum(1 for r in filled if r.get("paper") == "miss"),
                   real_missed_paper_filled=sum(1 for r in judged if not r.get("price") and r["paper"] != "miss"))
        if both:
            out["real_minus_paper_price"] = round(sum(r["price"] - r["paper"] for r in both) / len(both), 4)
        return out

    def on_signal(self, o, recv_ms):
        """Called by the paper trader the moment it notes an order. Must not block."""
        if not self.ready or o["s"].name != LIVE_STRATEGY:
            return
        if not (LO <= o["ask_seen"] <= HI) or o["cid"] in self.busy or o["cid"] in self.d["open"]:
            return
        if self.blocked():
            return
        self.busy.add(o["cid"])
        self.d["orders_today"] += 1
        self.d["n_orders"] += 1
        asyncio.run_coroutine_threadsafe(self.send(o, recv_ms), self.loop)

    async def send(self, o, recv_ms):
        m = o["m"]
        limit = round(o["limit"], 2)
        usd = self.amount(limit)
        rec = dict(at=iso(), cid=o["cid"], question=m["question"][:80], outcome=m["outcomes"][o["outcome"]],
                   bp=round(o["bp"], 2), ask_seen=o["ask_seen"], limit=limit, usd=usd)
        o["live"] = rec                                           # the paper trader adds its own result here
        t0 = time.time() * 1000
        rec["wait_ms"] = round(t0 - recv_ms)                      # Binance update received -> order handed to the client
        rec["book_sent"] = self.top(o["token"])                   # public feed's asks when the order left
        try:
            signed = await self.client.create_market_order(asset_id=o["token"], side="BUY", amount=str(usd),
                                                           max_price=str(limit), order_type="FAK")
            t1 = time.time() * 1000
            rec["sign_ms"] = round(t1 - t0)                       # build and sign the order
            r = await self.client.post_order(signed)
            rec["post_ms"] = round(time.time() * 1000 - t1)       # send it and get the matched/refused answer
            rec["ms"] = round(time.time() * 1000 - t0)
            if r.ok:
                spent, got = float(r.making_amount), float(r.taking_amount)
                if got > 0 and spent / got > 1:                   # amounts reported the other way round
                    spent, got = got, spent
                rec.update(status=r.status, spent=round(spent, 4), shares=round(got, 4), order_id=str(r.order_id)[:20])
                if r.status == "matched" and got > 0:
                    rec["price"] = round(spent / got, 4)
                    self.d["n_filled"] += 1
                    self.d["spent_total"] = round(self.d["spent_total"] + spent, 4)
                    self.d["open"][o["cid"]] = dict(outcome=o["outcome"], shares=got, cost=spent, at=rec["at"])
            else:
                rec.update(status="rejected", code=str(r.code), message=str(r.message)[:120])
        except Exception as exc:
            rec["ms"] = round(time.time() * 1000 - t0)
            rec.update(status="error", message=f"{type(exc).__name__}: {str(exc)[:120]}")
        finally:
            self.busy.discard(o["cid"])
        # What the public feed showed when the answer came back. If it still shows an ask within the cap
        # while Polymarket found nothing to match, the feed and the real book disagree.
        rec["book_answer"] = self.top(o["token"])
        rec["feed_age_ms"] = round(time.time() * 1000 - getattr(self.w.books, "last_ts", 0))   # how current that view is
        text = str(rec.get("message", "")).lower()
        if "restricted in your region" in text:                   # never retry against a location refusal
            self.ready = False
            log.error("live: Polymarket refused the order for this server's location; live orders are off until restart")
        if not self.d["five_shares"] and not rec.get("price") and ("size" in text or "minimum" in text):
            self.d["five_shares"] = True
            log.warning("[live] order refused for its size (%s); switching to 5 shares per order", rec.get("message"))
        log.info("[live] %s %s '%s' cap %.2f | bp %+.1f | binance age %.0fms, sent after %sms, sign %sms, answer %sms | %s",
                 rec.get("status"), rec["question"][:48], rec["outcome"], limit, o["bp"], o["age"], rec["wait_ms"],
                 rec.get("sign_ms"), rec.get("post_ms", rec.get("ms")),
                 f"{rec.get('shares')} @ {rec.get('price')}" if rec.get("price") else str(rec.get("message", ""))[:40])
        log.info("[live]   feed asks when sent %s, when answered %s (feed %sms old)", rec.get("book_sent"),
                 rec.get("book_answer"), rec.get("feed_age_ms"))
        self.d["orders"] = (self.d["orders"] + [rec])[-KEEP_ORDERS:]
        self.d["summary"] = self.summarize()
        if self.d["n_orders"] % 5 == 0:
            log.info("[live] summary %s", self.d["summary"])
        await self.save()

    def top(self, token):
        """Best three asks [price, size] as the public feed shows them now."""
        try:
            return [[round(p, 2), round(z, 1)] for p, z in self.w.books.asks(token)[:3]]
        except Exception:
            return None

    def paper_result(self, o, price):
        """The paper trader's verdict for the same order: its fill price, or None for a miss."""
        if "live" in o:
            o["live"]["paper"] = price if price is not None else "miss"

    async def save(self):
        try:
            await asyncio.to_thread(self.doc().set, dict(self.d, updated_at=iso(), balance=self.balance))
        except Exception as exc:
            log.warning("live_save_failed error=%s", type(exc).__name__)

    # ------------------------------------------------------------ background
    async def prewarm(self, tokens):
        """Load order metadata for the next markets so the first order on each is not slowed by a lookup."""
        if self.ready:
            asyncio.run_coroutine_threadsafe(self._prewarm(list(tokens)), self.loop)

    async def _prewarm(self, tokens):
        for tok in tokens:
            try:
                await self.client._ctx.order_metadata.resolve_market(self.client._ctx, token_id=tok)
            except Exception:
                return                        # private SDK call; orders still work without it, only slower

    async def keep_warm(self):
        while not self.w.stopping:
            await asyncio.sleep(KEEP_WARM_EVERY)
            try:
                bal = await self.client.get_balance_allowance(asset_type="COLLATERAL")
                self.balance = bal.balance / 1e6
            except Exception as exc:
                log.warning("live_keep_warm_failed error=%s", type(exc).__name__)

    async def settle_loop(self):
        while not self.w.stopping:
            await asyncio.sleep(SETTLE_EVERY)
            if not self.d["open"]:
                continue
            try:
                info = await asyncio.to_thread(api.markets_by_condition, sorted(self.d["open"]))
                done = 0
                for cid, pos in list(self.d["open"].items()):
                    m = info.get(cid)
                    if m and m["closed"] and sorted(m["outcome_prices"]) == [0.0, 1.0]:
                        pnl = pos["shares"] * m["outcome_prices"][pos["outcome"]] - pos["cost"]
                        self.roll_day()
                        self.d["pnl_today"] = round(self.d["pnl_today"] + pnl, 4)
                        self.d["pnl_total"] = round(self.d["pnl_total"] + pnl, 4)
                        self.d["n_settled"] += 1
                        self.d["n_wins"] += 1 if pnl > 0 else 0
                        for rec in self.d["orders"]:
                            if rec.get("cid") == cid and rec.get("price"):
                                rec["pnl"] = round(pnl, 4)
                        del self.d["open"][cid]
                        done += 1
                if done:
                    self.d["summary"] = self.summarize()
                    log.info("[live] summary %s", self.d["summary"])
                    log.info("[live] settled %d | today %+.2f, total %+.2f over %d bets (%d won), balance %s",
                             done, self.d["pnl_today"], self.d["pnl_total"], self.d["n_settled"], self.d["n_wins"], self.balance)
                    await self.save()
            except Exception as exc:
                log.warning("live_settle_failed error=%s", type(exc).__name__)

    async def _order_main(self):
        self.loop = asyncio.get_running_loop()
        await self.start()
        if self.ready:
            try:
                await asyncio.gather(self.keep_warm(), self.settle_loop())
            finally:
                await self.save()

    async def run(self):
        """Everything live runs on its own thread with its own event loop. The worker's main loop can be
        busy for hundreds of milliseconds with bursts of price updates exactly when a signal fires, and an
        order waiting behind that backlog arrives too late."""
        if self.wanted:
            threading.Thread(target=lambda: asyncio.run(self._order_main()), name="live-orders", daemon=True).start()
        await asyncio.Event().wait()                       # idle until cancelled
