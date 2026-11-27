"""Download expired and current MCX crude oil option history from Dhan's rolling-option endpoint.

Dhan serves the near-month series as moving at-the-money offsets (ATM-3 .. ATM+3), one day per request,
with the futures price in ``spot``. One file per day is kept, so a stopped run resumes where it left off.

    python download_rolling.py [--symbol CRUDEOIL] [--start 2025-01-01]
Needs a current DHAN_ACCESS_TOKEN in backend/.env (no TOTP login is attempted here).
"""
import argparse
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests
from dotenv import dotenv_values

STORE = Path(__file__).resolve().parents[1] / "data" / "mcx_crude"
ENV = Path(__file__).resolve().parents[2] / "backend" / ".env"
UNDERLYING = {"CRUDEOIL": 294, "CRUDEOILM": 556}
OFFSETS = ["ATM-3", "ATM-2", "ATM-1", "ATM", "ATM+1", "ATM+2", "ATM+3"]
FIELDS = ["open", "high", "low", "close", "volume", "strike", "spot", "oi", "iv"]
MAX_REQUESTS = 7500          # Dhan refused after about 9,800 in one sitting; stay well under

values = dotenv_values(ENV)
HEADERS = {"client-id": values.get("DHAN_CLIENT_ID", ""), "access-token": values.get("DHAN_ACCESS_TOKEN", ""),
           "Content-Type": "application/json"}
session = requests.Session()
made = 0


def post(endpoint, payload):
    global made
    for attempt in range(4):
        time.sleep(0.28)
        made += 1
        try:
            r = session.post("https://api.dhan.co/v2" + endpoint, headers=HEADERS, json=payload, timeout=60)
        except requests.RequestException:
            time.sleep(2 ** attempt)
            continue
        if r.status_code == 429:
            raise SystemExit("HTTP 429: stop and wait an hour")
        if r.status_code in (401, 403):
            raise SystemExit("Token refused: put a current DHAN_ACCESS_TOKEN in backend/.env")
        if r.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        try:
            return r.json()
        except ValueError:
            return {}
    return {}


def rolling(sec, day, offset, side):
    data = post("/charts/rollingoption", {
        "securityId": sec, "exchangeSegment": "MCX_COMM", "instrument": "OPTFUT", "interval": "1", "expiryFlag": "MONTH",
        "expiryCode": 1, "strike": offset, "drvOptionType": side, "requiredData": FIELDS,
        "fromDate": str(day), "toDate": str(day + timedelta(days=1))}).get("data")
    part = (data or {}).get("ce" if side == "CALL" else "pe") if isinstance(data, dict) else None
    if not part or not part.get("timestamp"):
        return None
    count = len(part["timestamp"])
    frame = pd.DataFrame({k: v for k, v in part.items() if isinstance(v, list) and len(v) == count})
    frame["time"] = pd.to_datetime(frame.timestamp, unit="s") + pd.Timedelta(hours=5, minutes=30)
    frame = frame.loc[frame.time.dt.date == day].drop(columns="timestamp")      # toDate is inclusive
    frame["side"] = "CE" if side == "CALL" else "PE"
    frame["offset"] = OFFSETS.index(offset) - 3
    return frame


def session_days(symbol, start, end):
    master = pd.read_csv(sorted(STORE.glob("mcx_master_*.csv"))[-1], low_memory=False)
    fut = master.loc[master.UNDERLYING_SYMBOL.eq(symbol) & master.INSTRUMENT.eq("FUTCOM")].sort_values("SM_EXPIRY_DATE").iloc[0]
    d = post("/charts/historical", {"securityId": str(int(fut.SECURITY_ID)), "exchangeSegment": "MCX_COMM", "instrument": "FUTCOM",
                                    "expiryCode": 0, "oi": False, "fromDate": str(start), "toDate": str(end)})
    days = sorted({(pd.Timestamp(t, unit="s") + pd.Timedelta(hours=5, minutes=30)).date() for t in d.get("timestamp", [])})
    return [x for x in days if start <= x < end]


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="CRUDEOIL", choices=list(UNDERLYING))
    p.add_argument("--start", type=date.fromisoformat, default=date(2024, 10, 1))
    p.add_argument("--end", type=date.fromisoformat, default=date.today(), help="exclusive")
    a = p.parse_args()
    sec = UNDERLYING[a.symbol]
    out = STORE / f"rolling_{a.symbol}"
    out.mkdir(parents=True, exist_ok=True)
    days = session_days(a.symbol, a.start, a.end)
    print("session days", len(days), days[0], days[-1], flush=True)
    # find where history begins: step forward a month at a time until the at-the-money call has rows
    todo = [d for d in days if not (out / f"{d}.csv.gz").exists() and not (out / f"{d}.empty").exists()]
    first_have = next((d for d in days if (out / f"{d}.csv.gz").exists()), None)
    if first_have is None:
        probe = days[0]
        while probe is not None and rolling(sec, probe, "ATM", "CALL") is None:
            print("no data on", probe, flush=True)
            later = [d for d in days if d >= probe + timedelta(days=30)]
            probe = later[0] if later else None
        if probe is None:
            sys.exit("no history found")
        todo = [d for d in todo if d >= probe - timedelta(days=31)]
    for day in todo:
        if made > MAX_REQUESTS:
            print("request budget reached; run again in an hour", flush=True)
            break
        first = rolling(sec, day, "ATM", "CALL")
        if first is None:
            (out / f"{day}.empty").write_text("")
            continue
        parts = [first] + [f for offset in OFFSETS for side in ("CALL", "PUT") if (offset, side) != ("ATM", "CALL")
                           for f in [rolling(sec, day, offset, side)] if f is not None]
        pd.concat(parts, ignore_index=True).to_csv(out / f"{day}.csv.gz", index=False)
        print(day, "rows", sum(len(x) for x in parts), "requests", made, flush=True)
    print("finished; files", len(list(out.glob("*.csv.gz"))), "requests", made, flush=True)
