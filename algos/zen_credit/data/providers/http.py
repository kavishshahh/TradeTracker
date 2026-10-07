"""HTTP client with timeouts, retries, exponential backoff and NSE cookie priming."""
from __future__ import annotations

import logging
import time

import requests

from data.providers.base import MarketDataError

log = logging.getLogger(__name__)

BROWSER_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/140.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


class HttpClient:
    def __init__(self, timeout: float = 10.0, retries: int = 3, backoff: float = 0.8,
                 nse_base_url: str = "https://www.nseindia.com", sleep=time.sleep):
        self.session = requests.Session()
        self.session.headers.update(BROWSER_HEADERS)
        self.timeout, self.retries, self.backoff = timeout, retries, backoff
        self.nse_base_url = nse_base_url.rstrip("/")
        self._sleep = sleep
        self._nse_primed = False

    def _prime_nse(self) -> None:
        # NSE API endpoints expect cookies set by a page visit; failure is non-fatal.
        try:
            self.session.get(f"{self.nse_base_url}/option-chain", timeout=self.timeout)
        except requests.RequestException:
            pass
        self._nse_primed = True

    def _request(self, url: str, nse: bool, params: dict | None = None) -> requests.Response:
        if nse and not self._nse_primed:
            self._prime_nse()
        headers = {"Referer": f"{self.nse_base_url}/option-chain"} if nse else {}
        last_exc: Exception | None = None
        for attempt in range(self.retries):
            try:
                resp = self.session.get(url, params=params, headers=headers, timeout=self.timeout)
                if resp.status_code == 200:
                    return resp
                last_exc = MarketDataError(f"HTTP {resp.status_code} for {url}")
                if nse and resp.status_code in (401, 403):
                    self._prime_nse()
            except requests.RequestException as exc:
                last_exc = exc
            self._sleep(self.backoff * (2 ** attempt))
        raise MarketDataError(f"request failed after {self.retries} attempts: {url}: {last_exc}")

    def get_json(self, url: str, nse: bool = False, params: dict | None = None):
        resp = self._request(url, nse, params)
        try:
            return resp.json()
        except ValueError as exc:
            raise MarketDataError(f"invalid JSON from {url}") from exc

    def get_text(self, url: str, nse: bool = False, params: dict | None = None) -> str:
        return self._request(url, nse, params).text
