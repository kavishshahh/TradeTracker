"""Download resolved 5-minute up/down markets with every fill in their 5-minute window.
Output: data/updown5m.pkl  rows: slug, coin, start, won_up, fee_rate, trades=[(sec_from_start, outcome_idx, price, size, side)]
Usage: python fetch_updown.py [days=6] [coins=btc,eth]"""
import json, sys, time
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
import requests
from pmq import api

DAYS = float(sys.argv[1]) if len(sys.argv) > 1 else 6
COINS = (sys.argv[2] if len(sys.argv) > 2 else "btc,eth").split(",")
S = requests.Session()


def meta(slugs):
    out = []
    for closed in ("true",):
        rows = api._req("GET", f"{api.GAMMA}/markets", params=[("slug", s) for s in slugs] + [("closed", closed), ("limit", 100)]) or []
        for m in rows:
            px = [float(x) for x in json.loads(m.get("outcomePrices") or "[]")]
            if sorted(px) != [0.0, 1.0] or json.loads(m["outcomes"]) != ["Up", "Down"]:
                continue
            fs = m.get("feeSchedule") or {}
            out.append(dict(slug=m["slug"], cid=m["conditionId"], coin=m["slug"].split("-")[0], start=int(m["slug"].split("-")[-1]),
                            won_up=px[0], fee_rate=float(fs.get("rate") or 0) if m.get("feesEnabled") else 0.0, volume=m.get("volumeNum")))
    return out


def trades(row, max_pages=4):
    rows, cur, st = [], None, row["start"]
    for _ in range(max_pages):
        p = dict(condition_id=row["cid"], limit=1000)
        if cur:
            p["cursor"] = cur
        d = None
        for i in range(5):
            try:
                r = S.get("https://data-api.polymarket.com/v2/trades", params=p, timeout=30)
                if r.status_code == 200:
                    d = r.json(); break
            except requests.RequestException:
                pass
            time.sleep(1.5 * 2 ** i)
        if not d:
            break
        page = d.get("data", [])
        rows += [(x["timestamp"] - st, x["outcome_index"], x["price"], x["size"], x["side"]) for x in page]
        cur = (d.get("pagination") or {}).get("next_cursor")
        if not cur or not page or page[-1]["timestamp"] - st < 90:   # we only need the last ~3.5 minutes
            break
    return sorted(t for t in rows if 0 <= t[0] <= 300)


if __name__ == "__main__":
    now = int(time.time()) // 300 * 300 - 900
    starts = range(now - int(DAYS * 86400), now, 300)
    slugs = [f"{c}-updown-5m-{s}" for c in COINS for s in starts]
    print("markets wanted", len(slugs), flush=True)
    chunks = [slugs[i:i + 40] for i in range(0, len(slugs), 40)]
    with ThreadPoolExecutor(6) as ex:
        metas = [m for part in ex.map(meta, chunks) for m in part]
    print("resolved found", len(metas), flush=True)
    res = []
    with ThreadPoolExecutor(8) as ex:
        for i, t in enumerate(ex.map(trades, metas)):
            res.append(t)
            if i % 250 == 0:
                print(i, flush=True)
    df = pd.DataFrame(metas)
    df["trades"] = res
    df.to_pickle(sys.argv[3] if len(sys.argv) > 3 else "data/updown5m.pkl")
    print("saved", len(df), "median fills", df.trades.map(len).median())
