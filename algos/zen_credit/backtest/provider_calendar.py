"""Dated NSE calendar and contracts from August 2023 (three-year replays plus warm-up) through 2026."""
from datetime import date, timedelta
from dataclasses import replace
from data.market_calendar import HolidaySetCalendar
from backtest.nifty_2026 import HOLIDAYS as HOLIDAYS_2026, SOURCES as SOURCES_2026
from backtest import nifty_2024

SOURCES = SOURCES_2026 + nifty_2024.SOURCES + [
    "https://nsearchives.nseindia.com/content/circulars/FAOP65588.pdf",
    "https://nsearchives.nseindia.com/content/circulars/FAOP72352.pdf",
]
# Aug-Nov 2023 weekday closures, checked against the days with no Dhan NIFTY index candles
# (Dec 2023 and 2024 come from nifty_2024). 28 Sep 2023 (Id-E-Milad) traded; only settlement moved.
HOLIDAYS_2023 = {date.fromisoformat(s) for s in (
    "2023-08-15", "2023-09-19", "2023-10-02", "2023-10-24", "2023-11-14", "2023-11-27")}
HOLIDAYS_2025 = {date.fromisoformat(s) for s in (
    "2025-02-26", "2025-03-14", "2025-03-31", "2025-04-10", "2025-04-14", "2025-04-18",
    "2025-05-01", "2025-08-15", "2025-08-27", "2025-10-02", "2025-10-21", "2025-10-22",
    "2025-11-05", "2025-12-25")}


class ProviderCalendar(HolidaySetCalendar):
    def __init__(self, special_sessions=True):
        super().__init__(HOLIDAYS_2023 | nifty_2024.HOLIDAYS | HOLIDAYS_2025 | HOLIDAYS_2026)
        self.special_sessions = special_sessions

    def is_trading_day(self, d):
        if not date(2023, 8, 1) <= d <= date(2026, 12, 31):
            raise ValueError("Provider historical calendar supports August 2023 through 2026 only")
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
    if not date(2023, 8, 1) <= d <= date(2026, 12, 31):
        raise ValueError("Provider lot-size rules support August 2023 through 2026")
    if d < date(2025, 2, 1):
        return nifty_2024.lot_size(d, expiry)   # 50, then 25 from 26 Apr 2024, 75 for 2025 weeklies
    return 75 if expiry <= date(2025, 12, 30) else 65


def history_config(cfg):
    """Observed schedule regime; entry alpha formulas remain unverified."""
    return replace(cfg, historical_time_exit_start=date(2025,7,9),
                   historical_time_exit_end=date(2026,6,30))
