"""Dated NSE calendar and contracts from December 2021 through 2026.

August 2023 onwards serves the published three-year replays. December 2021 - July 2023 was added on
22 Nov 2026 for five-year research runs (Dhan serves five years of minute data); the engine replay
(backtest.dhan_replay) still starts in October 2023."""
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
# Dec 2021 - Jul 2023 weekday closures (Dec 2021 had none). Checked the same way, against the days with
# no Dhan NIFTY index candles, when the five-year dataset was downloaded. Thursday closures move that
# week's expiry to Wednesday (14 Apr 2022, 26 Jan, 30 Mar and 29 Jun 2023). NIFTY lots were 50 throughout.
HOLIDAYS_2022 = {date.fromisoformat(s) for s in (
    "2022-01-26", "2022-03-01", "2022-03-18", "2022-04-14", "2022-04-15", "2022-05-03", "2022-08-09",
    "2022-08-15", "2022-08-31", "2022-10-05", "2022-10-24", "2022-10-26", "2022-11-08")}
HOLIDAYS_2023 = {date.fromisoformat(s) for s in (
    "2023-01-26", "2023-03-07", "2023-03-30", "2023-04-04", "2023-04-07", "2023-04-14", "2023-05-01", "2023-06-29",
    "2023-08-15", "2023-09-19", "2023-10-02", "2023-10-24", "2023-11-14", "2023-11-27")}
HOLIDAYS_2025 = {date.fromisoformat(s) for s in (
    "2025-02-26", "2025-03-14", "2025-03-31", "2025-04-10", "2025-04-14", "2025-04-18",
    "2025-05-01", "2025-08-15", "2025-08-27", "2025-10-02", "2025-10-21", "2025-10-22",
    "2025-11-05", "2025-12-25")}


FIRST_DAY = date(2021, 12, 1)


class ProviderCalendar(HolidaySetCalendar):
    def __init__(self, special_sessions=True):
        super().__init__(HOLIDAYS_2022 | HOLIDAYS_2023 | nifty_2024.HOLIDAYS | HOLIDAYS_2025 | HOLIDAYS_2026)
        self.special_sessions = special_sessions

    def is_trading_day(self, d):
        if not FIRST_DAY <= d <= date(2026, 12, 31):
            raise ValueError("Provider historical calendar supports December 2021 through 2026 only")
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
    if not FIRST_DAY <= d <= date(2026, 12, 31):
        raise ValueError("Provider lot-size rules support December 2021 through 2026")
    if d < date(2025, 2, 1):
        return nifty_2024.lot_size(d, expiry)   # 50, then 25 from 26 Apr 2024, 75 for 2025 weeklies
    return 75 if expiry <= date(2025, 12, 30) else 65


def history_config(cfg):
    """Observed schedule regime; entry alpha formulas remain unverified."""
    return replace(cfg, historical_time_exit_start=date(2025,7,9),
                   historical_time_exit_end=date(2026,6,30))
