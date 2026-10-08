"""NSE trading calendar and the session gate.

Structure mirrors the other Dhan algo projects: ``MarketCalendar.check(now)``
returns a :class:`SessionVerdict` and the runner exits on anything but OPEN
*before any market-data request*. Weekends are decided from the clock alone
(no network I/O at all). The production runner uses BundledNSECalendar with
reviewed official NSE dates and no holiday HTTP requests. NSEHolidayCalendar
remains available for legacy callers that explicitly request API-backed data.

Zen Credit semantics are unchanged: the market is open for
09:15 <= time < 15:30 on NSE trading days ("FO" segment, falling back to "CM");
with no usable holiday data the engine does not trade (CalendarUnavailable).
"""
from __future__ import annotations

import logging
import time as _time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from enum import Enum
from typing import Callable

from utils.time import to_ist
from data.holiday_snapshot import HOLIDAYS_BY_YEAR

log = logging.getLogger(__name__)

class CalendarUnavailable(RuntimeError):
    """Raised when no trustworthy holiday data is available (live: no trading)."""


class TradingCalendar(ABC):
    session_open = time(9, 15)
    session_close = time(15, 30)

    @abstractmethod
    def is_trading_day(self, d: date) -> bool: ...

    def next_trading_day(self, d: date, max_days: int = 15) -> date:
        cur = d
        for _ in range(max_days):
            cur = cur + timedelta(days=1)
            if self.is_trading_day(cur):
                return cur
        raise CalendarUnavailable(f"no trading day within {max_days} days after {d}")

    def previous_trading_day(self, d: date, max_days: int = 15) -> date:
        cur = d
        for _ in range(max_days):
            cur = cur - timedelta(days=1)
            if self.is_trading_day(cur):
                return cur
        raise CalendarUnavailable(f"no trading day within {max_days} days before {d}")

    def is_market_open(self, ts: datetime) -> bool:
        ist = to_ist(ts)
        return self.is_trading_day(ist.date()) and self.session_open <= ist.time() < self.session_close


class HolidaySetCalendar(TradingCalendar):
    """Weekends + an explicit set of exchange holidays (data supplied at runtime)."""

    def __init__(self, holidays: set[date]):
        self.holidays = set(holidays)

    def is_trading_day(self, d: date) -> bool:
        return d.weekday() < 5 and d not in self.holidays


class BundledNSECalendar(TradingCalendar):
    """Reviewed NSE holiday snapshots; no HTTP requests or external cache.

    Each calendar year must be supplied explicitly in holiday_snapshot.py.
    Unknown years fail closed rather than assuming every weekday is open.
    """

    def is_trading_day(self, d: date) -> bool:
        holidays = HOLIDAYS_BY_YEAR.get(d.year)
        if holidays is None:
            raise CalendarUnavailable(f"no bundled NSE holiday data for {d.year}")
        return d.weekday() < 5 and d not in holidays

    @property
    def holidays_known(self) -> bool:
        return to_ist(datetime.now(timezone.utc)).year in HOLIDAYS_BY_YEAR

    def next_holidays(self, limit: int = 3) -> list[date]:
        today = to_ist(datetime.now(timezone.utc)).date()
        return sorted(d for d in HOLIDAYS_BY_YEAR.get(today.year, ()) if d >= today)[:limit]


class ObservedSessionsCalendar(TradingCalendar):
    """Historical calendar built from dates on which the index actually traded
    (e.g. Yahoo daily bars). Used by the backtest for past years, for which the
    NSE API no longer publishes holidays."""

    def __init__(self, trading_days: set[date]):
        if not trading_days:
            raise CalendarUnavailable("empty trading-day set")
        self.trading_days = set(trading_days)
        self.first, self.last = min(trading_days), max(trading_days)

    def is_trading_day(self, d: date) -> bool:
        if d < self.first:
            raise CalendarUnavailable(f"{d} before observed calendar range")
        if d > self.last:
            # beyond observed data: fall back to weekday rule (documented)
            return d.weekday() < 5
        return d in self.trading_days


def parse_nse_holidays(payload: dict, segment: str = "FO") -> set[date]:
    rows = payload.get(segment) or payload.get("CM") or []
    out: set[date] = set()
    for row in rows:
        raw = row.get("tradingDate")
        if raw:
            out.add(datetime.strptime(raw, "%d-%b-%Y").date())
    if not out:
        raise ValueError("holiday payload contains no dates")
    return out


class NSEHolidayCalendar(TradingCalendar):
    """Holidays from NSE_HOLIDAY_URL, cached for ``cache_hours``.

    The cache lives wherever ``cache_get``/``cache_set`` put it: the Postgres
    state store in production (survives restarts), a dict in tests. If a refresh
    fails, a cached copy of the SAME calendar year is still used and a warning is
    logged. A reviewed, year-specific NSE snapshot is the final fallback. With
    no usable data CalendarUnavailable is raised and nothing trades.
    """

    def __init__(self, http, url: str, cache_get: Callable[[], dict | None] | None = None,
                 cache_set: Callable[[dict], None] | None = None, cache_hours: int = 24, clock=None):
        self.http = http
        self.url = url
        self._cache_get, self._cache_set = cache_get, cache_set
        self.cache_seconds = cache_hours * 3600
        self.clock = clock or _time.time
        self._holidays: set[date] | None = None
        self._loaded_at = 0.0

    def _read_cache(self) -> tuple[dict, float] | None:
        if self._cache_get is None:
            return None
        try:
            blob = self._cache_get()
            if not blob:
                return None
            return blob["payload"], float(blob["fetched_at"])
        except (ValueError, KeyError, TypeError):
            return None

    def _write_cache(self, payload: dict) -> None:
        if self._cache_set is None:
            return
        try:
            self._cache_set({"fetched_at": self.clock(), "payload": payload})
        except Exception as exc:  # cache write failure is not fatal
            log.warning("holiday cache write failed: %s", exc)

    def holidays(self) -> set[date]:
        now = self.clock()
        year = to_ist(datetime.fromtimestamp(now, timezone.utc)).year
        def valid_for_year(parsed):
            return any(d.year == year for d in parsed)

        if self._holidays is not None and valid_for_year(self._holidays) and now - self._loaded_at < self.cache_seconds:
            return self._holidays
        cached = self._read_cache()
        cached_holidays = None
        if cached:
            try:
                parsed = parse_nse_holidays(cached[0])
                if valid_for_year(parsed):
                    cached_holidays = parsed
            except (ValueError, TypeError, AttributeError):
                pass
        if cached_holidays is not None and now - cached[1] < self.cache_seconds:
            self._holidays, self._loaded_at = cached_holidays, cached[1]
            return self._holidays
        try:
            payload = self.http.get_json(self.url, nse=True)
            parsed = parse_nse_holidays(payload)
            if not valid_for_year(parsed):
                raise ValueError(f"no NSE holiday data for {year}")
            self._write_cache(payload)
            self._holidays, self._loaded_at = parsed, now
            return parsed
        except Exception as exc:  # network / format failure
            fallback = cached_holidays
            source = "stale cache"
            if fallback is None and self._holidays is not None and valid_for_year(self._holidays):
                fallback = self._holidays
            if fallback is None and year in HOLIDAYS_BY_YEAR:
                fallback = set(HOLIDAYS_BY_YEAR[year])
                source = f"bundled NSE {year} snapshot"
            if fallback is not None:
                log.warning("holiday refresh failed; using %s: %s", source, exc)
                # Retry the API in at most 15 minutes. Do not persist the
                # snapshot as though it were a freshly fetched API response.
                self._holidays = fallback
                self._loaded_at = now - self.cache_seconds + min(900, self.cache_seconds)
                return fallback
            raise CalendarUnavailable(f"NSE holiday data unavailable: {exc}") from exc

    @property
    def holidays_known(self) -> bool:
        return self._holidays is not None

    def next_holidays(self, limit: int = 3) -> list[date]:
        if not self._holidays:
            return []
        today = date.fromtimestamp(self.clock())
        return sorted(d for d in self._holidays if d >= today)[:limit]

    def is_trading_day(self, d: date) -> bool:
        hol = self.holidays()
        if not any(h.year == d.year for h in hol):
            raise CalendarUnavailable(f"no NSE holiday data for {d.year}")
        return HolidaySetCalendar(hol).is_trading_day(d)


# --------------------------------------------------------------------------- #
# Session gate (the runner's first step, before any market-data fetch)
class SessionState(str, Enum):
    OPEN = "OPEN"
    WEEKEND = "WEEKEND"
    HOLIDAY = "HOLIDAY"
    BEFORE_OPEN = "BEFORE_OPEN"
    AFTER_CLOSE = "AFTER_CLOSE"


@dataclass
class SessionVerdict:
    state: SessionState
    reason: str

    @property
    def is_open(self) -> bool:
        return self.state is SessionState.OPEN


class MarketCalendar:
    """Wraps any TradingCalendar with the ordered, cheapest-first session check.

    Equivalent to ``TradingCalendar.is_market_open`` (open iff trading day and
    09:15 <= t < 15:30) but says WHY it is closed. A weekend is decided without
    touching the holiday source. CalendarUnavailable propagates to the caller.
    """

    def __init__(self, calendar: TradingCalendar):
        self.calendar = calendar

    def check(self, now: datetime) -> SessionVerdict:
        ist = to_ist(now)
        if ist.weekday() >= 5:
            return SessionVerdict(SessionState.WEEKEND, f"{ist.strftime('%A')}, market closed")
        if not self.calendar.is_trading_day(ist.date()):
            return SessionVerdict(SessionState.HOLIDAY, f"NSE trading holiday ({ist.date().isoformat()})")
        t = ist.time()
        if t < self.calendar.session_open:
            return SessionVerdict(SessionState.BEFORE_OPEN, f"{t:%H:%M} IST is before the 09:15 open")
        if t >= self.calendar.session_close:
            return SessionVerdict(SessionState.AFTER_CLOSE, f"{t:%H:%M} IST is at/after the 15:30 close")
        return SessionVerdict(SessionState.OPEN, f"{t:%H:%M} IST, market open")
