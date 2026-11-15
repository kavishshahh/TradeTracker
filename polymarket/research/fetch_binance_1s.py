import time, sys, numpy as np, requests
from concurrent.futures import ThreadPoolExecutor
DAYS = 6.3
end = int(time.time()) // 1000 * 1000
start = end - int(DAYS * 86400)
S = requests.Session()
def chunk(args):
    sym, s = args
    for i in range(6):
        try:
            r = S.get("https://data-api.binance.vision/api/v3/klines", params=dict(symbol=sym, interval="1s", startTime=s * 1000, limit=1000), timeout=30)
            if r.status_code == 200:
                return [(int(x[0] // 1000), float(x[4])) for x in r.json()]
        except requests.RequestException:
            pass
        time.sleep(1.5 * 2 ** i)
    return []
out = {}
for sym in ("BTCUSDT", "ETHUSDT"):
    with ThreadPoolExecutor(6) as ex:
        rows = [x for part in ex.map(chunk, [(sym, s) for s in range(start, end, 1000)]) for x in part]
    a = np.array(sorted(set(rows)))
    out[sym] = a; print(sym, len(a), flush=True)
np.save("data/binance_1s.npy", out, allow_pickle=True)
