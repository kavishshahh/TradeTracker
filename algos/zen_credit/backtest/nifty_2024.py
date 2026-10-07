"""Sourced NSE rules for the requested 2024 replay and its warm-up/tail.

No present-day expiry or lot-size metadata is used for historical contracts.
"""
from datetime import date, timedelta

from data.market_calendar import HolidaySetCalendar

SOURCES = [
    "https://archives.nseindia.com/content/circulars/FAOP59723.pdf",
    "https://nsearchives.nseindia.com/content/circulars/FAOP60337.pdf",
    "https://nsearchives.nseindia.com/content/circulars/FAOP61517.pdf",
    "https://nsearchives.nseindia.com/content/circulars/FAOP64959.pdf",
    "https://nsearchives.nseindia.com/content/circulars/FAOP61415.pdf",
    "https://nsearchives.nseindia.com/content/circulars/FAOP64625.pdf",
    "https://nsearchives.nseindia.com/content/circulars/FAOP64672.pdf",
]
HOLIDAYS = {date.fromisoformat(s) for s in (
    "2023-12-25", "2024-01-22", "2024-01-26", "2024-03-08", "2024-03-25", "2024-03-29",
    "2024-04-11", "2024-04-17", "2024-05-01", "2024-05-20", "2024-06-17", "2024-07-17",
    "2024-08-15", "2024-10-02", "2024-11-01", "2024-11-15", "2024-11-20", "2024-12-25")}


class Nifty2024Calendar(HolidaySetCalendar):
    def __init__(self):
        super().__init__(HOLIDAYS)

    def is_trading_day(self, d):
        if not date(2023, 12, 1) <= d <= date(2025, 2, 6):
            raise ValueError("2024 historical calendar cannot be used outside its supported range")
        return super().is_trading_day(d)


def expiries_for(d):
    calendar = Nifty2024Calendar()
    thursday = d + timedelta(days=(3 - d.weekday()) % 7)
    result = []
    for _ in range(4):
        expiry = thursday
        while not calendar.is_trading_day(expiry):
            expiry -= timedelta(days=1)
        if expiry >= d:
            result.append(expiry)
        thursday += timedelta(days=7)
        if len(result) == 2:
            break
    return result


def lot_size(d, expiry):
    if d < date(2024, 4, 26):
        return 50
    # January 2025 monthly retained 25; weekly contracts from Jan 2 use 75.
    if expiry >= date(2025, 1, 2) and expiry != date(2025, 1, 30):
        return 75
    return 25
