"""Download MCX crude oil 1-minute bars (futures and near-the-money options still listed) from Dhan. Run once, after login works: python download.py"""
import io, sys, time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, r"C:\Users\kavis\OneDrive\Desktop\TradeTracker\algos\zen_credit")
import pandas as pd
from backtest.dhan_history import DhanHistoryClient

OUT = Path(__file__).parent
STORE = Path(r"C:\Users\kavis\OneDrive\Desktop\TradeTracker\algos\data\mcx_crude")
STORE.mkdir(parents=True, exist_ok=True)
client = DhanHistoryClient(cache_dir=STORE / "cache", offline=True)   # session and headers only
IST = timezone(timedelta(hours=5, minutes=30))
today = datetime.now(IST).date()
from dotenv import dotenv_values
from config import BACKEND_ENV
token = dotenv_values(BACKEND_ENV).get("DHAN_ACCESS_TOKEN")     # fixed token only: no TOTP login from here
if not token:
    raise SystemExit("Put a current DHAN_ACCESS_TOKEN in backend/.env")
print("token ok", flush=True)

master_path = STORE / f"mcx_master_{today}.csv"
if not master_path.exists():
    r = client.session.get("https://images.dhan.co/api-data/api-scrip-master-detailed.csv", timeout=120)
    m = pd.read_csv(io.StringIO(r.text), low_memory=False)
    m.loc[m.EXCH_ID.eq("MCX")].to_csv(master_path, index=False)
m = pd.read_csv(master_path, low_memory=False)
c = m.loc[m.UNDERLYING_SYMBOL.isin(["CRUDEOIL", "CRUDEOILM"])].copy()
requests_made = 0


def post(endpoint, payload):
    global requests_made
    for attempt in range(4):
        time.sleep(0.3)
        requests_made += 1
        r = client.session.post("https://api.dhan.co/v2" + endpoint, json=payload, timeout=60,
                                headers={"client-id": dotenv_values(BACKEND_ENV).get("DHAN_CLIENT_ID", ""), "Content-Type": "application/json", "access-token": token})
        if r.status_code == 429:
            print("HTTP 429, stopping", flush=True)
            raise SystemExit(2)
        if r.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        try:
            return r.status_code, r.json()
        except ValueError:
            return r.status_code, r.text[:200]
    return 599, "retries exhausted"


def frame(d):
    if not (isinstance(d, dict) and d.get("timestamp")):
        return None
    return pd.DataFrame({k: d[k] for k in ("timestamp", "open", "high", "low", "close", "volume") if k in d})


def describe(tag, status, d):
    f = frame(d)
    if f is None:
        print(tag, status, str(d)[:250], flush=True)
    else:
        t = pd.to_datetime(f.timestamp, unit="s", utc=True).dt.tz_convert(IST)
        print(tag, status, "rows", len(f), t.iloc[0], "->", t.iloc[-1], flush=True)


def intraday(sec, inst, start, end):
    return post("/charts/intraday", {"securityId": str(sec), "exchangeSegment": "MCX_COMM", "instrument": inst, "interval": "1",
                                     "oi": False, "fromDate": f"{start} 00:00:00", "toDate": f"{end} 00:00:00"})


fut = c.loc[c.INSTRUMENT.eq("FUTCOM")].sort_values("SM_EXPIRY_DATE")
dec = fut.loc[fut.UNDERLYING_SYMBOL.eq("CRUDEOIL")].iloc[0]

# ---- probes
describe("FUT 5d", *intraday(dec.SECURITY_ID, "FUTCOM", today - timedelta(days=5), today + timedelta(days=1)))
describe("FUT 90d window", *intraday(dec.SECURITY_ID, "FUTCOM", today - timedelta(days=90), today + timedelta(days=1)))
describe("FUT 400d back", *intraday(dec.SECURITY_ID, "FUTCOM", today - timedelta(days=400), today - timedelta(days=372)))
for sec, inst in ((int(dec.UNDERLYING_SECURITY_ID), "OPTFUT"), (int(dec.SECURITY_ID), "OPTFUT"), (int(dec.UNDERLYING_SECURITY_ID), "OPTFUT_M")):
    p = {"securityId": sec, "exchangeSegment": "MCX_COMM", "instrument": inst.replace("_M", ""), "interval": "1",
         "expiryFlag": "MONTH", "expiryCode": 1 if inst == "OPTFUT" else 2,
         "strike": "ATM", "drvOptionType": "CALL", "requiredData": ["close", "volume", "strike", "spot"],
         "fromDate": "2026-10-06", "toDate": "2026-10-07"}
    s, d = post("/charts/rollingoption", p)
    print("ROLLING", sec, inst, s, str(d)[:250], flush=True)
for code in (0, 1, 2):
    s, d = post("/charts/historical", {"securityId": str(dec.SECURITY_ID), "exchangeSegment": "MCX_COMM", "instrument": "FUTCOM",
                                       "expiryCode": code, "oi": False, "fromDate": "2022-01-01", "toDate": str(today)})
    describe(f"DAILY code{code}", s, d)
# continuous / underlying id on the intraday endpoint
describe("UNDERLYING id intraday", *intraday(int(dec.UNDERLYING_SECURITY_ID), "FUTCOM", today - timedelta(days=400), today - timedelta(days=372)))


# ---- download everything the active contracts offer
def series(sec, inst, max_windows=8):
    parts, end = [], today + timedelta(days=1)
    for k in range(max_windows):
        start = end - timedelta(days=28)
        s, d = intraday(sec, inst, start, end)
        f = frame(d)
        if f is None or f.empty:
            if k >= 1:
                break
        else:
            parts.append(f)
        end = start
    if not parts:
        return None
    return pd.concat(parts).drop_duplicates("timestamp").sort_values("timestamp")


frames = []
last = {}
for _, row in fut.loc[fut.SM_EXPIRY_DATE <= "2027-03-01"].iterrows():
    f = series(row.SECURITY_ID, "FUTCOM")
    if f is None:
        continue
    f["security_id"] = int(row.SECURITY_ID)
    frames.append(f)
    last.setdefault(row.UNDERLYING_SYMBOL, (f.close.min(), f.close.max()))
    print("FUT", row.DISPLAY_NAME, len(f), pd.to_datetime(f.timestamp.iloc[0], unit="s"), flush=True)
print("price ranges", last, flush=True)

opt = c.loc[c.INSTRUMENT.eq("OPTFUT") & (c.SM_EXPIRY_DATE <= "2027-01-31")]
done = 0
for (und, expiry), group in opt.groupby(["UNDERLYING_SYMBOL", "SM_EXPIRY_DATE"]):
    lo, hi = last.get(und, last.get("CRUDEOIL"))
    pick = group.loc[group.STRIKE_PRICE.between(lo * 0.93, hi * 1.07)]
    print(und, expiry, "strikes", pick.STRIKE_PRICE.min(), pick.STRIKE_PRICE.max(), "series", len(pick), flush=True)
    for _, row in pick.iterrows():
        f = series(row.SECURITY_ID, "OPTFUT")
        done += 1
        if f is not None:
            f["security_id"] = int(row.SECURITY_ID)
            frames.append(f)
        if done % 40 == 0:
            print("  series done", done, "requests", requests_made, flush=True)

allbars = pd.concat(frames, ignore_index=True)
allbars.to_csv(STORE / f"bars_1min_{today}.csv.gz", index=False)
print("saved rows", len(allbars), "series", allbars.security_id.nunique(), "requests", requests_made, flush=True)
