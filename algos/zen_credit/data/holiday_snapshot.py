"""Reviewed NSE F&O holidays for offline calendar recovery.

Verified 2026-10-08 against NSE's published trading calendar and circulars:
https://nsearchives.nseindia.com/content/circulars/FAOP71777.pdf
https://nsearchives.nseindia.com/content/circulars/FAOP72262.pdf

Update for exchange amendments and add each new year explicitly. These are
trading holidays, not settlement holidays. Special weekend sessions remain
outside the runner's regular weekday session gate.
"""
from datetime import date


HOLIDAYS_BY_YEAR = {
    2026: frozenset(date.fromisoformat(value) for value in (
        "2026-01-15", "2026-01-26", "2026-02-15", "2026-03-03",
        "2026-03-21", "2026-03-26", "2026-03-31", "2026-04-03",
        "2026-04-14", "2026-05-01", "2026-05-28", "2026-06-26",
        "2026-08-15", "2026-09-14", "2026-10-02", "2026-10-20",
        "2026-11-08", "2026-11-10", "2026-11-24", "2026-12-25",
    )),
}
