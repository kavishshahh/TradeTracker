"""Dhan order and account endpoints used by the live desk (execution/live.py).

Kept apart from data/providers/dhan.py, whose allowlist is read-only. This client can place and cancel
real orders, so:

- LIVE_ORDERS below is False: live trading is switched off in the code. While it is False this client
  cannot be constructed and cannot send an order, whatever the settings or the environment say. Dry run
  uses SimBroker, which makes no request at all.
- Once LIVE_ORDERS is True, it is still only constructed when a strategy is switched to live AND the
  server sets LIVE_TRADING_ENABLED=true.
- Every order carries a correlation id the caller stored first. A request that times out is never sent
  again blindly: the caller looks the order up by that id before deciding anything.
- Dhan refuses order requests from an IP that is not whitelisted for the account (SEBI retail algo rules,
  DhanHQ v2.4). That refusal arrives as a rejection and is reported like any other.

Endpoints (https://dhanhq.co/docs/v2/orders/, /portfolio/, /funds/): POST /orders, GET /orders,
GET /orders/{id}, GET /orders/external/{correlation-id}, DELETE /orders/{id}, GET /positions, GET /fundlimit.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass

import requests

from data.providers.dhan_auth import DhanAuthError, shared_source

# The master switch for real orders. False since 22 Nov 2026 by the owner's decision: paper and dry run
# only, to be reviewed after some months of dry-run results. Turning it on is a deliberate code change
# (here, and LIVE_TRADING_AVAILABLE in backend/algos_api.py), not a setting.
LIVE_ORDERS = False
OFF_MESSAGE = 'live orders are switched off in this build'

FINAL = frozenset({'TRADED', 'REJECTED', 'CANCELLED', 'EXPIRED'})
SEGMENT = 'NSE_FNO'
PRODUCT = 'MARGIN'            # carry-forward F&O: positions are held overnight


class BrokerError(RuntimeError):
    """The broker could not be reached or answered unusably; the outcome of the request is unknown."""


class BrokerRejected(BrokerError):
    """The broker refused the request; nothing was placed."""


@dataclass(frozen=True)
class OrderState:
    order_id: str
    status: str
    filled_qty: int = 0
    avg_price: float | None = None
    reason: str | None = None

    @property
    def final(self) -> bool:
        return self.status in FINAL


def _number(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def order_state(raw: dict) -> OrderState:
    filled = int(_number(raw.get('filledQty')) or 0)
    avg = _number(raw.get('averageTradedPrice'))
    reason = raw.get('omsErrorDescription') or None
    return OrderState(str(raw.get('orderId') or ''), str(raw.get('orderStatus') or 'UNKNOWN').upper(), filled,
                      avg if avg and avg > 0 else None, str(reason)[:200] if reason else None)


class DhanBroker:
    BASE = 'https://api.dhan.co/v2'
    MIN_GAP_SECONDS = 0.15        # Dhan allows 10 order requests a second

    def __init__(self, session=None, auth=None, sleeper=time.sleep):
        if not LIVE_ORDERS:
            raise BrokerError(OFF_MESSAGE)
        self.session = session or requests.Session()
        self.sleep = sleeper
        try:
            self.auth = auth or shared_source()
        except DhanAuthError as exc:
            raise BrokerError(str(exc)) from None
        self.last_request = 0.0

    # ------------------------------------------------------------------ transport
    def _call(self, method: str, path: str, payload: dict | None = None):
        """(status code, decoded body). Raises BrokerError when no usable answer came back."""
        reauthorised = False
        while True:
            self.sleep(max(0.0, self.MIN_GAP_SECONDS - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
            try:
                token = self.auth.token()
            except DhanAuthError as exc:
                raise BrokerError(str(exc)) from None
            headers = {'access-token': token, 'client-id': self.auth.client_id,
                       'Content-Type': 'application/json', 'Accept': 'application/json'}
            try:
                response = self.session.request(method, self.BASE + path, headers=headers, json=payload, timeout=10)
            except requests.RequestException as exc:
                raise BrokerError(f'Dhan order connection failed ({type(exc).__name__})') from None
            if response.status_code == 401 and not reauthorised and self.auth.rejected(token):
                reauthorised = True       # an expired token was refused before anything was placed
                continue
            try:
                body = response.json() if response.content else {}
            except ValueError:
                body = {}
            return response.status_code, body

    @staticmethod
    def _error(body) -> str:
        if isinstance(body, dict):
            parts = [str(body.get(key)) for key in ('errorCode', 'errorMessage') if body.get(key)]
            if parts:
                return ' '.join(parts)[:200]
        return 'no reason given'

    # ------------------------------------------------------------------ orders
    def place(self, *, correlation_id: str, side: str, security_id: str, quantity: int,
              price: float | None, market: dict | None = None) -> OrderState:
        """One DAY order: LIMIT at ``price``, or MARKET when ``price`` is None. ``market`` is ignored here
        (the simulated broker fills against it)."""
        if not LIVE_ORDERS:
            raise BrokerRejected(OFF_MESSAGE)
        if side not in ('BUY', 'SELL') or quantity <= 0:
            raise ValueError('invalid order')
        payload = {'dhanClientId': self.auth.client_id, 'correlationId': correlation_id, 'transactionType': side,
                   'exchangeSegment': SEGMENT, 'productType': PRODUCT,
                   'orderType': 'MARKET' if price is None else 'LIMIT', 'validity': 'DAY',
                   'securityId': str(security_id), 'quantity': int(quantity), 'disclosedQuantity': 0,
                   'price': 0 if price is None else float(price), 'triggerPrice': 0, 'afterMarketOrder': False}
        status, body = self._call('POST', '/orders', payload)
        if status in (200, 201, 202) and isinstance(body, dict) and body.get('orderId'):
            state = order_state(body)
            if state.status == 'REJECTED':
                raise BrokerRejected(state.reason or self._error(body))
            return state
        if 400 <= status < 500 and status != 429:
            raise BrokerRejected(self._error(body))
        raise BrokerError(f'Dhan order request unanswered (HTTP {status})')

    def order(self, order_id: str) -> OrderState:
        status, body = self._call('GET', f'/orders/{order_id}')
        if isinstance(body, list):
            body = body[0] if body else {}
        if status != 200 or not isinstance(body, dict) or not body.get('orderStatus'):
            raise BrokerError(f'Dhan order status unavailable (HTTP {status})')
        return order_state({**body, 'orderId': body.get('orderId') or order_id})

    def order_by_correlation(self, correlation_id: str) -> OrderState | None:
        """The order carrying this correlation id, or None when today's order book has none.
        A lookup miss is confirmed against the full order book before reporting None."""
        status, body = self._call('GET', f'/orders/external/{correlation_id}')
        if isinstance(body, list):
            body = body[0] if body else {}
        if status == 200 and isinstance(body, dict) and body.get('orderId'):
            return order_state(body)
        status, book = self._call('GET', '/orders')
        if status != 200 or not isinstance(book, list):
            raise BrokerError(f'Dhan order book unavailable (HTTP {status})')
        for row in book:
            if isinstance(row, dict) and row.get('correlationId') == correlation_id and row.get('orderId'):
                return order_state(row)
        return None

    def cancel(self, order_id: str) -> None:
        status, body = self._call('DELETE', f'/orders/{order_id}')
        if status >= 500 or status == 429:
            raise BrokerError(f'Dhan cancel unanswered (HTTP {status})')
        # A 4xx here means the order is no longer pending (filled or already cancelled); the caller re-reads it.

    # ------------------------------------------------------------------ account
    def positions(self) -> dict[str, int]:
        """Net quantity by security id for NSE F&O, zero rows dropped."""
        status, body = self._call('GET', '/positions')
        if status != 200 or not isinstance(body, list):
            raise BrokerError(f'Dhan positions unavailable (HTTP {status})')
        net: dict[str, int] = {}
        for row in body:
            if isinstance(row, dict) and row.get('exchangeSegment') == SEGMENT:
                key = str(row.get('securityId'))
                net[key] = net.get(key, 0) + int(_number(row.get('netQty')) or 0)
        return {key: qty for key, qty in net.items() if qty}

    def available_balance(self) -> float:
        status, body = self._call('GET', '/fundlimit')
        value = None
        if status == 200 and isinstance(body, dict):
            value = _number(body.get('availabelBalance'))          # Dhan's spelling
            if value is None:
                value = _number(body.get('availableBalance'))
        if value is None:
            raise BrokerError(f'Dhan fund limit unavailable (HTTP {status})')
        return value


class SimBroker:
    """Dry run: no request leaves the process. A BUY fills at the ask and a SELL at the bid when the limit
    allows it (a market order always fills); otherwise the order rests and is cancelled unfilled."""

    def __init__(self):
        self.orders: dict[str, OrderState] = {}
        self.by_correlation: dict[str, str] = {}

    def place(self, *, correlation_id, side, security_id, quantity, price, market=None) -> OrderState:
        market = market or {}
        touch = market.get('ask') if side == 'BUY' else market.get('bid')
        touch = touch if touch is not None else market.get('ltp')
        order_id = f'SIM{len(self.orders) + 1}'
        crosses = touch is not None and (price is None or (price >= touch if side == 'BUY' else price <= touch))
        state = (OrderState(order_id, 'TRADED', int(quantity), float(touch)) if crosses
                 else OrderState(order_id, 'PENDING'))
        self.orders[order_id], self.by_correlation[correlation_id] = state, order_id
        return state

    def order(self, order_id) -> OrderState:
        return self.orders[order_id]

    def order_by_correlation(self, correlation_id) -> OrderState | None:
        order_id = self.by_correlation.get(correlation_id)
        return self.orders[order_id] if order_id else None

    def cancel(self, order_id) -> None:
        state = self.orders[order_id]
        if not state.final:
            self.orders[order_id] = OrderState(order_id, 'CANCELLED', state.filled_qty, state.avg_price)

    def positions(self) -> dict[str, int]:
        return {}

    def available_balance(self) -> float:
        return math.inf
