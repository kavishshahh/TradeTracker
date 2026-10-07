"""Dated NSE calendar and contracts for the provider's July 2025–October 2026 history."""
from datetime import date, timedelta
from dataclasses import replace
from data.market_calendar import HolidaySetCalendar
from backtest.nifty_2026 import HOLIDAYS as HOLIDAYS_2026, SOURCES as SOURCES_2026

SOURCES = SOURCES_2026 + [
    "https://nsearchives.nseindia.com/content/circulars/FAOP65588.pdf",
    "https://nsearchives.nseindia.com/content/circulars/FAOP72352.pdf",
]
HOLIDAYS_2025 = {date.fromisoformat(s) for s in (
    "2025-02-26", "2025-03-14", "2025-03-31", "2025-04-10", "2025-04-14", "2025-04-18",
    "2025-05-01", "2025-08-15", "2025-08-27", "2025-10-02", "2025-10-21", "2025-10-22",
    "2025-11-05", "2025-12-25")}


class ProviderCalendar(HolidaySetCalendar):
    def __init__(self, special_sessions=True):
        super().__init__(HOLIDAYS_2025 | HOLIDAYS_2026)
        self.special_sessions = special_sessions

    def is_trading_day(self, d):
        if not date(2025, 1, 1) <= d <= date(2026, 12, 31):
            raise ValueError("Provider historical calendar supports 2025 and 2026 only")
        if self.special_sessions and d == date(2026, 2, 1):
            return True
        return super().is_trading_day(d)


def expiries_for(d):
    calendar = ProviderCalendar()
    # Generate scheduled expiries on both sides of the Aug/Sep 2025 transition.
    candidates = []
    for i in range(22):
        scheduled = d + timedelta(days=i)
        weekday = 3 if scheduled < date(2025, 9, 1) else 1
        if scheduled.weekday() != weekday:
            continue
        expiry = scheduled
        while not calendar.is_trading_day(expiry):
            expiry -= timedelta(days=1)
        if expiry >= d and expiry not in candidates:
            candidates.append(expiry)
        if len(candidates) == 2:
            return candidates
    raise ValueError("Could not resolve two listed expiries")


def lot_size(d, expiry):
    if not date(2025, 2, 1) <= d <= date(2026, 12, 31):
        raise ValueError("Provider lot-size rules support February 2025 onward")
    return 75 if expiry <= date(2025, 12, 30) else 65


def history_config(cfg):
    """Observed schedule regime; entry alpha formulas remain unverified."""
    return replace(cfg, historical_time_exit_start=date(2025,7,9),
                   historical_time_exit_end=date(2026,6,30))
