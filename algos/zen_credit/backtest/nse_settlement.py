"""Dated final index closes from NSE's public daily CSV archive."""
import io
import math
from datetime import datetime

import pandas as pd
import requests

from data.providers.base import ExpirySettlement


def parse_close(text, expiry, source):
    frame = pd.read_csv(io.StringIO(text))
    frame.columns = frame.columns.str.strip()
    rows = frame.loc[frame["Index Name"].str.strip().str.upper().eq("NIFTY 50")]
    if len(rows) != 1:
        raise ValueError("NSE archive does not contain one NIFTY 50 row")
    row = rows.iloc[0]
    if datetime.strptime(str(row["Index Date"]).strip(), "%d-%m-%Y").date() != expiry:
        raise ValueError("NSE closing archive date mismatch")
    close = float(row["Closing Index Value"])
    if not math.isfinite(close) or close <= 0:
        raise ValueError("Invalid NSE index close")
    return ExpirySettlement(expiry, close, source)


class NSESettlementClient:
    def __init__(self, cache_dir, offline=False):
        self.cache_dir, self.offline = cache_dir, offline
        self.results = {}

    def get(self, expiry):
        if expiry in self.results:
            return self.results[expiry]
        source = f"https://nsearchives.nseindia.com/content/indices/ind_close_all_{expiry:%d%m%Y}.csv"
        path = self.cache_dir / f"nse_{expiry}.csv"
        result = None
        if path.exists():
            result = parse_close(path.read_text(encoding="utf-8"), expiry, source)
        elif not self.offline:
            print(f"Fetching official NSE settlement for {expiry}", flush=True)
            for attempt in range(2):
                try:
                    response = requests.get(source, headers={"User-Agent": "Mozilla/5.0", "Accept": "*/*",
                                                            "Referer": "https://www.nseindia.com/"}, timeout=15)
                    if response.status_code == 200:
                        result = parse_close(response.text, expiry, source)
                        path.write_text(response.text, encoding="utf-8")
                        break
                    if response.status_code not in (403,429,500,502,503,504):break
                except requests.RequestException:
                    pass
                except (ValueError,KeyError):
                    # Wrong dates or malformed archives are not usable prices.
                    break
                if attempt==0:print(f"Retrying transient NSE settlement failure for {expiry}",flush=True)
        if result is None:
            print(f"Official settlement unavailable for {expiry}; position remains unresolved", flush=True)
        self.results[expiry] = result
        return result
