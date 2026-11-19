"""Screen Polymarket wallets for copy trading, with the lessons from the first copy accounts built in.

The first four copy accounts (16-19 Nov 2026) failed in three ways, and each has a filter here:

1. Copy delay ate the edge (copy_substantial_service, a fast in-play sports trader: -55% in 3 days).
   -> Every copied bet is priced from the market's price ONE MINUTE after the wallet's trade, plus 1c,
      and skipped if that is more than 2c above the wallet's price (the live rule's limit). The live
      worker arrives in about 0.35 s, so this is stricter than live on purpose.
2. A dead wallet passed on old bets settling (copy_6e82_nba).
   -> At least MIN_RECENT first entries in the last 14 days.
3. A small sample picked for looking good (copy_goool_esports: +28%/bet on 80 entries, then 2 of 7 live).
   -> At least MIN_RESOLVED resolved copied bets, a t-stat of 2, and a profit in BOTH the older and the
      newer half of them.

Stages (public read-only APIs, nothing is written anywhere but the output CSV):
  candidates  data-api v2 leaderboard, top N by PnL for the month and the week in every category
  entries     data-api v2 activity: each wallet's FIRST buy per market of $5+ at 3-97c, last DAYS days
  own edge    the wallet's own return per bet at its own price (resolution from Gamma); cheap prefilter
  copy test   CLOB prices-history at +60 s for the wallets that pass the prefilter, with taker fees
  hold-out    a wallet that passes must also profit when copied on its bets from the 75 days before

    .venv\\Scripts\\python.exe -u research\\screen_copy_wallets.py            # about 10-20 minutes
    .venv\\Scripts\\python.exe -u research\\screen_copy_wallets.py --top 10   # quick run

Results are evidence for a PAPER account only: several hundred wallets are screened, so a few will
pass by luck even with the split-half check.
"""
from __future__ import annotations

import argparse
import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pmq import api  # noqa: E402

DATA = "https://data-api.polymarket.com/v2"
CATEGORIES = ("OVERALL", "POLITICS", "SPORTS", "CRYPTO", "CULTURE", "ECONOMICS", "TECH", "FINANCE",
              "WEATHER", "ESPORTS", "MENTIONS")
MIN_USD, MIN_PRICE, MAX_PRICE = 5.0, 0.03, 0.97
MAX_CHASE, SLIP, DELAY_S = 0.02, 0.01, 60
MIN_RECENT, MIN_RESOLVED, MAX_PER_DAY = 8, 40, 30
SAMPLE = 100                       # most recent resolved entries per wallet sent to the copy test
HOLDOUT_DAYS = 75                  # older window used only to confirm a wallet that passed
CURRENT = {"0x2c335066fe58fe9237c3d3dc7b275c2a034a0563": "copy_substantial_service",
           "0xc8b9a30184244d427169cf62485dde6041b2b836": "copy_c8b9_politics",
           "0xda3a9b7afff7b44ad4fd75308723194e0a11381f": "copy_goool_esports",
           "0x6e82b93eb57b01a63027bd0c6d2f3f04934a752c": "copy_6e82_nba"}

S = requests.Session()
S.headers["User-Agent"] = "pmq-research/1.0"


def get(path, **params):
    for i in range(5):
        try:
            r = S.get(f"{DATA}/{path}", params=params, timeout=30)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (400, 404):
                return {"data": []}
        except (requests.RequestException, ValueError):
            pass
        time.sleep(1.5 * 2 ** i)
    return {"data": []}


def candidates(top):
    found = {}
    for cat in CATEGORIES:
        for period in ("MONTH", "WEEK"):
            for row in get("leaderboard", category=cat, timePeriod=period, orderBy="PNL", limit=top).get("data", []):
                w = row["user_id"].lower()
                found.setdefault(w, dict(wallet=w, name=row.get("user_name") or "", cats=set(), lb_pnl=0.0, lb_volume=0.0))
                found[w]["cats"].add(cat.lower())
                found[w]["lb_pnl"] = max(found[w]["lb_pnl"], float(row.get("pnl") or 0))
                found[w]["lb_volume"] = max(found[w]["lb_volume"], float(row.get("volume") or 0))
    for w, name in CURRENT.items():            # calibration: the screen should reject the failed ones
        found.setdefault(w, dict(wallet=w, name=name, cats={"current"}, lb_pnl=0.0, lb_volume=0.0))
    return list(found.values())


def entries(wallet, days):
    """First qualifying buy per market, newest first, plus activity counts."""
    since = time.time() - days * 86400
    rows, cursor = [], None
    for _ in range(30):
        page = get("activity", user=wallet, type="TRADE", limit=500, **({"cursor": cursor} if cursor else {}))
        data = page.get("data", [])
        rows += data
        cursor = (page.get("pagination") or {}).get("next_cursor")
        if not data or not cursor or data[-1]["timestamp"] < since:
            break
    rows = list({(r.get("transaction_hash"), r.get("token_id"), r.get("size")): r for r in rows}.values())
    first, buys_per_market = {}, {}
    for r in sorted(rows, key=lambda r: r["timestamp"]):
        if r["timestamp"] < since or r.get("side") != "BUY":
            continue
        cid = r["condition_id"]
        buys_per_market[cid] = buys_per_market.get(cid, 0) + 1
        price, usd = float(r.get("price") or 0), float(r.get("usdc_size") or 0)
        if cid in first or usd < MIN_USD or not (MIN_PRICE <= price <= MAX_PRICE):
            continue
        first[cid] = dict(cid=cid, t=int(r["timestamp"]), price=price, usd=usd, token=r["token_id"],
                          outcome_index=int(r.get("outcome_index") or 0), title=r.get("title") or "", slug=r.get("event_slug") or "")
    ents = sorted(first.values(), key=lambda e: -e["t"])
    fills = sorted(buys_per_market.values())
    return ents, (fills[len(fills) // 2] if fills else 0)


def resolve(cids):
    """condition_id -> (closed and decided, payout per outcome, fee rate, end time)."""
    out, cids = {}, list(cids)
    chunks = [cids[i:i + 50] for i in range(0, len(cids), 50)]
    with ThreadPoolExecutor(4) as pool:
        for part in pool.map(api.markets_by_condition, chunks):
            for cid, m in part.items():
                p = m["outcome_prices"]
                decided = bool(m["closed"]) and len(p) >= 2 and all(x in (0.0, 1.0) for x in p)
                out[cid] = (decided, p, m["fee_rate"], m["end"])
    return out


def ret(entry_price, payout, fee_rate):
    cost = entry_price + fee_rate * entry_price * (1 - entry_price)
    return payout / cost - 1


def stats(xs):
    n = len(xs)
    if n < 2:
        return dict(n=n, mean=xs[0] if xs else float("nan"), t=0.0)
    m = sum(xs) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1)) or 1e-9
    return dict(n=n, mean=m, t=m / sd * math.sqrt(n))


def copy_price(e):
    """Market price DELAY_S after the wallet's trade (first point at or after it, within 15 minutes)."""
    try:
        pts = api.price_history(e["token"], e["t"], e["t"] + 900, fidelity=1)
    except RuntimeError:
        return None
    later = [p for t, p in pts if t >= e["t"] + DELAY_S]
    return float(later[0]) if later else None


def holdout_returns(ents):
    """Copy returns (same rule as the main test) on up to SAMPLE resolved entries."""
    res = resolve({e["cid"] for e in ents})
    done = [e for e in ents if res.get(e["cid"], (False,))[0]][:SAMPLE]
    for e in done:
        _, payout, fee, _ = res[e["cid"]]
        e["payout"], e["fee"] = payout[e["outcome_index"]], fee
    with ThreadPoolExecutor(6) as pool:
        cps = list(pool.map(copy_price, done))
    rets = [ret(min(cp + SLIP, e["price"] + MAX_CHASE, 0.99), e["payout"], e["fee"])
            for e, cp in zip(done, cps) if cp is not None and cp <= e["price"] + MAX_CHASE]
    return stats(rets) if rets else dict(n=0, mean=float("nan"), t=0.0)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=25, help="leaderboard rows per category and period")
    ap.add_argument("--days", type=int, default=45)
    ap.add_argument("--out", default=str(Path(__file__).with_name("copy_screen.csv")))
    a = ap.parse_args(argv)
    now = time.time()

    cands = candidates(a.top)
    print(f"{len(cands)} candidate wallets", flush=True)
    with ThreadPoolExecutor(4) as pool:
        got = list(pool.map(lambda c: entries(c["wallet"], a.days), cands))
    for c, (ents, med_fills) in zip(cands, got):
        c["entries"] = ents
        c["recent14"] = sum(e["t"] >= now - 14 * 86400 for e in ents)
        c["per_day"] = len(ents) / a.days
        c["median_fills_per_market"] = med_fills
        c["share_85c_plus"] = (sum(e["price"] >= 0.85 for e in ents) / len(ents)) if ents else 0.0
    active = [c for c in cands if c["recent14"] >= MIN_RECENT and c["per_day"] <= MAX_PER_DAY]
    print(f"{len(active)} active (>= {MIN_RECENT} new markets in 14 days, <= {MAX_PER_DAY}/day)", flush=True)

    res = resolve({e["cid"] for c in active for e in c["entries"]})
    for c in active:
        done = [e for e in c["entries"] if res.get(e["cid"], (False,))[0]]
        for e in done:
            _, payout, fee, end = res[e["cid"]]
            e["payout"], e["fee"] = payout[e["outcome_index"]], fee
        c["resolved"] = done
        c["own"] = stats([ret(e["price"], e["payout"], e["fee"]) for e in done])
    pre = [c for c in active if c["own"]["n"] >= MIN_RESOLVED and c["own"]["mean"] >= 0.05]
    pre += [c for c in active if c["wallet"] in CURRENT and c not in pre]
    print(f"{len(pre)} pass the own-edge prefilter (>= {MIN_RESOLVED} resolved, >= +5%/bet at their own price)", flush=True)

    jobs = [(c, e) for c in pre for e in c["resolved"][:SAMPLE]]
    with ThreadPoolExecutor(6) as pool:
        prices = list(pool.map(lambda ce: copy_price(ce[1]), jobs))
    for (c, e), p in zip(jobs, prices):
        e["copy_price"] = p
    rows = []
    for c in pre:
        tested = [e for e in c["resolved"][:SAMPLE] if e.get("copy_price") is not None]
        filled = [e for e in tested if e["copy_price"] <= e["price"] + MAX_CHASE]
        rets = []
        for e in sorted(filled, key=lambda e: e["t"]):
            entry = min(e["copy_price"] + SLIP, e["price"] + MAX_CHASE, 0.99)
            rets.append(ret(entry, e["payout"], e["fee"]))
        half = len(rets) // 2
        old, new, allr = stats(rets[:half]), stats(rets[half:]), stats(rets)
        passed = (allr["n"] >= MIN_RESOLVED and allr["mean"] > 0.05 and allr["t"] >= 2.0
                  and old["mean"] > 0 and new["mean"] > 0)
        rows.append(dict(wallet=c["wallet"], name=c["name"], current=CURRENT.get(c["wallet"], ""),
                         categories="/".join(sorted(c["cats"])), lb_pnl=round(c["lb_pnl"]), lb_volume=round(c["lb_volume"]),
                         new_markets_45d=len(c["entries"]), new_markets_14d=c["recent14"],
                         median_fills_per_market=c["median_fills_per_market"], share_85c_plus=round(c["share_85c_plus"], 2),
                         own_n=c["own"]["n"], own_mean=round(c["own"]["mean"], 3),
                         tested=len(tested), fill_rate=round(len(filled) / len(tested), 2) if tested else 0,
                         copy_n=allr["n"], copy_mean=round(allr["mean"], 3) if rets else None, copy_t=round(allr["t"], 2),
                         older_half=round(old["mean"], 3) if rets else None, newer_half=round(new["mean"], 3) if rets else None,
                         win_rate=round(sum(r > 0 for r in rets) / len(rets), 2) if rets else None,
                         example=(c["resolved"][0]["title"][:60] if c["resolved"] else ""),
                         holdout_n=None, holdout_mean=None, passed=passed))
    # Hold-out: a wallet that passes on the last DAYS days must also profit when copied on its bets from the
    # HOLDOUT_DAYS before that, which played no part in picking it. (19 Nov 2026: both wallets that passed the
    # 45-day screen lost 6-40% per bet here.)
    by_wallet = {c["wallet"]: c for c in pre}
    for r in rows:
        if not r["passed"]:
            continue
        older, _ = entries(r["wallet"], a.days + HOLDOUT_DAYS)
        older = [e for e in older if e["t"] < now - a.days * 86400]
        ho = holdout_returns(older)
        r.update(holdout_n=ho["n"], holdout_mean=round(ho["mean"], 3) if ho["n"] else None)
        r["passed"] = ho["n"] >= 20 and ho["mean"] > 0
        print(f"hold-out {r['wallet']} ({by_wallet[r['wallet']]['name']}): {ho['n']} bets, {ho['mean']:+.3f}/bet", flush=True)
    rows.sort(key=lambda r: (not r["passed"], -(r["copy_t"] or 0)))
    import csv
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["wallet"])
        w.writeheader()
        w.writerows(rows)
    keys = ("wallet", "name", "current", "categories", "new_markets_14d", "own_mean", "fill_rate", "copy_n", "copy_mean",
            "copy_t", "older_half", "newer_half", "win_rate", "holdout_mean", "passed")
    for r in rows:
        print({k: r[k] for k in keys})
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
