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
  POLY_LIVE_SHARES=5          shares per order (5 is the market minimum)
  POLY_LIVE_MAX_ORDERS_DAY=40 orders sent per UTC day
  POLY_LIVE_DAY_LOSS=10       stop for the day after losing this many dollars (settled bets)
  POLY_LIVE_TOTAL_LOSS=20     stop for good after losing this much in total, until the state is reset

State and the order log live in Firestore `poly_live/state` (one write per order and per result).
"""
import asyncio
import logging
import math
import os
import time

from pmq import api
from store import iso

log = logging.getLogger("poly")

LIVE_STRATEGY = "updown_latency_2bp"
LO, HI = 0.30, 0.90            # only sides priced in this band (cheap sides lost on paper)
KEEP_WARM_EVERY = 10           # seconds; keeps the connection to Polymarket open and reads the balance
SETTLE_EVERY = 60
MAX_OPEN = 6
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
        self.shares = _env_float("POLY_LIVE_SHARES", 5)
        self.max_orders = int(_env_float("POLY_LIVE_MAX_ORDERS_DAY", 40))
        self.day_loss = _env_float("POLY_LIVE_DAY_LOSS", 10)
        self.total_loss = _env_float("POLY_LIVE_TOTAL_LOSS", 20)
        self.balance = None
        self.busy = set()             # condition ids with an order in flight
        self.tasks = set()
        self.d = dict(day=day(), orders_today=0, pnl_today=0.0, pnl_total=0.0, spent_total=0.0, n_orders=0,
                      n_filled=0, n_settled=0, n_wins=0, open={}, orders=[], stopped=None)

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
            from polymarket import AsyncSecureClient
            saved = await asyncio.to_thread(lambda: self.doc().get().to_dict())
            if saved:
                self.d.update(saved)
            self.client = await AsyncSecureClient.create(private_key=key, wallet=wallet)
            bal = await self.client.get_balance_allowance(asset_type="COLLATERAL")
            self.balance = bal.balance / 1e6
            self.ready = True
            log.info("live: ON wallet=%s type=%s balance=%.2f | %s shares/order, max %d orders/day, stop at -$%.0f/day, -$%.0f total",
                     wallet[:8], self.client.wallet_type, self.balance, self.shares, self.max_orders, self.day_loss, self.total_loss)
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
        if len(self.d["open"]) + len(self.busy) >= MAX_OPEN:
            return "max open"
        return None

    # ------------------------------------------------------------ orders
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
        task = asyncio.create_task(self.send(o, recv_ms))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def send(self, o, recv_ms):
        m = o["m"]
        limit = round(o["limit"], 2)
        usd = math.ceil(self.shares * limit * 100) / 100          # enough for `shares` even at the cap price
        rec = dict(at=iso(), cid=o["cid"], question=m["question"][:80], outcome=m["outcomes"][o["outcome"]],
                   bp=round(o["bp"], 2), ask_seen=o["ask_seen"], limit=limit, usd=usd)
        o["live"] = rec                                           # the paper trader adds its own result here
        t0 = time.time() * 1000
        rec["wait_ms"] = round(t0 - recv_ms)                      # Binance update received -> order handed to the client
        try:
            r = await self.client.place_market_order(asset_id=o["token"], side="BUY", amount=str(usd),
                                                     max_price=str(limit), order_type="FAK")
            rec["ms"] = round(time.time() * 1000 - t0)            # sign + send + matched response
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
        log.info("[live] %s %s '%s' cap %.2f | bp %+.1f | sent after %sms, answered in %sms | %s",
                 rec.get("status"), rec["question"][:48], rec["outcome"], limit, o["bp"], rec["wait_ms"], rec.get("ms"),
                 f"{rec.get('shares')} @ {rec.get('price')}" if rec.get("price") else rec.get("message", ""))
        self.d["orders"] = (self.d["orders"] + [rec])[-KEEP_ORDERS:]
        await self.save()

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
        if not self.ready:
            return
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
                    log.info("[live] settled %d | today %+.2f, total %+.2f over %d bets (%d won), balance %s",
                             done, self.d["pnl_today"], self.d["pnl_total"], self.d["n_settled"], self.d["n_wins"], self.balance)
                    await self.save()
            except Exception as exc:
                log.warning("live_settle_failed error=%s", type(exc).__name__)

    async def run(self):
        await self.start()
        if not self.ready:
            return await asyncio.Event().wait()            # off: idle until cancelled
        try:
            await asyncio.gather(self.keep_warm(), self.settle_loop())
        finally:
            await self.save()
