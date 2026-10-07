"""Yahoo Finance chart API: free 1-minute ^NSEI bars (about the last 7 days)."""
from __future__ import annotations

from datetime import datetime

import pandas as pd

from data.providers.base import MarketDataError
from strategy.bars import complete_bars, normalize_bars


def parse_yahoo_chart(payload: dict) -> pd.DataFrame:
    try:
        res = payload["chart"]["result"][0]
        q = res["indicators"]["quote"][0]
        idx = pd.to_datetime(res["timestamp"], unit="s", utc=True)
    except (KeyError, IndexError, TypeError) as exc:
        raise MarketDataError("unexpected Yahoo chart payload") from exc
    df = pd.DataFrame({k: q.get(k) for k in ("open", "high", "low", "close")}, index=idx)
    return normalize_bars(df.astype(float))


class YahooSpotSource:
    def __init__(self, http, chart_url: str):
        self.http, self.chart_url = http, chart_url

    def get_spot_bars(self, as_of: datetime, range_: str = "5d") -> pd.DataFrame:
        payload = self.http.get_json(self.chart_url, params={"interval": "1m", "range": range_})
        bars = parse_yahoo_chart(payload)
        if bars.empty:
            raise MarketDataError("no Yahoo bars")
        if (bars[["open", "high", "low", "close"]] <= 0).any().any():
            raise MarketDataError("non-positive index price")
        return complete_bars(bars, as_of, 1)
