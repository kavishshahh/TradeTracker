"""Read-only Dhan historical client. Auth headers never enter the disk cache."""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import time
import threading
from datetime import date, timedelta
from pathlib import Path

import requests
from dotenv import dotenv_values

from config import REPO_ROOT, ROOT_DIR, BACKEND_ENV


class DhanHistoryClient:
    ENDPOINTS = {"intraday": "/charts/intraday", "rollingoption": "/charts/rollingoption"}
    _rate_lock = threading.Lock()
    _last_global_request = 0.0

    def __init__(self, cache_dir=None, offline=False):
        self.cache_dir = Path(cache_dir or REPO_ROOT / "data/dhan_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.offline = offline
        values = {**dotenv_values(BACKEND_ENV), **os.environ}
        self._headers = {"access-token": values.get("DHAN_ACCESS_TOKEN", ""),
                         "client-id": values.get("DHAN_CLIENT_ID", ""), "Content-Type": "application/json"}
        if not offline and not all(self._headers.values()):
            raise RuntimeError("Save DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN in backend/.env")
        self.session = requests.Session()
        self._last_request = 0.0
        self.downloaded = self.cached = 0

    def request(self, endpoint, payload):
        if endpoint not in self.ENDPOINTS:
            raise ValueError("Only historical chart endpoints are allowed")
        key = hashlib.sha256(json.dumps([endpoint, payload], sort_keys=True).encode()).hexdigest()
        path = self.cache_dir / (key + ".json.gz")
        if path.exists():
            with gzip.open(path, "rt", encoding="utf-8") as f:
                result = json.load(f)
            if result["request"] != payload or result["endpoint"] != endpoint:
                raise RuntimeError("Historical cache metadata mismatch")
            self.cached += 1
            return result["response"]
        if self.offline:
            raise RuntimeError(f"Missing offline cache: {endpoint} {payload['fromDate']}")
        for attempt in range(5):
            with self._rate_lock:
                time.sleep(max(0, 0.27 - (time.monotonic() - DhanHistoryClient._last_global_request)))
                DhanHistoryClient._last_global_request = time.monotonic()
            try:
                response = self.session.post("https://api.dhan.co/v2" + self.ENDPOINTS[endpoint],
                                             headers=self._headers, json=payload, timeout=60)
            except requests.RequestException:
                if attempt == 4:
                    raise RuntimeError("Dhan historical request failed after retries") from None
                time.sleep(2 ** attempt)
                continue
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < 4:
                    time.sleep(2 ** attempt)
                    continue
            if response.status_code != 200:
                raise RuntimeError(f"Dhan historical API returned HTTP {response.status_code}")
            try:
                data = response.json()
            except ValueError:
                raise RuntimeError("Dhan returned invalid JSON") from None
            if data.get("status") == "failure" or "errorCode" in data:
                raise RuntimeError("Dhan historical API returned an error payload")
            expected = "timestamp" if endpoint == "intraday" else "data"
            if expected not in data:
                raise RuntimeError("Dhan historical response has an unexpected schema")
            temp = path.with_suffix(".tmp")
            with gzip.open(temp, "wt", encoding="utf-8") as f:
                json.dump({"endpoint": endpoint, "request": payload, "response": data}, f)
            temp.replace(path)
            self.downloaded += 1
            return data
        raise RuntimeError("Dhan historical API retries exhausted")


def chunks(start: date, end: date, days=28):
    """Half-open chunks; callers also filter API responses to these bounds."""
    while start < end:
        stop = min(start + timedelta(days=days), end)
        yield start, stop
        start = stop


def option_payload(start, end, code, offset, side):
    # This endpoint uses 1=near, 2=next, unlike some other Dhan expiryCode enums.
    # Confirmed by the API samples and Dhan's staff explanation:
    # https://madefortrade.in/t/v2-charts-rollingoption-expirycode-0-gives-dh-905-expirycode-is-required-mapping-changed/60509
    return {"securityId": 13, "exchangeSegment": "NSE_FNO", "instrument": "OPTIDX", "interval": "1",
            "expiryFlag": "WEEK", "expiryCode": code,
            "strike": "ATM" if offset == 0 else f"ATM{offset:+d}", "drvOptionType": side,
            "requiredData": ["close", "volume", "strike", "spot"],
            "fromDate": start.isoformat(), "toDate": end.isoformat()}


def spot_payload(start, end):
    # The intraday endpoint excludes a candle exactly at fromDate in observed
    # responses. Midnight avoids dropping the first 09:15 candle of each chunk.
    return {"securityId": "13", "exchangeSegment": "IDX_I", "instrument": "INDEX",
            "interval": "1", "oi": False,
            "fromDate": f"{start} 00:00:00", "toDate": f"{end} 00:00:00"}


def download(client, start, end, progress=print):
    for first, last in chunks(start, end):
        progress(f"Historical chunk {first} to {last} (end excluded)", flush=True)
        client.request("intraday", spot_payload(first, last))
        for code, offsets in ((1, range(-10, 11)), (2, range(-3, 4))):
            for offset in offsets:
                for side in ("CALL", "PUT"):
                    client.request("rollingoption", option_payload(first, last, code, offset, side))
        progress(f"  cache hits={client.cached}; downloaded={client.downloaded}", flush=True)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Download read-only Dhan historical chart data")
    p.add_argument("--start", type=date.fromisoformat, required=True)
    p.add_argument("--end", type=date.fromisoformat, required=True, help="exclusive")
    a = p.parse_args()
    download(DhanHistoryClient(), a.start, a.end)
