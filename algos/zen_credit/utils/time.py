"""Timezone and rounding helpers. All market times are Asia/Kolkata via zoneinfo."""
from __future__ import annotations

from datetime import date, datetime, time
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def now_ist() -> datetime:
    return datetime.now(tz=IST)


def to_ist(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        raise ValueError("naive datetime; timezone required")
    return dt.astimezone(IST)


def combine_ist(d: date, t: time) -> datetime:
    return datetime.combine(d, t, tzinfo=IST)


def minute_bucket(dt: datetime) -> datetime:
    return to_ist(dt).replace(second=0, microsecond=0)


# --- rounding rules (single place) -------------------------------------------
# prices / spread values: 2 dp; rupee amounts: 2 dp; percentages: 2 dp;
# all half-up to avoid Python's banker's rounding.

def round_half_up(value: float, ndigits: int = 2) -> float:
    q = Decimal(1).scaleb(-ndigits)
    return float(Decimal(str(value)).quantize(q, rounding=ROUND_HALF_UP))


def round_price(value: float) -> float:
    return round_half_up(value, 2)


def round_money(value: float) -> float:
    return round_half_up(value, 2)


def round_pct(value: float) -> float:
    return round_half_up(value, 2)


def fmt_num(value: float) -> str:
    return f"{round_half_up(value, 2):.2f}"


def fmt_signed(value: float) -> str:
    v = round_half_up(value, 2)
    return f"{'+' if v >= 0 else '-'}{abs(v):.2f}"


def fmt_expiry(d: date) -> str:
    return d.strftime("%d-%b-%Y")
