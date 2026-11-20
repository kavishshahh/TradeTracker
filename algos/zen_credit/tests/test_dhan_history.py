"""DhanHistoryClient: one rolling-option request per session day (Dhan's November 2026 limit), merged back
into the multi-day response shape. A fake session answers every request; no credentials, no network."""
from datetime import date, datetime, time, timedelta

import pytest

from backtest import dhan_history
from backtest.dhan_history import DhanHistoryClient, DhanHTTPError, option_payload
from utils.time import IST

SESSIONS = [date(2026, 11, 2), date(2026, 11, 3), date(2026, 11, 5), date(2026, 11, 6)]   # 4 Nov: no candles


def _stamp(day, hour=9, minute=15):
    return int(datetime.combine(day, time(hour, minute), IST).timestamp())


class Response:
    def __init__(self, status, body=None):
        self.status_code, self._body = status, body

    def json(self):
        return self._body


class FakeDhan:
    """Index candles for SESSIONS; rolling options only for a one-day range, with Dhan's inclusive toDate
    (a (day, day + 1) request also returns the next day's rows)."""

    def __init__(self, accept_spans=(0, 1)):
        self.accept_spans, self.rolling, self.intraday = accept_spans, [], 0

    def post(self, url, headers, json, timeout):
        assert headers["access-token"] == "test-token"
        if url.endswith("/charts/intraday"):
            self.intraday += 1
            return Response(200, {"timestamp": [_stamp(d) for d in SESSIONS], "close": [24000.0] * len(SESSIONS)})
        first, last = date.fromisoformat(json["fromDate"]), date.fromisoformat(json["toDate"])
        self.rolling.append((first, last))
        if (last - first).days not in self.accept_spans:
            return Response(400, {"errorCode": "DH-905"})
        days = [d for d in SESSIONS if first <= d <= last]
        stamps = [_stamp(d, 9, 15 + k) for d in days for k in range(2)]
        side = {"iv": [], "strike": [24000.0] * len(stamps), "close": [float(d.day) for d in days for _ in range(2)],
                "timestamp": stamps}
        return Response(200, {"data": {"ce": side, "pe": None}})


@pytest.fixture
def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DHAN_CLIENT_ID", "test-client")
    monkeypatch.setenv("DHAN_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("DHAN_PIN", "")                    # a fixed token: never the TOTP login
    monkeypatch.setenv("DHAN_TOTP_SECRET", "")
    monkeypatch.setattr(DhanHistoryClient, "_day_span", None)
    monkeypatch.setattr(dhan_history.time, "sleep", lambda seconds: None)

    def build(server, **kwargs):
        client = DhanHistoryClient(tmp_path, **kwargs)
        assert not client.offline and not client._auth.automatic
        client.session = server
        return client
    return build


def test_multi_day_rolling_request_is_fetched_per_session_day_and_merged(make_client, tmp_path):
    server = FakeDhan()
    client = make_client(server)
    payload = option_payload(date(2026, 11, 2), date(2026, 11, 6), 1, 0, "CALL")
    data = client.request("rollingoption", payload)["data"]
    # one request per day that has index candles, each a one-day range; the range end is excluded
    assert server.rolling == [(d, d + timedelta(days=1)) for d in SESSIONS[:3]] and server.intraday == 1
    assert data["pe"] is None and data["ce"]["iv"] == []
    assert data["ce"]["timestamp"] == [_stamp(d, 9, 15 + k) for d in SESSIONS[:3] for k in range(2)]
    assert data["ce"]["close"] == [2.0, 2.0, 3.0, 3.0, 5.0, 5.0]        # the overrun rows of day + 1 are dropped
    assert len(data["ce"]["strike"]) == 6
    # the merged range and every day are cached: an overlapping range needs only its own index candles
    assert client.request("rollingoption", payload)["data"] == data and len(server.rolling) == 3
    later = client.request("rollingoption", option_payload(date(2026, 11, 3), date(2026, 11, 6), 1, 0, "CALL"))
    assert later["data"]["ce"]["close"] == [3.0, 3.0, 5.0, 5.0] and len(server.rolling) == 3 and server.intraday == 2
    assert DhanHistoryClient(tmp_path, offline=True).request("rollingoption", payload)["data"] == data
    other = client.request("rollingoption", option_payload(date(2026, 11, 2), date(2026, 11, 6), 1, 1, "CALL"))
    assert other["data"]["ce"]["close"] == data["ce"]["close"] and len(server.rolling) == 6    # another series


def test_one_day_requests_pass_straight_through(make_client):
    server = FakeDhan()
    client = make_client(server)
    data = client.request("rollingoption", option_payload(date(2026, 11, 2), date(2026, 11, 3), 1, 0, "CALL"))
    assert server.rolling == [(date(2026, 11, 2), date(2026, 11, 3))] and server.intraday == 0
    assert data["data"]["ce"]["close"] == [2.0, 2.0, 3.0, 3.0]          # raw answer, as before the limit


def test_same_day_form_is_used_when_dhan_refuses_the_next_day_form(make_client):
    server = FakeDhan(accept_spans=(0,))
    client = make_client(server)
    data = client.request("rollingoption", option_payload(date(2026, 11, 2), date(2026, 11, 4), 1, 0, "PUT"))
    assert data["data"]["ce"]["close"] == [2.0, 2.0, 3.0, 3.0]
    # the refused form is tried once, then the accepted form is kept for the rest of the session
    assert server.rolling == [(date(2026, 11, 2), date(2026, 11, 3)), (date(2026, 11, 2), date(2026, 11, 2)),
                              (date(2026, 11, 3), date(2026, 11, 3))]
    assert DhanHistoryClient._day_span == 0


def test_a_refused_day_raises_and_caches_no_partial_range(make_client, tmp_path):
    server = FakeDhan(accept_spans=())
    client = make_client(server)
    payload = option_payload(date(2026, 11, 2), date(2026, 11, 6), 1, 0, "CALL")
    with pytest.raises(DhanHTTPError, match="HTTP 400") as caught:
        client.request("rollingoption", payload)
    assert caught.value.status == 400 and len(server.rolling) == 2      # both one-day forms of the first day only
    with pytest.raises(RuntimeError, match="Missing offline cache"):
        DhanHistoryClient(tmp_path, offline=True).request("rollingoption", payload)


def test_the_current_day_is_not_cached_on_its_own(make_client, monkeypatch):
    monkeypatch.setattr(dhan_history, "_today_ist", lambda: date(2026, 11, 3))
    server = FakeDhan()
    client = make_client(server)
    client.request("rollingoption", option_payload(date(2026, 11, 2), date(2026, 11, 4), 1, 0, "CALL"))
    client.request("rollingoption", option_payload(date(2026, 11, 2), date(2026, 11, 5), 1, 0, "CALL"))
    fetched = [first for first, _ in server.rolling]
    assert fetched == [date(2026, 11, 2), date(2026, 11, 3), date(2026, 11, 3)]     # 2 Nov reused, 3 Nov refetched
