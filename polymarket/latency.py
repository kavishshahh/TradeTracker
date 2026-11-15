"""Latency probe: how far this machine is from Polymarket and Binance, in milliseconds.

Read-only and public endpoints only. Run by the worker every 10 minutes (logged, and saved to
poly_worker/latency), or by hand:  python latency.py

  polymarket_rest   request round trip to the CLOB (order placement goes the same way)
  polymarket_feed   how old a book update is when it arrives (arrival time minus its own timestamp)
  binance_spot      how old a spot trade is when it arrives
  binance_perp      how old a perp quote is when it arrives (or the error if this region is blocked)

The feed ages compare this machine's clock with the exchange's, so a clock that is off shifts them
all by the same amount; the request round trip does not depend on the clock.
"""
import asyncio
import json
import statistics
import time

import requests
import websockets

from pmq import api

CLOB_TIME = "https://clob.polymarket.com/time"
POLY_WS = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
SPOT_WS = "wss://data-stream.binance.vision/stream?streams=btcusdt@aggTrade"
PERP_WS = "wss://fstream.binance.com/stream?streams=btcusdt@bookTicker"


def _summary(values):
    if not values:
        return dict(n=0)
    values = sorted(values)
    return dict(n=len(values), min=round(values[0]), median=round(statistics.median(values)),
                p90=round(values[int(len(values) * 0.9)]))


def rest_round_trip(url=CLOB_TIME, n=8):
    s = requests.Session()
    s.get(url, timeout=10)                       # open the connection first; orders reuse one too
    out = []
    for _ in range(n):
        t = time.perf_counter()
        s.get(url, timeout=10)
        out.append((time.perf_counter() - t) * 1000)
    return _summary(out)


async def feed_age(url, stamps, subscribe=None, seconds=12, limit=400):
    """Arrival time minus the message's own timestamp, for `seconds` of messages."""
    out, end = [], time.time() + seconds
    async with websockets.connect(url, max_size=None, open_timeout=15) as ws:
        if subscribe:
            await ws.send(json.dumps(subscribe))
        while time.time() < end and len(out) < limit:
            try:
                raw = await asyncio.wait_for(ws.recv(), 3)
            except asyncio.TimeoutError:
                continue
            now = time.time() * 1000
            try:
                data = json.loads(raw)
            except ValueError:
                continue
            for ts in stamps(data):
                out.append(now - ts)
    return _summary(out)


def _binance(data):
    d = data.get("data", {}) if isinstance(data, dict) else {}
    return [d["T"]] if d.get("T") else []


def _poly(data):
    events = data if isinstance(data, list) else [data]
    return [int(e["timestamp"]) for e in events
            if isinstance(e, dict) and e.get("event_type") == "price_change" and e.get("timestamp")]


async def probe():
    async def safe(coro):
        try:
            return await coro
        except Exception as exc:
            return dict(error=f"{type(exc).__name__}: {str(exc)[:80]}")

    async def poly():
        markets = await asyncio.to_thread(api.updown_markets, ["btc"])
        tokens = [t for m in markets for t in m["token_ids"]]
        return await feed_age(POLY_WS, _poly, subscribe={"assets_ids": tokens, "type": "market"})

    rest, feed, spot, perp = await asyncio.gather(
        safe(asyncio.to_thread(rest_round_trip)), safe(poly()),
        safe(feed_age(SPOT_WS, _binance)), safe(feed_age(PERP_WS, _binance)))
    return dict(at=time.time(), polymarket_rest=rest, polymarket_feed=feed, binance_spot=spot, binance_perp=perp)


def line(result):
    def part(name):
        v = result[name]
        if "error" in v:
            return f"{name} ERROR {v['error']}"
        if not v.get("n"):
            return f"{name} no data"
        return f"{name} min {v['min']} median {v['median']} p90 {v['p90']} ms"
    return " | ".join(part(k) for k in ("polymarket_rest", "polymarket_feed", "binance_spot", "binance_perp"))


if __name__ == "__main__":
    print(line(asyncio.run(probe())))
