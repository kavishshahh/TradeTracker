"""Tick recorder for lead-lag research. Writes nothing to Firestore; public feeds only.
  Binance spot + USDT perp best bid/ask (throttled to 50 ms per symbol) and Polymarket top of book
  (price + size, both sides) and trades for the current/next BTC+ETH 5m and 15m up/down markets.
Lines (JSON arrays), t = local receive time in ms:
  [t, "s", sym, bid, ask]            spot quote    [t, "f", sym, bid, ask, exch_ms]   perp quote (exchange event time)
  [t, "S", sym, price, exch_ms]      spot trade (exchange trade time)
  [t, "b", token, bid, bidsz, ask, asksz, server_ts]   Polymarket top of book
  [t, "t", token, price, size, side, server_ts]        Polymarket trade
  [t, "m", slug, start, window, tokUp, tokDown]        market seen
Usage: python record_ticks.py [hours=3]"""
import asyncio, gzip, json, sys, time
import requests, websockets

HOURS = float(sys.argv[1]) if len(sys.argv) > 1 else 3
END = time.time() + HOURS * 3600
import os; os.makedirs("data/ticks", exist_ok=True)
OUT = gzip.open(f"data/ticks/ticks_{int(time.time())}.jsonl.gz", "wt", compresslevel=4)
N = dict(s=0, f=0, b=0, t=0)
def w(*row):
    OUT.write(json.dumps(row, separators=(",", ":")) + "\n")
ms = lambda: int(time.time() * 1000)

async def binance(url, tag):
    last = {}
    while time.time() < END:
        try:
            async with websockets.connect(url, open_timeout=20) as ws:
                async for raw in ws:
                    d = json.loads(raw).get("data", {})
                    now = ms(); sym = d.get("s")
                    if d.get("e") == "aggTrade":
                        if now - last.get("T" + sym, 0) >= 50:
                            last["T" + sym] = now; w(now, "S", sym, float(d["p"]), d["T"])
                        continue
                    if "b" not in d: continue
                    if now - last.get(sym, 0) < 50: continue
                    last[sym] = now
                    if tag == "f": w(now, tag, sym, float(d["b"]), float(d["a"]), d.get("T") or d.get("E"))
                    else: w(now, tag, sym, float(d["b"]), float(d["a"]))
                    N[tag] += 1
                    if time.time() > END: return
        except Exception as e:
            print(tag, "reconnect", type(e).__name__, str(e)[:80], flush=True); await asyncio.sleep(3)

def markets():
    now = int(time.time()); slugs = []
    for win, tag in ((300, "5m"), (900, "15m")):
        base = now // win * win
        slugs += [(f"{c}-updown-{tag}-{base + i * win}", base + i * win, win) for c in ("btc", "eth") for i in (0, 1)]
    r = requests.get("https://gamma-api.polymarket.com/markets", params=[("slug", s[0]) for s in slugs] + [("limit", 100)], timeout=20).json()
    meta = {s[0]: s for s in slugs}; out = []
    for m in r:
        toks = json.loads(m.get("clobTokenIds") or "[]")
        if len(toks) == 2 and m["slug"] in meta:
            out.append((m["slug"], meta[m["slug"]][1], meta[m["slug"]][2], toks[0], toks[1]))
    return out

async def poly_conn(tokens, stop):
    book = {}
    def top(tok, ts):
        b = book.get(tok)
        if not b: return
        bid = max(b[0]) if b[0] else None; ask = min(b[1]) if b[1] else None
        cur = (bid, b[0].get(bid), ask, b[1].get(ask))
        if b[2] != cur:
            b[2] = cur; w(ms(), "b", tok, *cur, ts); N["b"] += 1
    while not stop.is_set() and time.time() < END:
        try:
            async with websockets.connect("wss://ws-subscriptions-clob.polymarket.com/ws/market", max_size=None, ping_interval=None, open_timeout=20) as ws:
                await ws.send(json.dumps({"assets_ids": tokens, "type": "market"}))
                while not stop.is_set():
                    try: raw = await asyncio.wait_for(ws.recv(), 10)
                    except asyncio.TimeoutError:
                        await ws.send("PING"); continue
                    if raw == "PONG": continue
                    data = json.loads(raw)
                    for e in data if isinstance(data, list) else [data]:
                        k = e.get("event_type"); ts = int(e.get("timestamp") or 0)
                        if k == "book":
                            book[e["asset_id"]] = [{float(x["price"]): float(x["size"]) for x in e.get("bids", [])}, {float(x["price"]): float(x["size"]) for x in e.get("asks", [])}, None]
                            top(e["asset_id"], ts)
                        elif k == "price_change":
                            for c in e.get("price_changes", []):
                                b = book.get(c["asset_id"])
                                if b is None: continue
                                side = b[0] if c["side"] == "BUY" else b[1]; p, s = float(c["price"]), float(c["size"])
                                if s <= 0: side.pop(p, None)
                                else: side[p] = s
                                top(c["asset_id"], ts)
                        elif k == "last_trade_price":
                            w(ms(), "t", e["asset_id"], float(e["price"]), float(e.get("size") or 0), e.get("side"), ts); N["t"] += 1
        except Exception as e:
            if stop.is_set(): return
            print("poly reconnect", type(e).__name__, flush=True); await asyncio.sleep(2)

async def poly():
    cur, stop, seen = None, None, set()
    while time.time() < END:
        try:
            ms_ = await asyncio.to_thread(markets)
            for m in ms_:
                if m[0] not in seen:
                    seen.add(m[0]); w(ms(), "m", *m)
            toks = sorted(t for m in ms_ for t in m[3:5])
            if toks and toks != cur:
                if stop: stop.set()
                cur, stop = toks, asyncio.Event()
                asyncio.create_task(poly_conn(toks, stop))
        except Exception as e:
            print("markets", type(e).__name__, flush=True)
        await asyncio.sleep(20)

async def status():
    while time.time() < END:
        await asyncio.sleep(300); OUT.flush(); print(time.strftime("%H:%M:%S"), N, flush=True)

async def main():
    spot = "wss://data-stream.binance.vision/stream?streams=btcusdt@bookTicker/ethusdt@bookTicker/btcusdt@aggTrade/ethusdt@aggTrade"
    perp = "wss://fstream.binance.com/stream?streams=btcusdt@bookTicker/ethusdt@bookTicker"
    tasks = [asyncio.create_task(c) for c in (binance(spot, "s"), binance(perp, "f"), poly(), status())]
    await asyncio.sleep(max(END - time.time(), 0))
    for t in tasks: t.cancel()
    OUT.close(); print("done", N, flush=True)
asyncio.run(main())
