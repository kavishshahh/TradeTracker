"""Feed-driven Polymarket paper trader. Paper only: no wallet, key or order-placement code.

  .venv\\Scripts\\python.exe -u worker.py                 # run until Ctrl+C, state in Firestore
  .venv\\Scripts\\python.exe -u worker.py --dry --seconds 60   # in-memory test run, no Firestore writes

How it reacts:
  * Only markets near a trade are streamed: every few minutes the full market list (which carries
    each market's current quotes) is scanned, and live feeds are opened just for the shortlist
    plus the positions held. Far-away markets cost nothing.
  * Polymarket order-book WebSocket -> a change in a watched market's best price re-evaluates it at once.
  * Binance price WebSocket         -> a price move re-evaluates every watched crypto market.
  * Fills are simulated against the live ask ladder (real fees, 5-share minimum) and saved immediately.
What is not a feed (no stream exists for it), so it is refreshed on a timer:
  * the list of open markets and the shortlist (every 3 min), hourly candles for the volatility
    estimate (10 min), and whether held markets have resolved (every 2 min).
"""
import argparse
import asyncio
import json
import logging
import os
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from feed import BookFeed, Books, SpotFeed          # noqa: E402
from lease import Lease                              # noqa: E402
from pmq import api                                  # noqa: E402
from pmq.broker import execute                       # noqa: E402
from pmq.core import Context, Snapshot               # noqa: E402
from pmq.strategies import REGISTRY                  # noqa: E402
from pmq.strategies.crypto_fair_value import SYM     # noqa: E402
from store import Account, MemoryDb, firestore_client, iso   # noqa: E402
import latency
from latency_algo import LatencyTrader                # noqa: E402
from copy_algo import CopyTrader                      # noqa: E402
from live import LiveTrader                           # noqa: E402

log = logging.getLogger("poly")

BANKROLL = 25.0
UNIVERSE_EVERY = 120          # also how often the next 5-minute markets are picked up (two windows ahead)
CANDLES_EVERY = 600
SETTLE_EVERY = 120
HEARTBEAT_EVERY = 120         # lease renewal; account saves are spaced out below
SAVE_EVERY = 600              # an account's scoreboard (marks, equity) is saved at least this often; fills and
                              # settlements save at once. Firestore's free tier is 20,000 writes a day, shared
                              # with the main app, so a 2-minute save for every account was too much.
IDLE_SAVE_EVERY = 6 * 3600    # paused accounts with no open bets: nothing changes, so only an occasional save
LATENCY_EVERY = 600           # latency probe (logged and saved to poly_worker/latency)
UNIVERSE_STALL = 900          # no completed market refresh for this long: exit so the host restarts the worker
SPOT_SWEEP_EVERY = 5          # seconds between full crypto re-evaluations on price moves
SPOT_MOVE = 0.0005            # ...and only when a price moved by at least 0.05%
MAX_NEW_PER_10MIN = 2         # pace entries so a small bankroll is spread over time
FEED_MAX_SILENCE = 45         # seconds without any book message before trading pauses
SYMBOLS = sorted(set(SYM.values()))


class LiveData:
    """What strategies read: spot from the Binance stream, candles from a background refresh."""
    def __init__(self, spot):
        self._spot = spot
        self._k = {}
        self._slices = {}

    def refresh_candles(self):          # blocking; called in a thread
        for sym in SYMBOLS:
            self._k[sym] = api.klines(sym, time.time() - 32 * 86400)   # covers the longest market traded (30 days)
        self._slices.clear()

    def extremes(self, sym, start):
        """Lowest and highest price since `start`, up to now: hourly candles (including the one in
        progress at the last refresh) plus the live stream since then. Used for "already touched"."""
        k = self._k.get(sym)
        lo, hi = self._spot.extremes(sym, start)
        if k is not None:
            seen = k[k.index + 3600 > start]
            if len(seen):
                lo, hi = min(lo, float(seen.l.min())), max(hi, float(seen.h.max()))
        return lo, hi

    def klines(self, sym, t, lookback):
        key = (sym, lookback, int(t // 300))
        if key not in self._slices:
            k = self._k.get(sym)
            self._slices[key] = None if k is None else k[(k.index <= t - 3600) & (k.index > t - lookback)]
        return self._slices[key]

    def spot(self, sym):
        price = self._spot.get(sym)
        if price is None:
            raise RuntimeError(f"no live price for {sym}")
        return price


def by_halt(worker, name):
    return any(s.halted for s in worker.strategies if s.name == name)


class Worker:
    def __init__(self, db, bankroll=BANKROLL, lease=None):
        self.db = db
        self.lease = lease            # None in --dry runs
        self.lost_lease = False
        self.stopping = False         # loops also check this: on Python 3.11 a cancel can be swallowed
        self.strategies = [cls() for cls in REGISTRY.values()]
        self.accounts = {s.name: Account(db, s, getattr(s, "bankroll", bankroll)) for s in self.strategies}
        self.books = Books()
        self.feed = BookFeed(self.books)
        self.spot = SpotFeed(SYMBOLS)
        self.data = LiveData(self.spot)
        self.universe = {s.name: {} for s in self.strategies}     # cid -> market, only those on the live feed
        self.scanned = {s.name: 0 for s in self.strategies}       # markets looked at in the last listing
        self.by_token = {}                                        # token -> [(strategy, cid)]
        self.stats = {s.name: dict(evaluations=0, signals=0, skipped={}) for s in self.strategies}
        self.errors = {}
        self._swept = {}
        self._listing = {}                 # strategy -> (time, rows) for algos that set scan_every
        self._save_locks = {s.name: asyncio.Lock() for s in self.strategies}
        self._saved_at = {}           # account -> time of its last successful save
        self._cpu = (time.process_time(), time.time())
        self.universe_at = time.time()     # last completed market refresh
        self.stalled = False
        self.latency = LatencyTrader(self)
        self.copy = CopyTrader(self)       # copies other wallets' buys from the live activity feed
        self.live = LiveTrader(self)       # real orders; off unless POLY_LIVE=1 and keys are set on the host

    # ------------------------------------------------------------ persistence
    def marks(self, acc):
        return {k: self.books.best_bid(m.get("token_id")) for k, m in acc.meta.items()}

    def feed_ok(self):
        return self.feed.connected > 0 and time.time() - self.books.last_message < FEED_MAX_SILENCE

    async def save(self, name):
        acc, st = self.accounts[name], self.stats[name]
        # Copy accounts trade off the activity feed; the order-book feed only matters to them while a bet is
        # open (for marks). With every other algo paused it has no tokens and is idle, which is not "offline".
        copying = any(s.name == name and getattr(s, "copy_rule", False) for s in self.strategies)
        connected = (self.copy.connected and (self.feed_ok() or not acc.pf.pos)) if copying else self.feed_ok()
        extra = dict(candidates=self.scanned[name], watching=len(self.universe[name]), evaluations=st["evaluations"], signals=st["signals"],
                     skipped=st["skipped"], last_skip=st.get("last_skip"), last_error=self.errors.get(name), last_evaluation=iso(),
                     markets_refreshed_at=iso(self.universe_at), halted=by_halt(self, name),
                     perp_feed=dict(connected=self.latency.feed.connected, ticks=self.latency.feed.ticks),
                     activity_feed=dict(connected=self.copy.connected, messages=self.copy.messages,
                                        chain_connected=self.copy.chain_connected, chain_maker_fills=self.copy.chain_events),
                     feed=dict(connected=connected, connections=self.feed.connected, tokens=len(self.feed.tokens),
                               messages=self.books.messages,
                               last_message_at=iso(self.books.last_message) if self.books.last_message else None))
        async with self._save_locks[name]:             # one save per account at a time, in order
            await asyncio.to_thread(acc.flush_ledger)  # permanent trade ledger first, then the scoreboard
            doc = acc.document(self.marks(acc), extra)
            await asyncio.to_thread(self.db.collection("poly_paper_state").document(name).set, doc)
            self._saved_at[name] = time.time()

    async def safe_save(self, name):
        """A failed write must not stop trading: the account stays in memory and the next save retries."""
        try:
            await self.save(name)
        except Exception as exc:
            log.warning("save_failed strategy=%s error=%s", name, type(exc).__name__)

    # ------------------------------------------------------------ decisions
    def evaluate(self, s, m, now):
        """Run one strategy on one market from the local books. Returns True when a paper fill happened."""
        acc, st = self.accounts[s.name], self.stats[s.name]
        if s.halted or getattr(s, "latency_rule", False) or getattr(s, "copy_rule", False):   # traded in latency_algo.py / copy_algo.py
            return False
        if acc.pf.held(m["condition_id"]) or m.get("event_slug") in acc.held_events() or not s.universe(m, now):
            return False
        acc.recent_entries = [t for t in acc.recent_entries if now - t < 600]
        if len(acc.recent_entries) >= getattr(s, "max_new_per_10min", MAX_NEW_PER_10MIN):
            return False
        toks = m["token_ids"]
        ladders = [self.books.asks(toks[0]), self.books.asks(toks[1])]
        if ladders[0] is None or ladders[1] is None:
            return False                       # no snapshot yet for one side
        snap = Snapshot(m, now, bid=[self.books.best_bid(toks[0]), self.books.best_bid(toks[1])],
                        ask=[ladders[0][0][0] if ladders[0] else None, ladders[1][0][0] if ladders[1] else None],
                        ask_depth=ladders,
                        last_trade=[self.books.last_trade(toks[0], toks[1], now), self.books.last_trade(toks[1], toks[0], now)])
        st["evaluations"] += 1
        ctx = Context(acc.pf, now=now, data=self.data, mode="paper")
        risk = dict(one_entry_per_market=True, max_open_markets=12, max_order_usd=acc.pf.start_cash * 0.10,
                    max_exposure_usd=acc.pf.start_cash * 0.8)
        if getattr(s, "min_order_usd", None):
            risk["min_order_usd"] = s.min_order_usd
        risk.update(getattr(s, "risk", {}))      # an algo may set its own limits (e.g. many small long-held bets)
        for order in s.on_snapshot(snap, ctx) or []:
            st["signals"] += 1
            fill, why = execute(order, snap, acc.pf, risk)
            if not fill:
                key = why.split(" (")[0]
                st["skipped"][key] = st["skipped"].get(key, 0) + 1
                st["last_skip"] = dict(at=iso(now), why=why, question=m["question"], outcome=m["outcomes"][order.outcome],
                                       reason=order.reason, limit=round(order.limit, 3), top_asks=ladders[order.outcome][:3])
                continue
            acc.record_fill(fill, m)
            log.info("[%s] PAPER BUY %.2f '%s' @ %.3f ($%.2f, fee %.4f) | %s | %s", s.name, fill.shares,
                     m["outcomes"][fill.outcome], fill.price, fill.shares * fill.price, fill.fee, m["question"][:70], fill.reason)
            return True
        return False

    async def decide_loop(self):
        by_name = {s.name: s for s in self.strategies}
        while not self.stopping:
            try:
                await asyncio.wait_for(self.books.event.wait(), 1)
            except asyncio.TimeoutError:
                pass
            now = time.time()
            todo = {}                                   # (strategy, cid) -> None, insertion-ordered
            for token in self.books.take_dirty():
                for pair in self.by_token.get(token, ()):
                    todo[pair] = None
            # A crypto price move changes fair value for every crypto market, not just the one whose book moved.
            moved = [sym for sym in SYMBOLS if (p := self.spot.get(sym)) and abs(p / self._swept.get(sym, (0, p * 2))[1] - 1) >= SPOT_MOVE
                     and now - self._swept.get(sym, (0, 0))[0] >= SPOT_SWEEP_EVERY]
            if moved:
                for sym in moved:
                    self._swept[sym] = (now, self.spot.get(sym))
                for s in self.strategies:
                    if getattr(s, "spot_driven", False):
                        for cid in self.universe[s.name]:
                            todo[(s.name, cid)] = None
            # Time-driven algos (5-minute markets) are re-checked every second even when their book is still.
            for s in self.strategies:
                if getattr(s, "time_driven", False):
                    for cid in self.universe[s.name]:
                        todo[(s.name, cid)] = None
            if not todo or not self.feed_ok() or (self.lease and not self.lease.fresh()):
                continue
            changed = set()
            for name, cid in todo:
                m = self.universe[name].get(cid)
                if m is None:
                    continue
                try:
                    if self.evaluate(by_name[name], m, now):
                        changed.add(name)
                except Exception as exc:
                    self.errors[name] = f"{type(exc).__name__}: {str(exc)[:160]}"
            for name in changed:
                await self.safe_save(name)
            await asyncio.sleep(0)

    # ------------------------------------------------------------ timers (things with no feed)
    async def universe_loop(self):
        candles_at = 0
        while True:
            try:
                if time.time() - candles_at > CANDLES_EVERY:
                    try:
                        await asyncio.to_thread(self.data.refresh_candles)
                        candles_at = time.time()
                    except Exception as exc:               # keep the old candles and still refresh the markets
                        log.warning("candle_refresh_failed error=%s", type(exc).__name__)
                for _ in range(40):                       # the shortlist needs live coin prices
                    if all(self.spot.get(sym) for sym in SYMBOLS):
                        break
                    await asyncio.sleep(0.5)
                now = time.time()
                for s in self.strategies:
                    if s.halted or getattr(s, "copy_rule", False):   # paused, or copy algos (no scan); held bets still settle
                        self.universe[s.name], self.scanned[s.name] = {}, 0
                        continue
                    try:                                   # one algo's data problem must not starve the others
                        cached = self._listing.get(s.name)
                        if cached and now - cached[0] < getattr(s, "scan_every", 0):
                            rows = cached[1]               # a large listing is re-read only every scan_every seconds
                        else:
                            rows = await asyncio.to_thread(api.market_query, s.market_query)
                            if getattr(s, "scan_every", 0):
                                self._listing[s.name] = (now, rows)
                        rows = [m for m in rows if m.get("accepting") and len(m["token_ids"]) == 2 and s.universe(m, now)]
                        acc = self.accounts[s.name]
                        ctx = Context(acc.pf, now=now, data=self.data, mode="paper")
                        # Shortlist from the listing's own quotes: only markets near a trade get a live feed.
                        uni = {m["condition_id"]: m for m in rows if not acc.pf.held(m["condition_id"])
                               and (getattr(s, "always_stream", False) or s.prefilter(m, ctx))}
                        self.scanned[s.name] = len(rows)
                        self.universe[s.name] = uni
                        self.errors.pop(s.name, None)
                    except Exception as exc:               # keep this algo's previous shortlist
                        self.errors[s.name] = f"market refresh: {type(exc).__name__}: {str(exc)[:120]}"
                        log.warning("universe_refresh_failed strategy=%s error=%s", s.name, type(exc).__name__)
                by_token = {}
                for name, uni in self.universe.items():
                    for cid, m in uni.items():
                        for tok in m["token_ids"]:
                            by_token.setdefault(tok, []).append((name, cid))
                self.by_token = by_token
                self.books.track = self.latency.tracked_tokens()
                held = [m["token_id"] for acc in self.accounts.values() for m in acc.meta.values() if m.get("token_id")]
                await self.feed.set_tokens(list(by_token) + held)
                self.universe_at = time.time()
                await self.live.prewarm(self.books.track)
                log.info("scanned %s -> watching %s | %d tokens on %d connection(s)", self.scanned,
                         {n: len(u) for n, u in self.universe.items()}, len(self.feed.tokens), len(self.feed.tasks))
            except Exception as exc:
                log.warning("universe_refresh_failed error=%s", type(exc).__name__)
            await asyncio.sleep(UNIVERSE_EVERY)

    async def latency_loop(self):
        await asyncio.sleep(45)
        while True:
            try:
                result = await latency.probe()
                log.info("latency %s", latency.line(result))
                if self.lease:                 # not on --dry runs
                    await asyncio.to_thread(self.db.collection("poly_worker").document("latency").set,
                                            {**result, "at_iso": iso(result["at"]), "host": self.lease.owner})
            except Exception as exc:
                log.warning("latency_probe_failed error=%s", type(exc).__name__)
            await asyncio.sleep(LATENCY_EVERY)

    async def settle_loop(self):
        while True:
            await asyncio.sleep(SETTLE_EVERY)
            try:
                cids = sorted({c for acc in self.accounts.values() for c, _ in acc.pf.pos})
                if not cids:
                    continue
                info = await asyncio.to_thread(api.markets_by_condition, cids)
                for name, acc in self.accounts.items():
                    done = 0
                    for cid in sorted({c for c, _ in acc.pf.pos}):
                        m = info.get(cid)
                        if m and m["closed"] and sorted(m["outcome_prices"]) == [0.0, 1.0]:
                            done += acc.settle(cid, m["outcome_prices"], time.time())
                    if done:
                        log.info("[%s] settled %d position(s), realized %.2f", name, done, acc.d["realized_pnl"])
                        await self.safe_save(name)
            except Exception as exc:
                log.warning("settle_failed error=%s", type(exc).__name__)

    async def heartbeat_loop(self):
        while True:
            await asyncio.sleep(HEARTBEAT_EVERY)
            if self.lease:
                try:
                    if not await asyncio.to_thread(self.lease.renew):
                        # Another worker took over (we stalled past the lease TTL). Our in-memory accounts
                        # are now out of date: stop without saving so we cannot overwrite the new holder.
                        log.error("lease lost to %s; stopping without saving", self.lease.holder)
                        self.lost_lease = True
                        return
                except Exception as exc:       # cannot reach Firestore: trading pauses once the lease goes stale
                    log.warning("lease_renew_failed error=%s", type(exc).__name__)
            for name, acc in self.accounts.items():
                every = IDLE_SAVE_EVERY if by_halt(self, name) and not acc.pf.pos else SAVE_EVERY
                if time.time() - self._saved_at.get(name, 0) < every - 30:
                    continue
                try:
                    await self.save(name)
                except Exception as exc:
                    log.warning("heartbeat_failed strategy=%s error=%s", name, type(exc).__name__)
            if time.time() - self.universe_at > UNIVERSE_STALL:
                # The market refresh has stopped, so the algos are watching old markets. Save, release
                # the lease and exit non-zero: the host starts a fresh process.
                log.error("market refresh stalled for %.0fs; restarting", time.time() - self.universe_at)
                self.stalled = True
                return
            cpu, wall = time.process_time(), time.time()
            used = (cpu - self._cpu[0]) / max(wall - self._cpu[1], 1e-9) * 100
            self._cpu = (cpu, wall)
            log.info("feed ok=%s msgs=%d cpu=%.0f%% | %s", self.feed_ok(), self.books.messages, used,
                     {n: f"eq {a.d.get('equity')} open {len(a.pf.pos)} evals {self.stats[n]['evaluations']}" for n, a in self.accounts.items()})

    async def run(self, seconds=None):
        tasks = [asyncio.create_task(c) for c in (self.spot.run(), self.universe_loop(), self.decide_loop(),
                                                  self.settle_loop(), self.latency_loop(), self.latency.run(),
                                                  self.live.run(), self.copy.run())]
        heartbeat = asyncio.create_task(self.heartbeat_loop())     # returns only when the lease is lost
        stop = asyncio.Event()
        try:                                   # hosts stop a service with SIGTERM; finish cleanly on it
            asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, stop.set)
        except (NotImplementedError, AttributeError, ValueError):
            pass                               # Windows: Ctrl+C (KeyboardInterrupt) is the stop signal
        waiters = [asyncio.create_task(stop.wait()), heartbeat, asyncio.ensure_future(asyncio.gather(*tasks))]
        if seconds:
            waiters.append(asyncio.create_task(asyncio.sleep(seconds)))
        try:
            await asyncio.wait(waiters, return_when=asyncio.FIRST_COMPLETED)
        finally:
            self.stopping = True
            self.feed.stopping = True
            self.latency.feed.stopping = True
            self.copy.stopping = True
            everything = tasks + [heartbeat] + waiters + self.feed.tasks
            for t in everything:
                t.cancel()
            # Never wait without limit for tasks to finish: state is saved from memory either way.
            done, stuck = await asyncio.wait(everything, timeout=10)
            for t in done:                     # collect results so nothing is reported as "never retrieved"
                if not t.cancelled():
                    t.exception()
            if stuck:
                log.warning("%d task(s) did not stop within 10s; saving anyway", len(stuck))
            if not self.lost_lease:
                for name in self.accounts:
                    await self.safe_save(name)
                if self.lease:
                    try:
                        await asyncio.to_thread(self.lease.release)
                        log.info("stopped cleanly; lease released")
                    except Exception as exc:
                        log.warning("lease_release_failed error=%s", type(exc).__name__)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="in-memory store; no Firestore writes")
    ap.add_argument("--seconds", type=int, help="stop after this many seconds")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    db = MemoryDb() if a.dry else firestore_client()
    lease = None
    if not a.dry:
        # Wait until no other worker is trading these accounts, and only then load them.
        lease = Lease(db)
        waited = False
        try:
            while not lease.acquire():
                if not waited:
                    log.info("another worker (%s) is running; waiting for it to stop. This copy trades nothing meanwhile.", lease.holder)
                    waited = True
                time.sleep(10)
        except KeyboardInterrupt:
            return
        log.info("lease acquired as %s", lease.owner)
    worker = Worker(db, lease=lease)
    loop = asyncio.new_event_loop()
    main_task = loop.create_task(worker.run(a.seconds))
    try:
        loop.run_until_complete(main_task)
    except KeyboardInterrupt:
        # Ctrl+C: cancel the run so its shutdown (final save, lease release) still happens.
        main_task.cancel()
        try:
            loop.run_until_complete(asyncio.wait([main_task], timeout=60))
        except KeyboardInterrupt:
            pass
    if a.dry:
        for path, doc in db.docs.items():
            keep = ("cash", "equity", "candidates", "watching", "evaluations", "signals", "skipped", "last_skip", "last_error")
            print(path, json.dumps({k: doc.get(k) for k in keep})[:1400])
    # State is saved and the lease released inside run(). Do not wait for a network call still stuck
    # in a background thread (Python 3.11 would wait without limit): exit now.
    logging.shutdown()
    sys.stdout.flush()
    os._exit(1 if worker.stalled else 0)


if __name__ == "__main__":
    main()
