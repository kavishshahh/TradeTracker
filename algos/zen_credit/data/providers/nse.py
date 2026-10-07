"""NSE public endpoints: expiries/strikes, option chain, official lot sizes.

NSE publishes no free intraday history, so 1-minute spot bars come from a
separate spot source (Yahoo); option data comes from the live NSE chain and is
recorded by the engine every run to build alpha2's history.
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime

import pandas as pd

from data.providers.base import MarketDataError, MarketDataProvider, OptionChainSnapshot, OptionQuote
from utils.time import IST


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f


def _parse_date(raw) -> date | None:
    for fmt in ("%d-%m-%Y", "%d-%b-%Y"):
        try:
            return datetime.strptime(str(raw), fmt).date()
        except ValueError:
            continue
    return None


def parse_expiries(payload: dict) -> list[date]:
    raw = payload.get("expiryDates") or payload.get("records", {}).get("expiryDates") or []
    out = sorted(datetime.strptime(x, "%d-%b-%Y").date() for x in raw)
    if not out:
        raise MarketDataError("no expiries in NSE payload")
    return out


def parse_option_chain(payload: dict, expiry: date, underlying: str = "NIFTY") -> OptionChainSnapshot:
    rec = payload.get("records") or {}
    rows = rec.get("data") or []
    spot = _num(rec.get("underlyingValue"))
    ts_raw = rec.get("timestamp")
    if not rows or spot is None or not ts_raw:
        raise MarketDataError("incomplete NSE option chain payload")
    ts = datetime.strptime(ts_raw, "%d-%b-%Y %H:%M:%S").replace(tzinfo=IST)
    snap = OptionChainSnapshot(underlying=underlying, expiry=expiry, timestamp=ts, spot=spot)
    for row in rows:
        for side in ("CE", "PE"):
            leg = row.get(side)
            if not leg:
                continue
            leg_exp = _parse_date(leg.get("expiryDate") or row.get("expiryDates"))
            if leg_exp != expiry:
                continue
            strike = float(row.get("strikePrice", leg.get("strikePrice")))
            ltp = _num(leg.get("lastPrice"))
            snap.quotes[(strike, side)] = OptionQuote(
                strike=strike, option_type=side,
                ltp=ltp if ltp and ltp > 0 else None,
                bid=_num(leg.get("buyPrice1")) or None,
                ask=_num(leg.get("sellPrice1")) or None,
                cum_volume=_num(leg.get("totalTradedVolume")))
    if not snap.quotes:
        raise MarketDataError(f"no quotes for expiry {expiry}")
    return snap


def parse_lot_sizes(text: str, symbol: str = "NIFTY") -> dict[str, int]:
    """fo_mktlots.csv -> {"SEP-26": 65, ...} for the symbol."""
    reader = csv.reader(io.StringIO(text))
    header = [h.strip() for h in next(reader)]
    for row in reader:
        cells = [c.strip() for c in row]
        if len(cells) > 1 and cells[1] == symbol:
            return {header[i]: int(cells[i]) for i in range(2, len(cells))
                    if i < len(header) and cells[i].isdigit()}
    raise MarketDataError(f"{symbol} not found in lot-size file")


class NSEMarketDataProvider(MarketDataProvider):
    def __init__(self, http, spot_source, base_url: str, lot_size_url: str, underlying: str = "NIFTY"):
        self.http, self.spot_source = http, spot_source
        self.base_url = base_url.rstrip("/")
        self.lot_size_url = lot_size_url
        self.underlying = underlying
        self._lots: dict[str, int] | None = None

    def get_spot_bars(self, as_of: datetime) -> pd.DataFrame:
        return self.spot_source.get_spot_bars(as_of)

    def get_expiries(self) -> list[date]:
        payload = self.http.get_json(f"{self.base_url}/api/option-chain-contract-info",
                                     nse=True, params={"symbol": self.underlying})
        return parse_expiries(payload)

    def get_option_chain(self, expiry: date) -> OptionChainSnapshot:
        payload = self.http.get_json(
            f"{self.base_url}/api/option-chain-v3", nse=True,
            params={"type": "Indices", "symbol": self.underlying, "expiry": expiry.strftime("%d-%b-%Y")})
        return parse_option_chain(payload, expiry, self.underlying)

    def get_lot_size(self, expiry: date) -> int:
        if self._lots is None:
            self._lots = parse_lot_sizes(self.http.get_text(self.lot_size_url), self.underlying)
        key = expiry.strftime("%b-%y").upper()
        if key in self._lots:
            return self._lots[key]
        raise MarketDataError(f"no lot size for {self.underlying} {key}")
