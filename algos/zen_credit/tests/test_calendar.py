import json
from datetime import date

import pytest

from data.market_calendar import CalendarUnavailable, HolidaySetCalendar, ObservedSessionsCalendar
from data.market_calendar import MarketCalendar, NSEHolidayCalendar, SessionState, parse_nse_holidays
from tests.conftest import ist, load_fixture


class FakeHttp:
    def __init__(self, payload=None, fail=False):
        self.payload, self.fail, self.calls = payload, fail, 0

    def get_json(self, url, nse=False, params=None):
        self.calls += 1
        if self.fail:
            raise RuntimeError("NSE down")
        return self.payload


def test_parse_official_payload():
    hol = parse_nse_holidays(load_fixture("nse_holidays_sample.json"))
    assert date(2026, 1, 26) in hol and date(2026, 10, 2) in hol
    with pytest.raises(ValueError):
        parse_nse_holidays({"FO": []})


class DictCache:
    """Stands in for the Postgres-backed holiday cache (zc_state)."""
    def __init__(self):
        self.blob = None

    def get(self):
        return self.blob

    def set(self, blob):
        self.blob = json.loads(json.dumps(blob))


def _cal(http, cache, clock):
    return NSEHolidayCalendar(http, "u", cache.get, cache.set, cache_hours=24, clock=lambda: clock[0])


def test_nse_calendar_fetch_cache_and_refresh():
    clock = [1_780_000_000.0]
    cache = DictCache()
    http = FakeHttp(load_fixture("nse_holidays_sample.json"))
    cal = _cal(http, cache, clock)
    assert not cal.is_trading_day(date(2026, 10, 2))       # Gandhi Jayanti (Friday)
    assert cal.is_trading_day(date(2026, 10, 1))
    assert not cal.is_trading_day(date(2026, 10, 3))       # Saturday
    assert http.calls == 1
    cal2 = _cal(http, cache, clock)
    cal2.is_trading_day(date(2026, 10, 1))
    assert http.calls == 1                                  # served from the (DB) cache
    clock[0] += 25 * 3600
    cal2.is_trading_day(date(2026, 10, 1))
    assert http.calls == 2                                  # stale -> refreshed


def test_nse_calendar_failure_uses_same_year_stale_cache():
    clock = [1_780_000_000.0]
    cache = DictCache()
    _cal(FakeHttp(load_fixture("nse_holidays_sample.json")), cache, clock).holidays()
    clock[0] += 48 * 3600
    cal = _cal(FakeHttp(fail=True), cache, clock)
    assert not cal.is_trading_day(date(2026, 10, 2))


def test_nse_calendar_failure_without_cache_raises():
    cal = _cal(FakeHttp(fail=True), DictCache(), [1_780_000_000.0])
    with pytest.raises(CalendarUnavailable):
        cal.is_trading_day(date(2026, 10, 1))


def test_no_data_for_year_raises():
    cal = _cal(FakeHttp(load_fixture("nse_holidays_sample.json")), DictCache(), [1_780_000_000.0])
    with pytest.raises(CalendarUnavailable):
        cal.is_trading_day(date(2031, 1, 6))


def test_market_session_handling():
    cal = HolidaySetCalendar({date(2026, 10, 2)})
    assert cal.is_market_open(ist(2026, 9, 24, 9, 15))
    assert cal.is_market_open(ist(2026, 9, 24, 15, 29))
    assert not cal.is_market_open(ist(2026, 9, 24, 15, 30))
    assert not cal.is_market_open(ist(2026, 9, 24, 9, 14))
    assert not cal.is_market_open(ist(2026, 10, 2, 11, 0))    # holiday
    assert not cal.is_market_open(ist(2026, 9, 26, 11, 0))    # Saturday
    assert cal.next_trading_day(date(2026, 10, 1)) == date(2026, 10, 5)
    assert cal.previous_trading_day(date(2026, 10, 5)) == date(2026, 10, 1)


def test_observed_sessions_calendar():
    cal = ObservedSessionsCalendar({date(2026, 9, 24), date(2026, 9, 25)})
    assert cal.is_trading_day(date(2026, 9, 24)) and not cal.is_trading_day(date(2026, 9, 23 + 3))
    with pytest.raises(CalendarUnavailable):
        cal.is_trading_day(date(2020, 1, 1))


def test_session_gate_states_match_is_market_open():
    cal = HolidaySetCalendar({date(2026, 10, 2)})
    gate = MarketCalendar(cal)
    cases = {ist(2026, 9, 26, 11, 0): SessionState.WEEKEND, ist(2026, 10, 2, 11, 0): SessionState.HOLIDAY,
             ist(2026, 9, 24, 9, 14): SessionState.BEFORE_OPEN, ist(2026, 9, 24, 15, 30): SessionState.AFTER_CLOSE,
             ist(2026, 9, 24, 9, 15): SessionState.OPEN, ist(2026, 9, 24, 15, 29): SessionState.OPEN}
    for ts, state in cases.items():
        v = gate.check(ts)
        assert v.state is state
        assert v.is_open == cal.is_market_open(ts)
