"""Thin, retrying clients for the public Polymarket (Gamma, CLOB) and Binance APIs."""
import json
import time

import pandas as pd
import requests

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
BINANCE = "https://data-api.binance.vision/api/v3"

_s = requests.Session()
_s.headers["User-Agent"] = "pmq-research/1.0"


def _req(method, url, retries=5, **kw):
    last = None
    for i in range(retries):
        try:
            r = _s.request(method, url, timeout=30, **kw)
            if r.status_code == 200 and r.text.strip():
                return r.json()
            last = f"{r.status_code} {r.text[:120]}"
            if r.status_code == 404:
                return None
        except (requests.RequestException, ValueError) as e:
            last = str(e)
        time.sleep(min(1.5 * 2 ** i, 20))
    raise RuntimeError(f"{method} {url} failed: {last}")


# ---------------------------------------------------------------- Gamma
def _parse_market(m):
    def js(k, default="[]"):
        v = m.get(k) or default
        return json.loads(v) if isinstance(v, str) else v

    fs = m.get("feeSchedule") or {}
    ev = (m.get("events") or [{}])[0]
    return dict(
        condition_id=m.get("conditionId"), question=m.get("question") or "", slug=m.get("slug") or "",
        event_slug=ev.get("slug") or "", outcomes=js("outcomes"),
        outcome_prices=[float(x) for x in js("outcomePrices")], token_ids=js("clobTokenIds"),
        active=m.get("active"), closed=m.get("closed"), accepting=m.get("acceptingOrders"),
        start=m.get("startDate"), end=m.get("endDate"), game_start=m.get("gameStartTime"),
        sports_type=m.get("sportsMarketType"), neg_risk=m.get("negRisk"),
        fee_rate=float(fs.get("rate") or 0) if m.get("feesEnabled") else 0.0,
        min_size=float(m.get("orderMinSize") or 5), tick=float(m.get("orderPriceMinTickSize") or 0.01),
        best_bid=m.get("bestBid"), best_ask=m.get("bestAsk"), volume24h=m.get("volume24hr"),
        liquidity=float(m.get("liquidityNum") or 0), uma=m.get("umaResolutionStatus"),
    )


def active_markets(max_days=31, max_pages=600, **filters):
    """Open, order-book-enabled markets ending within `max_days` (keyset-paged, 100/page)."""
    now = pd.Timestamp.now(tz="UTC")
    base = dict(closed="false", active="true", limit=100, end_date_min=(now - pd.Timedelta(hours=12)).isoformat(),
                end_date_max=(now + pd.Timedelta(days=max_days)).isoformat(), **filters)
    out, cur = [], None
    for _ in range(max_pages):
        r = _req("GET", f"{GAMMA}/markets/keyset", params={**base, **({"after_cursor": cur} if cur else {})}) or {}
        rows = r.get("markets") or []
        out += [_parse_market(m) for m in rows if m.get("enableOrderBook") and m.get("clobTokenIds")]
        cur = r.get("next_cursor")
        if not cur or not rows:
            break
    return out


def event_markets(tag_slug, max_days=31, max_pages=100):
    """Open markets inside events carrying `tag_slug` (e.g. 'crypto-prices', 'sports')."""
    now = pd.Timestamp.now(tz="UTC")
    base = dict(tag_slug=tag_slug, closed="false", limit=100, end_date_min=now.isoformat(),
                end_date_max=(now + pd.Timedelta(days=max_days)).isoformat())
    out, cur = [], None
    for _ in range(max_pages):
        r = _req("GET", f"{GAMMA}/events/keyset", params={**base, **({"after_cursor": cur} if cur else {})}) or {}
        evs = r.get("events") or []
        for e in evs:
            for m in e.get("markets") or []:
                if m.get("closed") or not m.get("enableOrderBook") or not m.get("clobTokenIds"):
                    continue
                m.setdefault("events", [{"slug": e.get("slug")}])
                out.append(_parse_market(m))
        cur = r.get("next_cursor")
        if not cur or not evs:
            break
    return out


def updown_markets(coins, window=300, ahead=2):
    """The current and next few 5-minute up/down markets, found by their predictable slugs."""
    import time as _t
    now = int(_t.time()) // window * window
    slugs = [f"{c}-updown-5m-{now + i * window}" for c in coins for i in range(ahead + 1)]
    rows = _req("GET", f"{GAMMA}/markets", params=[("slug", s) for s in slugs] + [("closed", "false"), ("limit", 100)]) or []
    return [_parse_market(m) for m in rows if m.get("enableOrderBook") and m.get("clobTokenIds")]


def market_query(q):
    """Dispatch a strategy's `market_query` dict to the right Gamma listing."""
    q = dict(q)
    kind = q.pop("kind", "markets")
    if kind == "updown5m":
        return updown_markets(q["coins"])
    if kind == "events":
        return event_markets(q["tag_slug"], q.get("days", 31))
    types = q.pop("sports_market_types", None)
    days = q.pop("days", 31)
    if types:
        out = []
        for t in types:
            out += active_markets(max_days=days, sports_market_types=t, **q)
        return out
    return active_markets(max_days=days, **q)


def markets_by_condition(cids):
    out = []
    for i in range(0, len(cids), 50):
        chunk = cids[i:i + 50]
        for closed in ("true", "false"):
            q = [("condition_ids", c) for c in chunk] + [("limit", 100), ("closed", closed)]
            out += [_parse_market(m) for m in (_req("GET", f"{GAMMA}/markets", params=q) or [])]
    return {m["condition_id"]: m for m in out}


# ---------------------------------------------------------------- CLOB
def books(token_ids):
    """token_id -> {'bids': [(p, size)...] best first, 'asks': [...] best first}"""
    out = {}
    for i in range(0, len(token_ids), 100):
        chunk = token_ids[i:i + 100]
        res = _req("POST", f"{CLOB}/books", json=[{"token_id": t} for t in chunk]) or []
        for b in res:
            bids = sorted(((float(x["price"]), float(x["size"])) for x in b.get("bids", [])), reverse=True)
            asks = sorted((float(x["price"]), float(x["size"])) for x in b.get("asks", []))
            out[b["asset_id"]] = dict(bids=bids, asks=asks, ts=time.time())
    return out


def price_history(token_id, start_ts, end_ts, fidelity=1):
    pts = []
    for s in range(int(start_ts), int(end_ts), 6 * 86400):
        h = _req("GET", f"{CLOB}/prices-history",
                 params=dict(market=token_id, startTs=s, endTs=min(s + 6 * 86400, int(end_ts)), fidelity=fidelity))
        pts += [(x["t"], x["p"]) for x in (h or {}).get("history", [])]
    return sorted(pts)


# ---------------------------------------------------------------- Binance
def klines(symbol, start_ts, end_ts=None, interval="1h"):
    rows, s = [], int(start_ts * 1000)
    end_ms = int((end_ts or time.time()) * 1000)
    while s < end_ms:
        r = _req("GET", f"{BINANCE}/klines", params=dict(symbol=symbol, interval=interval, startTime=s, limit=1000))
        if not r:
            break
        rows += r
        s = r[-1][0] + 1
        if len(r) < 1000:
            break
    df = pd.DataFrame([x[:5] for x in rows], columns=["t", "o", "h", "l", "c"]).astype(float)
    df["t"] = (df.t / 1000).astype(int)
    return df.set_index("t")


def spot(symbol):
    return float(_req("GET", f"{BINANCE}/ticker/price", params=dict(symbol=symbol))["price"])
