"""Self-renewing Dhan tokens: TOTP codes, caching, renewal, rejection handling and failure back-off."""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from data.providers.base import MarketDataError
from data.providers.dhan_auth import FAILURE_BACKOFF, DhanAuthError, DhanTokenSource, totp
from utils.time import IST

RFC_SECRET = 'GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ'     # base32 of "12345678901234567890" (RFC 6238 appendix B)
PIN, SECRET = '135791', RFC_SECRET


def test_totp_matches_rfc_6238_sha1_vectors():
    assert totp(RFC_SECRET, 59, digits=8) == '94287082'
    assert totp(RFC_SECRET, 1111111109, digits=8) == '07081804'
    assert totp(RFC_SECRET, 1234567890) == '005924'          # 6-digit codes as authenticator apps show them
    assert totp(RFC_SECRET.lower(), 59, digits=8) == '94287082'


class FakeAuthSession:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def post(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params)))
        status, body = self.responses.pop(0)
        return SimpleNamespace(status_code=status, json=lambda: body)


class Clock:
    def __init__(self):
        self.now = datetime(2026, 11, 11, 9, 0, tzinfo=IST)

    def __call__(self):
        return self.now


def source(responses, clock=None):
    session = FakeAuthSession(responses)
    return DhanTokenSource('1100', PIN, SECRET, session=session, clock=clock or Clock(), wall=lambda: 59.0), session


def test_generates_once_caches_and_renews_before_expiry():
    clock = Clock()
    auth, session = source([(200, {'accessToken': 'tok-1', 'expiryTime': '2026-11-12T09:00:00.000'}),
                            (200, {'accessToken': 'tok-2', 'expiryTime': '2026-11-13T08:40:00.000'})], clock)
    assert auth.token() == 'tok-1' and auth.token() == 'tok-1'
    url, params = session.calls[0]
    assert url == 'https://auth.dhan.co/app/generateAccessToken'
    assert params == {'dhanClientId': '1100', 'pin': PIN, 'totp': '287082'}
    clock.now += timedelta(hours=23, minutes=29)
    assert auth.token() == 'tok-1'                       # 31 minutes left: still valid
    clock.now += timedelta(minutes=2)
    assert auth.token() == 'tok-2' and len(session.calls) == 2


def test_a_rejected_token_is_replaced_once():
    auth, session = source([(200, {'accessToken': 'tok-1', 'expiryTime': '2026-11-12T09:00:00.000'}),
                            (200, {'accessToken': 'tok-2', 'expiryTime': '2026-11-12T09:05:00.000'})])
    first = auth.token()
    assert auth.rejected(first) is True
    assert auth.token() == 'tok-2'
    assert auth.rejected('tok-1') is True and auth.token() == 'tok-2'   # a stale rejection keeps the new token
    assert len(session.calls) == 2


def test_failure_pauses_generation_and_never_leaks_secrets():
    clock = Clock()
    auth, session = source([(400, {'errorMessage': 'invalid pin'}),
                            (200, {'accessToken': 'tok-ok', 'expiryTime': '2026-11-12T10:00:00.000'})], clock)
    with pytest.raises(DhanAuthError) as first:
        auth.token()
    with pytest.raises(DhanAuthError) as paused:
        auth.token()                                     # inside the back-off: no second login attempt
    assert len(session.calls) == 1
    for message in (str(first.value), str(paused.value)):
        assert PIN not in message and SECRET not in message and '287082' not in message
    assert auth.rejected('anything') is False            # callers stop retrying while paused
    clock.now += FAILURE_BACKOFF
    assert auth.token() == 'tok-ok' and len(session.calls) == 2


def test_fixed_token_mode_is_unchanged():
    auth = DhanTokenSource('1100', static_token='fixed')
    assert not auth.automatic and auth.token() == 'fixed' and auth.rejected('fixed') is False
    with pytest.raises(DhanAuthError):
        DhanTokenSource('1100')
    with pytest.raises(DhanAuthError):
        DhanTokenSource('', PIN, SECRET)


def test_live_provider_regenerates_once_after_a_401():
    from data.providers.dhan import DhanLiveProvider
    auth, _ = source([(200, {'accessToken': 'old', 'expiryTime': '2026-11-12T09:00:00.000'}),
                      (200, {'accessToken': 'new', 'expiryTime': '2026-11-12T09:01:00.000'}),
                      (200, {'accessToken': 'newer', 'expiryTime': '2026-11-12T09:02:00.000'})])

    class DataSession:
        def __init__(self, statuses):
            self.statuses, self.tokens = list(statuses), []

        def post(self, url, headers=None, json=None, timeout=None):
            self.tokens.append(headers['access-token'])
            status = self.statuses.pop(0)
            return SimpleNamespace(status_code=status, json=lambda: {'data': {}})

    data = DataSession([401, 200])
    provider = DhanLiveProvider(session=data, sleeper=lambda *_: None, auth=auth)
    assert provider.request('/charts/intraday', {}) == {'data': {}}
    assert data.tokens == ['old', 'new']

    data = DataSession([401, 401])
    provider = DhanLiveProvider(session=data, sleeper=lambda *_: None, auth=auth)
    with pytest.raises(MarketDataError, match='freshly generated token'):
        provider.request('/charts/intraday', {})
    assert data.tokens == ['new', 'newer']               # exactly one regeneration, then a clear error
