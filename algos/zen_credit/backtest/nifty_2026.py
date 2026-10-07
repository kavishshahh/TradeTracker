"""NSE 2026 regular-session, Tuesday expiry and 65-unit NIFTY rules."""
from datetime import date, timedelta

from data.market_calendar import HolidaySetCalendar

SOURCES = [
    "https://nsearchives.nseindia.com/content/circulars/FAOP71777.pdf",
    "https://nsearchives.nseindia.com/content/circulars/FAOP72262.pdf",
    "https://nsearchives.nseindia.com/content/circulars/FAOP68747.pdf",
    "https://nsearchives.nseindia.com/content/circulars/FAOP70616.pdf",
]
HOLIDAYS = {date.fromisoformat(s) for s in (
    "2026-01-15", "2026-01-26", "2026-03-03", "2026-03-26", "2026-03-31", "2026-04-03",
    "2026-04-14", "2026-05-01", "2026-05-28", "2026-06-26", "2026-09-14",
    "2026-10-02", "2026-10-20", "2026-11-10", "2026-11-24", "2026-12-25")}


class Nifty2026Calendar(HolidaySetCalendar):
    def __init__(self):
        super().__init__(HOLIDAYS)

    def is_trading_day(self, d):
        if d.year != 2026:
            raise ValueError("2026 historical calendar cannot be used outside 2026")
        return super().is_trading_day(d)


def expiries_for(d):
    calendar = Nifty2026Calendar()
    tuesday = d + timedelta(days=(1 - d.weekday()) % 7)
    result = []
    for _ in range(4):
        expiry = tuesday
        while not calendar.is_trading_day(expiry):
            expiry -= timedelta(days=1)
        if expiry >= d:
            result.append(expiry)
        if len(result) == 2:
            return result
        tuesday += timedelta(days=7)
    raise ValueError("Cannot resolve two weekly expiries")


def lot_size(d, expiry):
    if d.year != 2026 or expiry.year != 2026:
        raise ValueError("65-unit lot rule supports 2026 contracts only")
    return 65
