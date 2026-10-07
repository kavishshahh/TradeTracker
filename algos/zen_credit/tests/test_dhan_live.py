"""Offline Dhan parser/worker checks. Never reads credentials or connects to Firebase."""
from datetime import date, datetime, timedelta
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import pandas as pd

from data.providers.base import MarketDataError
from data.providers.dhan import DhanLiveProvider
from paper_worker import run_round
from utils.time import IST

NOW = datetime(2026, 10, 7, 10, 30, 5, tzinfo=IST)
EXPIRY = date(2026, 10, 13)


def provider():
    with patch.dict('os.environ', {'DHAN_CLIENT_ID': 'test', 'DHAN_ACCESS_TOKEN': 'test'}):
        result = DhanLiveProvider(clock=lambda: NOW, sleeper=lambda *_: None)
    result.master_date = NOW.date()
    result.contracts = pd.DataFrame({'expiry': [EXPIRY] * 3, 'SECURITY_ID': [1, 2, 3],
        'STRIKE_PRICE': [23000., 23000., 23400.], 'OPTION_TYPE': ['CE', 'PE', 'CE'], 'LOT_SIZE': [65] * 3})
    return result


class DhanLiveTests(unittest.TestCase):
    def test_quotes_preserve_contract_identity_volume_depth_and_exchange_age(self):
        p = provider()
        fresh = {'last_price': 100, 'volume': 1500, 'last_trade_time': '07/10/2026 10:30:00',
                 'depth': {'buy': [{'price': 99}], 'sell': [{'price': 101}]}}
        stale = {**fresh, 'last_trade_time': '06/10/2026 15:29:00'}
        calls = []
        p.request = lambda endpoint, payload: calls.append((endpoint, payload)) or {
            'data': {'IDX_I': {'13': {'last_price': 23010}}, 'NSE_FNO': {'1': fresh, '2': fresh, '3': stale}}}
        chain = p.get_option_chain(EXPIRY)
        self.assertEqual(chain.timestamp, NOW.replace(second=0))
        self.assertEqual(chain.quote(23000, 'CE').cum_volume, 1500)
        self.assertEqual(chain.quote(23000, 'CE').bid, 99)
        self.assertIsNone(chain.quote(23400, 'CE').ltp)
        self.assertIsNone(chain.quote(23400, 'CE').cum_volume)
        self.assertIs(p.get_option_chain(EXPIRY), chain)
        self.assertEqual(len(calls), 1)
        p.begin_round()
        p.get_option_chain(EXPIRY)
        self.assertEqual(len(calls), 2)
        self.assertEqual(p.get_lot_size(EXPIRY), 65)

    def test_no_future_candles_stale_feed_or_order_endpoint(self):
        p = provider()
        timestamps = [NOW.replace(second=0) - timedelta(minutes=1), NOW.replace(second=0)]
        p.request = lambda *_: {'timestamp': [int(x.timestamp()) for x in timestamps],
            'open': [23000, 23001], 'high': [23002, 23003], 'low': [22999, 23000], 'close': [23001, 23002]}
        bars = p.get_spot_bars(NOW)
        self.assertEqual(len(bars), 1)
        self.assertEqual(bars.index[-1].minute, 29)
        p.request = lambda *_: {'data': {'IDX_I': {'13': {'last_price': 23000}},
            'NSE_FNO': {'1': {'last_price': 100, 'last_trade_time': '01/01/1980 00:00:00'}}}}
        with self.assertRaises(MarketDataError): p.get_option_chain(EXPIRY)
        with self.assertRaises(ValueError): DhanLiveProvider.request(p, '/orders', {})

    def test_auth_errors_are_sanitized_and_not_retried(self):
        p = provider()
        p.session = SimpleNamespace(post=lambda *_args, **_kwargs: SimpleNamespace(status_code=401))
        with self.assertRaisesRegex(MarketDataError, 'authentication'):
            p.request('/marketfeed/quote', {})

    def test_strategy_failure_does_not_block_other_strategy_and_disabled_position_exits(self):
        calls = []
        def fail(now): raise MarketDataError('secret must not appear')
        runners = {
            'a': SimpleNamespace(locked_cycle=fail, store=SimpleNamespace(open_position_row=lambda: None)),
            'b': SimpleNamespace(locked_cycle=lambda now: calls.append(now) or {'status': 'exit'}, store=SimpleNamespace(open_position_row=lambda: object())),
            'c': SimpleNamespace(locked_cycle=lambda now: self.fail('disabled flat strategy ran'), store=SimpleNamespace(open_position_row=lambda: None)),
        }
        result = run_round(runners, {'a': {'enabled': True}, 'b': {'enabled': False}, 'c': {'enabled': False}}, NOW)
        self.assertEqual(result['a']['reason'], 'MarketDataError')
        self.assertEqual(result['b']['status'], 'exit')
        self.assertEqual(len(calls), 1)


if __name__ == '__main__': unittest.main()
