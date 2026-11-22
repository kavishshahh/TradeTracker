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
        self._auth = None
        if not offline:
            from data.providers.dhan_auth import DhanAuthError, shared_source
            try:
                self._auth = shared_source(values)   # fixed token, or TOTP renewal (DHAN_PIN + DHAN_TOTP_SECRET)
            except DhanAuthError as exc:
                raise RuntimeError(f"{exc} in backend/.env") from None
        self._headers = {"client-id": self._auth.client_id if self._auth else "", "Content-Type": "application/json"}
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
        if endpoint == "rollingoption" and self._span_days(payload) > 1:
            data = self._rolling_by_day(payload)
            self._store(path, endpoint, payload, data)
            return data
        data = self._fetch(endpoint, payload)
        self._store(path, endpoint, payload, data)
        return data

    @staticmethod
    def _store(path, endpoint, payload, data):
        temp = path.with_suffix(".tmp")
        with gzip.open(temp, "wt", encoding="utf-8") as f:
            json.dump({"endpoint": endpoint, "request": payload, "response": data}, f)
        temp.replace(path)

    # ------------------------------------------------------------------ one day per rolling-option request
    # Since November 2026 Dhan serves at most one day of expired-options data per request (a longer range
    # returns HTTP 400 DH-905). A multi-day request is therefore answered from one request per session day
    # and merged back into the old response shape, so callers and the cache of earlier ranges are unchanged.
    DAY_SPANS = (1, 0)      # toDate = day + span; the first span Dhan accepts is kept for the session
    _day_span = None

    @staticmethod
    def _span_days(payload):
        try:
            first, last = (date.fromisoformat(str(payload[k])[:10]) for k in ("fromDate", "toDate"))
        except (KeyError, ValueError):
            return 0
        return (last - first).days

    def _session_days(self, first, last):
        """Dates in [first, last) that have index candles (one intraday request, normally already cached)."""
        stamps = self.request("intraday", spot_payload(first, last)).get("timestamp") or []
        days = sorted({date.fromordinal(_EPOCH_ORDINAL + int((int(t) + IST_OFFSET) // 86400)) for t in stamps})
        return [d for d in days if first <= d < last]

    def _rolling_by_day(self, payload):
        first, last = (date.fromisoformat(str(payload[k])[:10]) for k in ("fromDate", "toDate"))
        merged = {"ce": None, "pe": None}
        for day in self._session_days(first, last):
            part = self._rolling_day(payload, day).get("data") or {}
            for side in merged:
                rows = _rows_of_day(part.get(side), day)
                if rows is None:
                    continue
                if merged[side] is None:
                    merged[side] = rows
                    continue
                for field, values in rows.items():
                    if isinstance(values, list):
                        merged[side].setdefault(field, []).extend(values)
        return {"data": merged}

    def _rolling_day(self, payload, day):
        """One session day of a rolling-option series, cached under its own (day, day + 1) request. The
        current IST date is never cached: its candles are still arriving."""
        canonical = {**payload, "fromDate": day.isoformat(), "toDate": (day + timedelta(days=1)).isoformat()}
        key = hashlib.sha256(json.dumps(["rollingoption", canonical], sort_keys=True).encode()).hexdigest()
        path = self.cache_dir / (key + ".json.gz")
        if path.exists():
            with gzip.open(path, "rt", encoding="utf-8") as f:
                result = json.load(f)
            if result["request"] != canonical or result["endpoint"] != "rollingoption":
                raise RuntimeError("Historical cache metadata mismatch")
            self.cached += 1
            return result["response"]
        spans = (self._day_span,) if self._day_span is not None else self.DAY_SPANS
        for position, span in enumerate(spans):
            try:
                data = self._fetch("rollingoption", {**canonical, "toDate": (day + timedelta(days=span)).isoformat()})
            except DhanHTTPError as exc:
                if exc.status == 400 and position + 1 < len(spans):
                    continue        # Dhan refused this one-day form; try the other
                raise
            DhanHistoryClient._day_span = span
            if day < _today_ist():
                self._store(path, "rollingoption", canonical, data)
            return data
        raise RuntimeError("Dhan historical API retries exhausted")

    def _fetch(self, endpoint, payload):
        reauthorised = False
        for attempt in range(5):
            with self._rate_lock:
                time.sleep(max(0, 0.27 - (time.monotonic() - DhanHistoryClient._last_global_request)))
                DhanHistoryClient._last_global_request = time.monotonic()
            try:
                token = self._auth.token()
                response = self.session.post("https://api.dhan.co/v2" + self.ENDPOINTS[endpoint],
                                             headers={**self._headers, "access-token": token}, json=payload, timeout=60)
                if response.status_code in (401, 403) and not reauthorised and self._auth.rejected(token):
                    reauthorised = True         # renewable token: retry once with a freshly generated one
                    continue
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
                raise DhanHTTPError(response.status_code)
            try:
                data = response.json()
            except ValueError:
                raise RuntimeError("Dhan returned invalid JSON") from None
            if data.get("status") == "failure" or "errorCode" in data:
                raise RuntimeError("Dhan historical API returned an error payload")
            expected = "timestamp" if endpoint == "intraday" else "data"
            if expected not in data:
                raise RuntimeError("Dhan historical response has an unexpected schema")
            self.downloaded += 1
            return data
        raise RuntimeError("Dhan historical API retries exhausted")


class DhanHTTPError(RuntimeError):
    """Non-200 answer from a historical endpoint; the message carries the status only, never the body."""

    def __init__(self, status):
        super().__init__(f"Dhan historical API returned HTTP {status}")
        self.status = status


IST_OFFSET = 19800                                  # seconds; Dhan timestamps are epoch seconds
_EPOCH_ORDINAL = date(1970, 1, 1).toordinal()


def _today_ist():
    return date.fromordinal(_EPOCH_ORDINAL + int((time.time() + IST_OFFSET) // 86400))


def _rows_of_day(series, day):
    """The rows of one side's arrays whose IST date is ``day`` (Dhan's toDate is inclusive, so a one-day
    request can also return the next day). None when the side is absent or has no row that day."""
    if not series or not series.get("timestamp"):
        return None
    stamps = series["timestamp"]
    start = (day.toordinal() - _EPOCH_ORDINAL) * 86400 - IST_OFFSET
    keep = [i for i, t in enumerate(stamps) if start <= int(t) < start + 86400]
    if not keep:
        return None
    count = len(stamps)
    return {field: ([values[i] for i in keep] if isinstance(values, list) and len(values) == count else values)
            for field, values in series.items()}


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


OPTION_OFFSETS = ((1, range(-10, 11)), (2, range(-3, 4)))      # (expiry code, ATM offsets): nearest and next expiry
NEAR_EXPIRY_OFFSETS = OPTION_OFFSETS[:1]


def download(client, start, end, progress=print, option_offsets=OPTION_OFFSETS):
    for first, last in chunks(start, end):
        progress(f"Historical chunk {first} to {last} (end excluded)", flush=True)
        client.request("intraday", spot_payload(first, last))
        for code, offsets in option_offsets:
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
