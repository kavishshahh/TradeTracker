"""Read-only Dhan REST live quotes and completed one-minute index candles.

Only data endpoints are allowlisted. There are no order/account methods.
Shared by both strategies; cache lasts one worker round, with global throttling.
"""
from datetime import date, datetime, timedelta
import io
import math
import os
import time

import pandas as pd
import requests

from data.providers.base import MarketDataError, MarketDataProvider, OptionChainSnapshot, OptionQuote
from strategy.bars import complete_bars, normalize_bars
from utils.time import IST, now_ist


def number(value, positive=False):
    try:
        value = float(value)
        return value if math.isfinite(value) and (not positive or value > 0) else None
    except (TypeError, ValueError):
        return None


def trade_time(raw):
    try:
        return datetime.strptime(raw, '%d/%m/%Y %H:%M:%S').replace(tzinfo=IST)
    except (TypeError, ValueError):
        return None


class DhanLiveProvider(MarketDataProvider):
    ENDPOINTS = {'/marketfeed/quote', '/charts/intraday'}
    MASTER = 'https://images.dhan.co/api-data/api-scrip-master-detailed.csv'

    def __init__(self, session=None, clock=now_ist, sleeper=time.sleep):
        self.session = session or requests.Session()
        self.clock, self.sleep = clock, sleeper
        self.headers = {'access-token': os.getenv('DHAN_ACCESS_TOKEN', ''),
                        'client-id': os.getenv('DHAN_CLIENT_ID', ''), 'Content-Type': 'application/json'}
        if not self.headers['access-token'] or not self.headers['client-id']:
            raise MarketDataError('Set DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN in backend/.env')
        self.contracts = None
        self.master_date = None
        self.cache = {}
        self.bars = None
        self.last_request = 0.0

    def begin_round(self):
        self.cache.clear()

    def request(self, endpoint, payload):
        if endpoint not in self.ENDPOINTS:
            raise ValueError('Only read-only Dhan data endpoints are allowed')
        for attempt in range(3):
            self.sleep(max(0, 1.1 - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
            try:
                response = self.session.post('https://api.dhan.co/v2' + endpoint,
                                             headers=self.headers, json=payload, timeout=15)
                if response.status_code in (401, 403):
                    raise MarketDataError('Dhan authentication/data entitlement rejected; update backend token')
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < 2:
                        self.sleep(2 ** attempt)
                        continue
                if response.status_code != 200:
                    raise MarketDataError(f'Dhan data request failed (HTTP {response.status_code})')
                result = response.json()
                if result.get('status') not in (None, 'success') or result.get('errorCode'):
                    raise MarketDataError('Dhan returned a data error; check token and data subscription')
                return result
            except (requests.RequestException, ValueError):
                if attempt == 2:
                    raise MarketDataError('Dhan data connection failed') from None
                self.sleep(2 ** attempt)
        raise MarketDataError('Dhan data request exhausted retries')

    def refresh_master(self):
        today = self.clock().date()
        if self.master_date == today:
            return
        try:
            response = self.session.get(self.MASTER, timeout=60)
            response.raise_for_status()
            frame = pd.read_csv(io.StringIO(response.text), low_memory=False)
            required = {'EXCH_ID', 'INSTRUMENT', 'UNDERLYING_SYMBOL', 'SECURITY_ID',
                        'SM_EXPIRY_DATE', 'STRIKE_PRICE', 'OPTION_TYPE', 'LOT_SIZE'}
            if not required.issubset(frame.columns):
                raise MarketDataError('Dhan instrument master schema changed')
            frame = frame.loc[frame.EXCH_ID.eq('NSE') & frame.INSTRUMENT.eq('OPTIDX') &
                              frame.UNDERLYING_SYMBOL.eq('NIFTY')].copy()
            frame['expiry'] = pd.to_datetime(frame.SM_EXPIRY_DATE).dt.date
            frame = frame[frame.expiry >= today]
            if frame.empty:
                raise MarketDataError('No active NIFTY options in Dhan master')
            self.contracts, self.master_date = frame, today
        except (requests.RequestException, ValueError, KeyError):
            raise MarketDataError('Could not load Dhan instrument master') from None

    def get_expiries(self):
        self.refresh_master()
        return sorted(set(self.contracts.expiry))

    def get_lot_size(self, expiry):
        self.refresh_master()
        values = set(self.contracts.loc[self.contracts.expiry.eq(expiry), 'LOT_SIZE'].astype(int))
        if len(values) != 1 or next(iter(values), 0) <= 0:
            raise MarketDataError('Missing or inconsistent Dhan contract lot size')
        return values.pop()

    def get_option_chain(self, expiry):
        if expiry in self.cache:
            return self.cache[expiry]
        self.refresh_master()
        contracts = self.contracts[self.contracts.expiry.eq(expiry)]
        if contracts.empty:
            raise MarketDataError('Held/requested expiry absent from active Dhan master')
        ids = sorted(set(contracts.SECURITY_ID.astype(int)))
        quotes, spot, times = {}, None, []
        # Include the index in every batch; each quote request is <= 1000 IDs.
        for start in range(0, len(ids), 999):
            payload = self.request('/marketfeed/quote', {'IDX_I': [13], 'NSE_FNO': ids[start:start + 999]})
            data = payload.get('data', {})
            spot = number(data.get('IDX_I', {}).get('13', {}).get('last_price'), positive=True)
            if spot is None:
                raise MarketDataError('Dhan NIFTY live quote missing')
            quotes.update(data.get('NSE_FNO', {}))
        snap = OptionChainSnapshot('NIFTY', expiry, self.clock(), spot)
        now = self.clock()
        for row in contracts.itertuples():
            q = quotes.get(str(int(row.SECURITY_ID)))
            if not q:
                continue
            ts = trade_time(q.get('last_trade_time'))
            # Never use stale/future LTP for fills or indicators. No filling gaps.
            fresh = ts is not None and 0 <= (now - ts).total_seconds() <= 180
            if fresh:
                times.append(ts)
            depth = q.get('depth') or {}
            def best(side):
                rows = depth.get(side) or []
                return number(rows[0].get('price'), positive=True) if rows and fresh else None
            strike, side = float(row.STRIKE_PRICE), row.OPTION_TYPE
            snap.quotes[(strike, side)] = OptionQuote(strike, side,
                number(q.get('last_price'), positive=True) if fresh else None,
                best('buy'), best('sell'), number(q.get('volume')) if fresh else None)
        if not times:
            raise MarketDataError('Dhan option quotes stale or lack valid exchange trade timestamps')
        snap.timestamp = max(times)  # An actual exchange trade timestamp, not receipt time.
        self.cache[expiry] = snap
        return snap

    def get_spot_bars(self, as_of):
        if 'bars' in self.cache:
            return complete_bars(self.cache['bars'], as_of)
        # Bootstrap price alpha from Dhan history; overlap updates to catch revisions.
        start = as_of - timedelta(days=10) if self.bars is None or self.bars.empty else self.bars.index[-1].to_pydatetime() - timedelta(minutes=10)
        result = self.request('/charts/intraday', {'securityId': '13', 'exchangeSegment': 'IDX_I',
            'instrument': 'INDEX', 'interval': '1', 'oi': False,
            'fromDate': start.strftime('%Y-%m-%d %H:%M:%S'), 'toDate': as_of.strftime('%Y-%m-%d %H:%M:%S')})
        try:
            fields = ('open', 'high', 'low', 'close')
            times = result['timestamp']
            if any(len(result[key]) != len(times) for key in fields):
                raise ValueError('length')
            frame = pd.DataFrame({key: result[key] for key in fields}, index=pd.to_datetime(times, unit='s', utc=True)).astype(float)
            frame = normalize_bars(frame)
            if (frame <= 0).any().any():
                raise ValueError('price')
        except (KeyError, TypeError, ValueError):
            raise MarketDataError('Invalid Dhan index candle response') from None
        merged = pd.concat([self.bars, frame]) if self.bars is not None else frame
        self.bars = complete_bars(normalize_bars(merged), as_of)
        self.bars = self.bars[self.bars.index >= as_of - timedelta(days=10)]
        if self.bars.empty:
            raise MarketDataError('No completed Dhan index candles')
        self.cache['bars'] = self.bars
        return self.bars
