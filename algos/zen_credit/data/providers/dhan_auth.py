"""Dhan access tokens that renew themselves (TOTP), or a fixed token from the environment.

Dhan tokens last 24 hours. With DHAN_PIN and DHAN_TOTP_SECRET set (TOTP enabled under Dhan Web >
DhanHQ Trading APIs > Setup TOTP), a token is generated with
POST https://auth.dhan.co/app/generateAccessToken?dhanClientId=..&pin=..&totp=.. whenever none is
cached, the cached one is within RENEW_BEFORE of expiry, or Dhan rejects it. Without them, the
fixed DHAN_ACCESS_TOKEN is used exactly as before.

Safety: a failed generation (wrong PIN or TOTP, network) blocks further attempts for FAILURE_BACKOFF
so a bad secret can never hammer the login endpoint and lock the account. The PIN, TOTP secret, codes
and tokens are never logged or put in exception messages. This module only obtains tokens; callers
keep their own allowlists of read-only data endpoints.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import struct
import threading
import time
from datetime import datetime, timedelta

import requests

from utils.time import IST

log = logging.getLogger('dhan.auth')
GENERATE_URL = 'https://auth.dhan.co/app/generateAccessToken'
RENEW_BEFORE = timedelta(minutes=30)
FAILURE_BACKOFF = timedelta(minutes=15)


class DhanAuthError(RuntimeError):
    """No usable token; the message never contains secrets."""


def totp(secret: str, at: float | None = None, step: int = 30, digits: int = 6) -> str:
    """RFC 6238 TOTP (HMAC-SHA1), as authenticator apps compute it from the base32 setup key."""
    key = base64.b32decode(secret.replace(' ', '').upper() + '=' * (-len(secret.replace(' ', '')) % 8))
    counter = int((time.time() if at is None else at) // step)
    digest = hmac.new(key, struct.pack('>Q', counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack('>I', digest[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(code).zfill(digits)


def _expiry(raw) -> datetime | None:
    """Dhan returns e.g. '2026-01-01T00:00:00.000' (IST, no zone)."""
    try:
        moment = datetime.fromisoformat(str(raw).replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=IST)


class DhanTokenSource:
    """Thread-safe access token for one Dhan client id."""

    def __init__(self, client_id: str, pin: str | None = None, totp_secret: str | None = None,
                 static_token: str | None = None, session=None, clock=None, wall=time.time):
        if not client_id:
            raise DhanAuthError('Set DHAN_CLIENT_ID')
        self.client_id = client_id
        self._pin, self._secret = pin or None, totp_secret or None
        self.automatic = bool(self._pin and self._secret)
        if not self.automatic and not static_token:
            raise DhanAuthError('Set DHAN_ACCESS_TOKEN, or DHAN_PIN and DHAN_TOTP_SECRET for automatic renewal')
        self._token = None if self.automatic else static_token
        self._expires: datetime | None = None
        self._blocked_until: datetime | None = None
        self.session = session or requests.Session()
        self.clock = clock or (lambda: datetime.now(IST))
        self.wall = wall
        self._lock = threading.Lock()

    @classmethod
    def from_env(cls, values=None, **kwargs) -> 'DhanTokenSource':
        get = (values or {}).get if values is not None else (lambda key: None)
        def read(key):
            return os.getenv(key) or get(key) or None
        return cls(read('DHAN_CLIENT_ID') or '', read('DHAN_PIN'), read('DHAN_TOTP_SECRET'), read('DHAN_ACCESS_TOKEN'), **kwargs)

    def token(self) -> str:
        with self._lock:
            if not self.automatic:
                return self._token
            if self._token is None or (self._expires is not None and self.clock() >= self._expires - RENEW_BEFORE):
                self._generate()
            return self._token

    def rejected(self, token: str) -> bool:
        """Dhan refused ``token``: drop it so the next ``token()`` generates a new one. Returns whether a
        retry can help (False for a fixed token, or while generation is backing off after a failure)."""
        with self._lock:
            if not self.automatic:
                return False
            if self._token == token:
                self._token, self._expires = None, None
            return self._blocked_until is None or self.clock() >= self._blocked_until

    def _generate(self):
        now = self.clock()
        if self._blocked_until is not None and now < self._blocked_until:
            raise DhanAuthError(f'Dhan token generation paused after a failure until {self._blocked_until:%H:%M} IST')
        params = {'dhanClientId': self.client_id, 'pin': self._pin, 'totp': totp(self._secret, self.wall())}
        try:
            response = self.session.post(GENERATE_URL, params=params, timeout=20)
            body = response.json() if response.status_code == 200 else {}
        except (requests.RequestException, ValueError):
            response, body = None, {}
        token = body.get('accessToken') if isinstance(body, dict) else None
        if not token:
            self._blocked_until = now + FAILURE_BACKOFF
            status = getattr(response, 'status_code', 'no response')
            log.error('dhan_token_generation_failed status=%s paused_until=%s', status, self._blocked_until.isoformat())
            raise DhanAuthError(f'Dhan token generation failed (HTTP {status}); check DHAN_PIN, DHAN_TOTP_SECRET and TOTP setup')
        self._token, self._blocked_until = token, None
        self._expires = _expiry(body.get('expiryTime')) or now + timedelta(hours=24)
        log.info('dhan_token_generated expires=%s', self._expires.isoformat())


_SHARED: dict[tuple, DhanTokenSource] = {}
_SHARED_LOCK = threading.Lock()


def shared_source(values=None) -> DhanTokenSource:
    """One token source per process and credential set, so every client (and every download thread)
    reuses the same token instead of generating its own."""
    get = (values or {}).get
    def read(key):
        return os.getenv(key) or get(key) or None
    key = tuple(read(k) for k in ('DHAN_CLIENT_ID', 'DHAN_PIN', 'DHAN_TOTP_SECRET', 'DHAN_ACCESS_TOKEN'))
    with _SHARED_LOCK:
        if key not in _SHARED:
            _SHARED[key] = DhanTokenSource(key[0] or '', key[1], key[2], key[3])
        return _SHARED[key]
