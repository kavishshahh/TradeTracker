"""Market-data abstraction. The strategy never performs HTTP itself."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd


class MarketDataError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExpirySettlement:
    """Official underlying settlement price for a specific expiry, with provenance."""
    expiry: date
    spot: float
    source: str


@dataclass(frozen=True)
class OptionQuote:
    strike: float
    option_type: str          # "CE" / "PE"
    ltp: float | None
    bid: float | None
    ask: float | None
    cum_volume: float | None  # exchange cumulative traded volume (contracts) for the day


@dataclass
class OptionChainSnapshot:
    underlying: str
    expiry: date
    timestamp: datetime       # exchange timestamp (tz-aware)
    spot: float
    quotes: dict[tuple[float, str], OptionQuote] = field(default_factory=dict)

    @property
    def strikes(self) -> list[float]:
        return sorted({k[0] for k in self.quotes})

    def quote(self, strike: float, option_type: str) -> OptionQuote | None:
        return self.quotes.get((float(strike), option_type))

    def to_rows(self, minute: datetime, strikes: list[float] | None = None) -> list[dict]:
        keep = set(strikes) if strikes is not None else set(self.strikes)
        rows = []
        for k in sorted(keep):
            ce, pe = self.quote(k, "CE"), self.quote(k, "PE")
            if ce is None or pe is None:
                continue
            rows.append({"minute": minute, "expiry": self.expiry, "strike": float(k), "spot": self.spot,
                         "ce_ltp": ce.ltp, "pe_ltp": pe.ltp, "ce_bid": ce.bid, "ce_ask": ce.ask,
                         "pe_bid": pe.bid, "pe_ask": pe.ask,
                         "ce_cum_volume": ce.cum_volume, "pe_cum_volume": pe.cum_volume})
        return rows


class MarketDataProvider(ABC):
    def get_expiry_settlement(self, expiry: date) -> ExpirySettlement | None:
        """Return an official dated settlement, or None if this provider cannot supply it."""
        return None

    @abstractmethod
    def get_spot_bars(self, as_of: datetime) -> pd.DataFrame:
        """Recent 1-minute NIFTY bars (tz-aware index = bar start)."""

    @abstractmethod
    def get_expiries(self) -> list[date]: ...

    @abstractmethod
    def get_option_chain(self, expiry: date) -> OptionChainSnapshot: ...

    @abstractmethod
    def get_lot_size(self, expiry: date) -> int: ...
