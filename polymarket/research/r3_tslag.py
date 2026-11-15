"""How late are the timestamps in Polymarket's trade history compared with when the trade happened on the live feed?"""
import numpy as np, requests, collections, time, ticks
rows = ticks.read(); print("tick rows", len(rows))
mk = [r for r in rows if r[1] == "m" and r[4] == 300]
tr = collections.defaultdict(list)
for r in rows:
    if r[1] == "t": tr[r[2]].append(r)
now = time.time(); lags = []; recv = []
for m in mk:
    slug, start, win, up, dn = m[2:7]
    if start + 300 > now - 120: continue
    g = requests.get("https://gamma-api.polymarket.com/markets", params={"slug": slug}, timeout=20).json()
    cid = g[0]["conditionId"]
    api = requests.get("https://data-api.polymarket.com/v2/trades", params=dict(condition_id=cid, limit=1000), timeout=30).json()["data"]
    idx = collections.defaultdict(list)
    for x in api: idx[(x["outcome_index"], round(x["price"], 4), round(x["size"], 2))].append(x["timestamp"])
    n = 0
    for o, tok in ((0, up), (1, dn)):
        for r in tr[tok]:
            k = (o, round(r[3], 4), round(r[4], 2))
            if len(idx.get(k, [])) == 1:        # unambiguous match only
                lags.append(idx[k][0] - r[6] / 1000); recv.append((r[0] - r[6]) / 1000); n += 1
    print(slug, "api trades", len(api), "ws trades", len(tr[up]) + len(tr[dn]), "matched", n)
    if len(lags) > 1500: break
l = np.array(lags); rc = np.array(recv)
print("history timestamp minus live-feed trade time (s): median %.1f mean %.1f p10 %.1f p90 %.1f" % (np.median(l), l.mean(), np.percentile(l, 10), np.percentile(l, 90)))
print("live-feed receive delay here (s): median %.2f p90 %.2f" % (np.median(rc), np.percentile(rc, 90)))
print("history stamp second ahead/behind histogram:", dict(sorted(collections.Counter(np.round(l).astype(int)).items())))
