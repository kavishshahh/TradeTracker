"""zen_strategy_11 (Momentum Expiry Puts): the first option-buying strategy. Entry rules, the long-option arithmetic
of stop / target / time exit, and the order desk buying and selling one option."""
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from data.market_calendar import HolidaySetCalendar
from data.providers.base import OptionChainSnapshot, OptionQuote
from execution.live import LiveDesk, paper_view
from execution.store import PositionRecord, row_to_position
from strategy import registry
from strategy import zen_strategy_11_expiry_puts as m
from strategy.engine import MarketView
from strategy.implied_vol import bs_price, years_to_expiry
from utils.time import IST

import execution.broker as broker_module

EXPIRY = date(2026, 11, 24)                                   # Tuesday
NOW = datetime(2026, 11, 23, 12, 15, tzinfo=IST)              # Monday: one day to expiry
STRIKE = 24050.0


def bars(now=NOW, fall=0.002, minutes=200):
    """Start-indexed one-minute candles ending at now - 1 minute: a steady fall, flat over the last 6 minutes."""
    idx = pd.date_range(end=now - timedelta(minutes=1), periods=minutes, freq='min', tz=IST)
    path = np.linspace(24050.0 * (1 + fall), 24050.0, minutes - 6)
    close = np.concatenate([path, np.full(6, 24050.0)])
    return pd.DataFrame({'open': close, 'high': close, 'low': close, 'close': close, 'volume': 0.0}, index=idx)


def snapshots(now=NOW, minutes=400, top=True, put_cheaper=True):
    """Chain rows whose ATM IV rises steadily (so the latest is the highest of its 375-minute window when ``top``)."""
    rows = []
    for k in range(minutes):
        minute = now - timedelta(minutes=minutes - 1 - k)
        sigma = 0.12 + 0.03 * k / minutes if top else 0.15 - 0.03 * k / minutes
        t = float(years_to_expiry(pd.DatetimeIndex([minute]), [EXPIRY])[0])
        ce = float(bs_price(24050.0, STRIKE, t, sigma, True, rate=0.065))
        pe = float(bs_price(24050.0, STRIKE, t, sigma - (0.005 if put_cheaper else -0.005), False, rate=0.065))
        rows.append(dict(minute=minute, expiry=EXPIRY, strike=STRIKE, spot=24050.0, ce_ltp=ce, pe_ltp=pe, ce_bid=ce, ce_ask=ce,
                         pe_bid=pe, pe_ask=pe, ce_cum_volume=0.0, pe_cum_volume=0.0))
    return pd.DataFrame(rows)


def chain(now=NOW, put=100.0):
    c = OptionChainSnapshot('NIFTY', EXPIRY, now, 24050.0)
    c.quotes[(STRIKE, 'PE')] = OptionQuote(STRIKE, 'PE', put, put - 0.5, put + 0.5, 1000)
    c.quotes[(STRIKE, 'CE')] = OptionQuote(STRIKE, 'CE', 110.0, 109.5, 110.5, 1000)
    return c


def view(now=NOW, put=100.0, **kw):
    return MarketView(now=now, spot_bars=kw.get('spot_bars', bars(now)), snapshots=kw.get('snaps', snapshots(now)),
                      chain=chain(now, put), expiries=[EXPIRY], lot_size=65)


def engine():
    return registry.create_engine('zen_strategy_11', None, HolidaySetCalendar(set()), max_data_age_seconds=None)


def test_buys_the_atm_put_sized_at_15_percent_of_capital_with_long_option_levels():
    res = engine().evaluate(view(), None)
    assert res.action == 'entry', res.reason
    p = res.position
    # 7.5% of 320,000 = 24,000 of premium: floor(24,000 / (100 x 65)) = 3 lots
    assert (p.structure, p.option_type, p.buy_strike, p.lots, p.units) == ('long_option', 'PE', STRIKE, 3, 195)
    assert (p.buy_price, p.sell_price, p.net_credit, p.stop_loss, p.target) == (100.0, 0.0, -100.0, -80.0, -300.0)
    assert p.exit_due == datetime(2026, 11, 23, 15, 10, tzinfo=IST)
    assert res.diagnostics['iv_rank'] == pytest.approx(1.0) and res.diagnostics['trend'] < -0.001


@pytest.mark.parametrize('change, reason', [
    (dict(now=datetime(2026, 11, 18, 12, 15, tzinfo=IST)), 'not an entry day'),          # Wednesday, 6 days to expiry
    (dict(now=datetime(2026, 11, 23, 9, 30, tzinfo=IST)), 'outside signal window'),
    (dict(spot_bars=bars(fall=0.0005)), 'no signal'),                                     # the fall is too small
    (dict(snaps=snapshots(top=False)), 'no signal'),                                      # volatility falling, not at its top
    (dict(snaps=snapshots(put_cheaper=False)), 'no signal'),                              # puts dearer than calls
])
def test_no_entry_without_every_condition(change, reason):
    now = change.pop('now', NOW)
    v = view(now, **change)
    if now != NOW:
        v = MarketView(now=now, spot_bars=bars(now), snapshots=snapshots(now), chain=chain(now), expiries=[EXPIRY], lot_size=65)
    res = engine().evaluate(v, None)
    assert res.action == 'none' and reason in res.reason


@pytest.mark.parametrize('put, at, reason, pnl', [
    (79.0, datetime(2026, 11, 23, 12, 30, tzinfo=IST), 'Stop loss', (79.0 - 100.0) * 195),
    (301.0, datetime(2026, 11, 23, 12, 30, tzinfo=IST), 'Target', (301.0 - 100.0) * 195),
    (120.0, datetime(2026, 11, 23, 15, 10, tzinfo=IST), 'Time exit', (120.0 - 100.0) * 195),
])
def test_exits_sell_the_option_at_the_stop_the_target_or_15_10(put, at, reason, pnl):
    e = engine()
    pos = e.evaluate(view(), None).position
    assert e.evaluate(view(datetime(2026, 11, 23, 12, 20, tzinfo=IST), put=110.0), pos).action == 'none'
    res = e.evaluate(view(at, put=put), pos)
    assert res.action == 'exit' and res.reason == reason
    assert res.exit.exit_value == pytest.approx(-put) and res.exit.pnl == pytest.approx(pnl)
    assert (res.exit.sell_exit_price, res.exit.buy_exit_price) == (0.0, put)


def test_a_third_trade_in_a_day_is_refused():
    e = engine()
    for k in range(2):
        e.note_exit(datetime(2026, 11, 23, 11, k, tzinfo=IST), 'Stop loss')
    res = e.evaluate(view(), None)
    assert res.action == 'none' and 'limit 2' in res.reason


def test_the_stored_row_keeps_the_long_option_structure():
    pos = engine().evaluate(view(), None).position
    fields = {f: getattr(pos, f, None) for f in PositionRecord.__dataclass_fields__}
    fields.update(id=1, status='open', strategy_state='IN_POSITION', direction='BEARISH', entry_spread_price=pos.net_credit,
                  entry_email_status='none', entry_email_attempts=0, exit_email_status='none', exit_email_attempts=0)
    back = row_to_position(PositionRecord(**fields))
    assert back.structure == 'long_option' and back.net_credit == -100.0
    old = PositionRecord(**{**fields, 'structure': None})
    assert row_to_position(old).structure == 'credit_spread'          # rows saved before the field existed


# ------------------------------------------------------------------ the order desk, one bought option
class Store:
    def __init__(self, account):
        self.account_doc, self.states, self.archived = account, {}, []

    def account(self): return dict(self.account_doc)
    def state(self, name): return self.states.get(name)
    def save_state(self, name, state): self.states[name] = state
    def archive(self, name, trade): self.archived.append(trade)
    def save_desk(self, payload): pass


class Provider:
    def __init__(self): self.book = (99.0, 100.0, 99.5)
    def security_id(self, expiry, strike, option_type): return '7001'
    def get_option_chain(self, expiry):
        c = OptionChainSnapshot('NIFTY', expiry, NOW, 24050.0)
        bid, ask, ltp = self.book
        c.quotes[(STRIKE, 'PE')] = OptionQuote(STRIKE, 'PE', ltp, bid, ask, 1000)
        return c
    def get_expiry_settlement(self, expiry): return None


def paper(lots=3):
    return SimpleNamespace(signal_id='put-0001', expiry=EXPIRY, option_type='PE', sell_strike=STRIKE, buy_strike=STRIKE,
                           lots=lots, lot_size=65, sell_price=0.0, buy_price=99.5, net_credit=-99.5, stop_loss=-79.6,
                           target=-298.5, exit_reason=None, exit_value=None, structure='long_option')


@pytest.fixture
def made(monkeypatch):
    monkeypatch.setattr(broker_module, 'LIVE_ORDERS', True)
    store = Store({'strategies': {'zen_strategy_11': {'mode': 'dry_run', 'capital': 320000}}})
    provider, clock = Provider(), [0.0]
    desk = LiveDesk(store, provider, notifier=SimpleNamespace(_send=lambda s, b: None), env={}, names={'zen_strategy_11': 'Momentum Expiry Puts'},
                    sleeper=lambda s: clock.__setitem__(0, clock[0] + s), mono=lambda: clock[0])
    desk.begin_round(NOW)
    return desk, store, provider


def test_dry_run_buys_one_option_and_sells_it_when_the_paper_trade_closes(made):
    desk, store, provider = made
    cfg = registry.apply_profile('zen_strategy_11')
    desk.step('zen_strategy_11', cfg, paper_view(paper(), entered=True), True, NOW)
    trade = store.states['zen_strategy_11']['open_trade']
    # 7.5% of the deployed 320,000 at the 100.0 ask: floor(24,000 / 6,500) = 3 lots, one BUY order, no short leg
    assert (trade['structure'], trade['state'], trade['lots'], trade['units']) == ('long_option', 'open', 3, 195)
    assert list(trade['legs']) == ['hedge_entry'] and trade['legs']['hedge_entry']['side'] == 'BUY'
    assert trade['entry_credit'] == pytest.approx(-trade['legs']['hedge_entry']['avg'])
    provider.book = (129.0, 130.0, 129.5)
    closed = SimpleNamespace(**{**vars(paper()), 'exit_reason': 'Target', 'exit_value': -129.5})
    desk.step('zen_strategy_11', cfg, paper_view(None, closed), True, NOW + timedelta(minutes=30))
    done = store.states['zen_strategy_11']['recent'][-1]
    assert done['state'] == 'closed' and done['exit_reason'] == 'Target'
    assert set(done['fills']) == {'hedge_entry', 'hedge_exit'} and done['fills']['hedge_exit']['side'] == 'SELL'
    bought, sold = done['fills']['hedge_entry']['avg'], done['fills']['hedge_exit']['avg']
    assert done['pnl'] == pytest.approx((sold - bought) * 195) and done['pnl'] > 0
    assert done['exit_value'] == pytest.approx(-sold)
