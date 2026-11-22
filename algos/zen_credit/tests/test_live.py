"""Live order desk: real orders mirror the paper position, and every way an order can go wrong is handled."""
import copy
from contextlib import contextmanager
from dataclasses import replace
from datetime import date, datetime
from types import SimpleNamespace

import pytest

from data.providers.base import OptionChainSnapshot, OptionQuote
from execution.broker import BrokerError, BrokerRejected, DhanBroker, OrderState, SimBroker
from execution.live import LiveDesk, correlation, paper_view, tick
from strategy import registry
from utils.time import IST

import execution.broker as broker_module


@pytest.fixture(autouse=True)
def live_orders_on(request, monkeypatch):
    """The shipped build has live orders switched off. These tests exercise the dormant order flow against
    fakes, so they switch it on in memory; the ``test_as_shipped_*`` tests run with the switch as shipped."""
    if not request.node.name.startswith('test_as_shipped'):
        monkeypatch.setattr(broker_module, 'LIVE_ORDERS', True)


EXPIRY = date(2026, 11, 24)
NOW = datetime(2026, 11, 23, 12, 15, tzinfo=IST)            # a Monday, the day before expiry
CFG = registry.apply_profile('zen_strategy_10')              # 400 wide, stop 45, loss cap 2.5%
SELL, BUY = 24000.0, 23600.0                                 # a credit put spread
IDS = {SELL: '5001', BUY: '5002'}


class Store:
    def __init__(self, account=None):
        self.account_doc, self.states, self.archived, self.desk = account or {}, {}, [], None
        self.state_reads = self.account_reads = self.saves = 0

    def account(self):
        self.account_reads += 1
        return copy.deepcopy(self.account_doc)

    def state(self, name):
        self.state_reads += 1
        return copy.deepcopy(self.states.get(name))

    def save_state(self, name, state):
        self.saves += 1
        self.states[name] = copy.deepcopy(state)

    def archive(self, name, trade):
        self.archived.append(copy.deepcopy(trade))

    def save_desk(self, payload):
        self.desk = payload


class Provider:
    """Short leg 90.0 x 91.0, hedge 3.0 x 3.5 unless a test moves them."""
    def __init__(self):
        self.book = {SELL: (90.0, 91.0, 90.5), BUY: (3.0, 3.5, 3.2)}
        self.settlement = None

    def security_id(self, expiry, strike, option_type):
        return IDS[strike]

    def get_option_chain(self, expiry):
        chain = OptionChainSnapshot('NIFTY', expiry, NOW, 24050.0)
        for strike, (bid, ask, ltp) in self.book.items():
            chain.quotes[(strike, 'PE')] = OptionQuote(strike, 'PE', ltp, bid, ask, 1000)
        return chain

    def get_expiry_settlement(self, expiry):
        return self.settlement


class Broker:
    """Fills a crossing order in full at the touch unless a test scripts something else."""
    def __init__(self):
        self.orders, self.by_cid, self.placed, self.cancelled = {}, {}, [], []
        self.balance, self.book = 1_000_000.0, {}
        self.on_place = None           # callable(request) -> OrderState | raises

    def place(self, *, correlation_id, side, security_id, quantity, price, market=None):
        request = dict(cid=correlation_id, side=side, security_id=security_id, quantity=quantity, price=price, market=market)
        self.placed.append(request)
        order_id = f'O{len(self.placed)}'
        state = self.on_place(request, order_id) if self.on_place else None
        if state is None:
            touch = market['ask'] if side == 'BUY' else market['bid']
            crosses = price is None or (price >= touch if side == 'BUY' else price <= touch)
            state = OrderState(order_id, 'TRADED', quantity, touch) if crosses else OrderState(order_id, 'PENDING')
        self.orders[order_id], self.by_cid[correlation_id] = state, order_id
        if state.filled_qty:
            self.book[security_id] = self.book.get(security_id, 0) + (1 if side == 'BUY' else -1) * state.filled_qty
        return state

    def order(self, order_id):
        return self.orders[order_id]

    def order_by_correlation(self, correlation_id):
        return self.orders.get(self.by_cid.get(correlation_id))

    def cancel(self, order_id):
        self.cancelled.append(order_id)
        state = self.orders[order_id]
        if not state.final:
            self.orders[order_id] = OrderState(order_id, 'CANCELLED', state.filled_qty, state.avg_price)

    def positions(self):
        return {sid: qty for sid, qty in self.book.items() if qty}

    def available_balance(self):
        return self.balance


def paper_row(signal_id='sig-0001', lots=2, **changes):
    row = dict(signal_id=signal_id, expiry=EXPIRY, option_type='PE', sell_strike=SELL, buy_strike=BUY, lots=lots,
               lot_size=65, sell_price=90.5, buy_price=3.2, net_credit=87.3, stop_loss=132.3, target=None,
               exit_reason=None, exit_value=None)
    row.update(changes)
    return SimpleNamespace(**row)


def desk(mode='live', capital=120000, unlocked=True, account=None, **settings):
    store = Store({'strategies': {'zen_strategy_10': {'mode': mode, 'capital': capital, **settings}}, **(account or {})})
    broker, provider, sent = Broker(), Provider(), []
    clock = [0.0]
    made = LiveDesk(store, provider, broker_factory=lambda: broker,
                    notifier=SimpleNamespace(_send=lambda subject, body: sent.append((subject, body))),
                    env={'LIVE_TRADING_ENABLED': 'true'} if unlocked else {}, names={'zen_strategy_10': 'Momentum Afternoon Credit'},
                    sleeper=lambda seconds: clock.__setitem__(0, clock[0] + seconds), mono=lambda: clock[0])
    made.begin_round(NOW)
    return made, store, broker, provider, sent


def enter(made, row=None, now=NOW):
    made.step('zen_strategy_10', CFG, paper_view(row or paper_row(), entered=True), True, now)


def trade_of(store):
    return store.states['zen_strategy_10']['open_trade']


# ------------------------------------------------------------------ sizing and entry
def test_entry_buys_the_hedge_first_then_sells_the_short_leg_sized_by_deployed_capital():
    made, store, broker, _, sent = desk(capital=320000)
    enter(made, paper_row(lots=2))
    assert [(o['side'], o['security_id'], o['quantity']) for o in broker.placed] == [('BUY', '5002', 130), ('SELL', '5001', 130)]
    trade = trade_of(store)
    # 320,000 buys 5 lots of margin, but one stop may lose only 2.5% of the deployed capital: 8,000 / (45 x 65) = 2 lots
    assert (trade['state'], trade['lots'], trade['units'], trade['capital']) == ('open', 2, 130, 320000)
    assert trade['entry_credit'] == pytest.approx(90.0 - 3.5)             # sold at the bid, bought at the ask
    assert trade['entry_slippage'] == pytest.approx(87.3 - 86.5)          # versus the paper last-price credit
    assert broker.placed[0]['price'] == 4.5 and broker.placed[1]['price'] == 89.0   # marketable limits, never market
    assert 'entered' in sent[-1][0] and 'Momentum Afternoon Credit' in sent[-1][0]


def test_lots_follow_the_capital_the_owner_deploys():
    made, store, broker, _, _ = desk(capital=120000)
    enter(made)
    assert trade_of(store)['lots'] == 1                                   # 3,000 / 2,925: one lot
    plain = registry.apply_profile('zen_strategy_01')                     # no loss cap: margin alone decides
    assert plain.monday_capital_fraction == 0.8                           # and NOW is a Monday: 80% is deployed
    for capital, lots in ((120000, 1), (320000, 4)):                       # 58,500 a lot: 96,000 -> 1, 256,000 -> 4
        made, store, broker, _, _ = desk(capital=capital)
        made.step('zen_strategy_10', plain, paper_view(paper_row(), entered=True), True, NOW)
        assert trade_of(store)['lots'] == lots
    every_day = replace(plain, monday_capital_fraction=1.0)
    for capital, lots in ((120000, 2), (320000, 5)):
        made, store, broker, _, _ = desk(capital=capital)
        made.step('zen_strategy_10', every_day, paper_view(paper_row(), entered=True), True, NOW)
        assert trade_of(store)['lots'] == lots
    made, store, broker, _, _ = desk(capital=320000, max_lots=3)
    made.step('zen_strategy_10', every_day, paper_view(paper_row(), entered=True), True, NOW)
    assert trade_of(store)['lots'] == 3                                   # the owner's own ceiling


@pytest.mark.parametrize('change, reason', [
    (dict(capital=100000), 'deployed capital must be between'),
    (dict(capital=400000), 'deployed capital must be between'),
    (dict(account={'kill_switch': True}), 'kill switch'),
    (dict(unlocked=False), 'locked on the server'),
])
def test_entries_are_refused_before_any_order_is_sent(change, reason):
    made, store, broker, _, sent = desk(**change)
    enter(made)
    state = store.states['zen_strategy_10']
    assert broker.placed == [] and state['open_trade'] is None
    assert reason in state['skipped'][-1]['reason'] and state['totals']['live']['skipped'] == 1
    assert 'entry skipped' in sent[-1][0]


def test_entry_is_skipped_when_funds_are_short_or_the_spread_costs_too_much():
    made, store, broker, _, _ = desk()
    broker.balance = 50000.0
    enter(made)
    assert broker.placed == [] and 'funds: 50,000 available' in store.states['zen_strategy_10']['skipped'][-1]['reason']
    made, store, broker, provider, _ = desk()
    provider.book[SELL] = (86.0, 91.0, 90.5)                              # bid dropped 4 points below the paper price
    enter(made)
    assert broker.placed == [] and 'worse than the paper price' in store.states['zen_strategy_10']['skipped'][-1]['reason']


def test_the_short_leg_is_never_sold_below_the_slippage_cap():
    made, store, broker, provider, _ = desk()
    def moved(request, order_id):                                         # the bid falls away after the hedge is bought
        if request['side'] == 'SELL' and request['security_id'] == '5001':
            return OrderState(order_id, 'PENDING')
    broker.on_place = moved
    enter(made)
    shorts = [o for o in broker.placed if o['security_id'] == '5001']
    floor = tick(87.3 - 3.0 + 3.5, True)                                  # paper credit - cap + what the hedge cost
    assert [o['price'] for o in shorts] == [89.0, floor] and floor == 87.8
    assert len(broker.cancelled) == 2                                     # both resting orders were pulled
    # nothing sold, so the hedge was sold back and the entry is recorded as failed with its small cost
    assert broker.placed[-1]['side'] == 'SELL' and broker.placed[-1]['security_id'] == '5002'
    state = store.states['zen_strategy_10']
    failed = state['recent'][-1]
    assert state['open_trade'] is None and failed['state'] == 'failed' and failed['pnl'] == pytest.approx((3.0 - 3.5) * 65)
    assert broker.positions() == {}


def test_a_rejected_short_leg_unwinds_the_hedge_and_reports_the_brokers_reason():
    made, store, broker, _, sent = desk()
    def reject(request, order_id):
        if request['side'] == 'SELL' and request['security_id'] == '5001':
            raise BrokerRejected('DH-906 Insufficient margin')
    broker.on_place = reject
    enter(made)
    failed = store.states['zen_strategy_10']['recent'][-1]
    assert failed['state'] == 'failed' and 'Insufficient margin' in failed['exit_reason']
    assert store.states['zen_strategy_10']['totals']['live']['failed'] == 1 and broker.positions() == {}
    assert 'ENTRY FAILED' in sent[-1][0] and 'Insufficient margin' in sent[-1][1]


def test_a_partly_filled_short_leg_keeps_only_the_hedge_it_needs():
    made, store, broker, _, _ = desk(capital=320000)
    def partial(request, order_id):                                       # one lot trades, then the bid is gone
        if request['side'] == 'SELL' and request['security_id'] == '5001':
            first = not any(o['security_id'] == '5001' for o in broker.placed[:-1])
            return OrderState(order_id, 'PART_TRADED', 65, 90.0) if first else OrderState(order_id, 'PENDING')
    broker.on_place = partial
    enter(made)
    trade = trade_of(store)
    assert (trade['state'], trade['units'], trade['lots']) == ('open', 65, 1)
    assert [o['quantity'] for o in broker.placed if o['security_id'] == '5001'] == [130, 65]   # only the rest is retried
    assert broker.positions() == {'5001': -65, '5002': 65}                # the other 65 hedge units were sold back


# ------------------------------------------------------------------ restarts and outages
def test_an_order_whose_answer_was_lost_is_looked_up_and_never_sent_twice():
    made, store, broker, _, _ = desk()
    def lost(request, order_id):
        if request['side'] == 'SELL' and request['security_id'] == '5001':
            broker.orders[order_id] = OrderState(order_id, 'TRADED', request['quantity'], 90.0)
            broker.by_cid[request['cid']] = order_id
            broker.book['5001'] = -request['quantity']
            raise BrokerError('Dhan order connection failed (ReadTimeout)')
    broker.on_place = lost
    enter(made)
    trade = trade_of(store)
    assert trade['state'] == 'entering' and trade['legs']['short_entry']['orders'][-1]['order_id'] is None
    cid = trade['legs']['short_entry']['orders'][-1]['cid']
    assert cid == correlation('zen_strategy_10', 'sig-0001', 'short_entry', 0) and len(cid) <= 30
    # two strategies that open the same spread in the same minute share a signal id, never an order tag
    assert cid != correlation('zen_strategy_05', 'sig-0001', 'short_entry', 0)
    assert len(correlation('zen_strategy_10', 'f' * 20, 'hedge_unwind', 12)) <= 30
    # a new process picks the trade up from the stored state the next minute
    fresh = LiveDesk(store, Provider(), broker_factory=lambda: broker, env={'LIVE_TRADING_ENABLED': 'true'},
                     sleeper=lambda s: None, mono=lambda: 0.0)
    fresh.begin_round(NOW)
    broker.on_place = None
    fresh.step('zen_strategy_10', CFG, paper_view(paper_row()), True, NOW)
    trade = trade_of(store)
    assert trade['state'] == 'open' and trade['entry_credit'] == pytest.approx(86.5)
    assert len([o for o in broker.placed if o['security_id'] == '5001']) == 1     # not sent again


def test_an_order_that_never_reached_the_broker_ends_the_entry_cleanly():
    made, store, broker, _, _ = desk()
    def lost(request, order_id):
        if request['side'] == 'SELL' and request['security_id'] == '5001':
            raise BrokerError('Dhan order connection failed (ConnectTimeout)')
    broker.on_place = lost
    enter(made)
    broker.on_place = None
    made.begin_round(NOW)
    made.step('zen_strategy_10', CFG, paper_view(paper_row()), True, NOW)
    state = store.states['zen_strategy_10']
    assert state['open_trade'] is None and state['recent'][-1]['state'] == 'failed' and broker.positions() == {}
    # the same paper signal is not chased again a minute later
    made.step('zen_strategy_10', CFG, paper_view(paper_row(), entered=True), True, NOW)
    assert store.states['zen_strategy_10']['open_trade'] is None


def test_the_state_is_stored_before_each_order_is_sent():
    made, store, broker, _, _ = desk()
    seen = []
    def check(request, order_id):
        stored = store.states['zen_strategy_10']['open_trade']
        seen.append(any(order['cid'] == request['cid'] for leg in stored['legs'].values() for order in leg['orders']))
    broker.on_place = check
    enter(made)
    assert seen == [True, True]


# ------------------------------------------------------------------ exit
def open_trade(**kwargs):
    made, store, broker, provider, sent = desk(**kwargs)
    enter(made)
    return made, store, broker, provider, sent


def test_exit_buys_back_the_short_leg_first_and_records_slippage_against_paper():
    made, store, broker, provider, sent = open_trade()
    provider.book = {SELL: (131.0, 133.0, 132.5), BUY: (2.0, 2.4, 2.2)}
    closed = paper_row(exit_reason='Stop loss', exit_value=130.3)
    made.step('zen_strategy_10', CFG, paper_view(None, closed), True, NOW)
    assert [(o['side'], o['security_id']) for o in broker.placed[2:]] == [('BUY', '5001'), ('SELL', '5002')]
    state = store.states['zen_strategy_10']
    done = state['recent'][-1]
    assert state['open_trade'] is None and done['state'] == 'closed' and done['exit_reason'] == 'Stop loss'
    assert done['exit_value'] == pytest.approx(133.0 - 2.0)
    assert done['pnl'] == pytest.approx((86.5 - 131.0) * 65)
    assert done['exit_slippage'] == pytest.approx(131.0 - 130.3)
    totals = state['totals']['live']
    assert (totals['trades'], totals['winners'], totals['stop_trades']) == (1, 0, 1)
    assert totals['stop_slippage_points'] == pytest.approx(0.8 + 0.7)
    assert totals['slippage_rupees'] == pytest.approx(1.5 * 65)
    assert state['day'] == {'date': '2026-11-23', 'realized': done['pnl']}
    assert broker.positions() == {} and store.archived[-1]['signal_id'] == 'sig-0001'
    assert 'exited' in sent[-1][0] and 'Stop loss' in sent[-1][1]


def test_exit_widens_its_price_and_ends_in_a_market_order():
    made, store, broker, provider, _ = open_trade()
    def thin(request, order_id):                                          # nobody sells the short leg at a limit
        if request['side'] == 'BUY' and request['security_id'] == '5001' and request['price'] is not None:
            return OrderState(order_id, 'PENDING')
        if request['side'] == 'BUY' and request['security_id'] == '5001':
            return OrderState(order_id, 'TRADED', request['quantity'], 99.0)
    broker.on_place = thin
    made.step('zen_strategy_10', CFG, paper_view(None), True, NOW)
    buys = [o['price'] for o in broker.placed if o['side'] == 'BUY' and o['security_id'] == '5001']
    assert buys == [92.0, 94.0, 97.0, None]
    done = store.states['zen_strategy_10']['recent'][-1]
    assert done['state'] == 'closed' and done['exit_reason'] == 'Paper position closed'   # the exit minute was missed
    assert done['pnl'] == pytest.approx((90.0 - 3.5 - 99.0 + 3.0) * 65)


def test_an_exit_that_cannot_be_sent_is_retried_every_minute_and_alerts():
    made, store, broker, provider, sent = open_trade()
    def down(request, order_id):
        raise BrokerRejected('DH-905 exchange not reachable')
    broker.on_place = down
    made.step('zen_strategy_10', CFG, paper_view(None), True, NOW)
    trade = trade_of(store)
    assert trade['state'] == 'exiting' and trade['exit_minutes'] == 1
    assert 'EXIT NOT FILLED' in sent[-1][0] and 'exchange not reachable' in sent[-1][1]
    broker.on_place = None
    made.begin_round(NOW)
    made.step('zen_strategy_10', CFG, None, True, NOW)                    # even a cycle that evaluated nothing
    assert store.states['zen_strategy_10']['open_trade'] is None and broker.positions() == {}


def test_a_held_position_is_left_alone_and_a_cycle_without_a_view_changes_nothing():
    made, store, broker, _, _ = open_trade()
    orders = len(broker.placed)
    made.step('zen_strategy_10', CFG, paper_view(paper_row()), True, NOW)
    made.step('zen_strategy_10', CFG, None, True, NOW)                    # data error: the paper position is unknown
    made.step('zen_strategy_10', CFG, None, False, NOW)
    assert len(broker.placed) == orders and trade_of(store)['state'] == 'open'


def test_the_owner_can_exit_a_live_trade_while_the_paper_position_stays():
    made, store, broker, _, _ = open_trade()
    store.account_doc['strategies']['zen_strategy_10']['exit_now'] = '2026-11-23T12:20:00+05:30'
    made.begin_round(NOW)
    made.step('zen_strategy_10', CFG, paper_view(paper_row()), True, NOW)
    done = store.states['zen_strategy_10']['recent'][-1]
    assert done['exit_reason'] == 'Exit requested' and broker.positions() == {}
    # the paper position is still open; the desk stays flat until the next paper entry
    made.step('zen_strategy_10', CFG, paper_view(paper_row()), True, NOW)
    assert store.states['zen_strategy_10']['open_trade'] is None


def test_a_disabled_strategy_gets_its_live_trade_closed_when_paper_is_flat():
    from paper_worker import run_round
    made, store, broker, _, _ = open_trade()
    runner = SimpleNamespace(live=made, store=SimpleNamespace(open_position_row=lambda: None))
    run_round({'zen_strategy_10': runner}, {'zen_strategy_10': {'enabled': False}}, NOW)
    assert store.states['zen_strategy_10']['open_trade'] is None and broker.positions() == {}


def test_a_hedge_nobody_bids_for_is_left_to_expire_after_three_minutes():
    made, store, broker, provider, _ = open_trade()
    def no_bid(request, order_id):
        if request['side'] == 'SELL' and request['security_id'] == '5002':
            return OrderState(order_id, 'PENDING')
    broker.on_place = no_bid
    for _ in range(3):
        made.begin_round(NOW)
        made.step('zen_strategy_10', CFG, paper_view(None), True, NOW)
    state = store.states['zen_strategy_10']
    assert state['open_trade'] is None and state['residuals'] == {'5002': {'qty': 65, 'expiry': '2026-11-24'}}
    assert 'left to expire' in state['recent'][-1]['notes'][-1]
    made.end_round(NOW)
    made.end_round(NOW)
    assert made.mismatch is None                                          # the leftover long option is expected at the broker


def test_an_expired_trade_is_settled_at_intrinsic_value_without_orders():
    made, store, broker, provider, _ = open_trade()
    orders = len(broker.placed)
    provider.settlement = SimpleNamespace(spot=23950.0)
    later = datetime(2026, 11, 25, 9, 20, tzinfo=IST)
    made.begin_round(later)
    made.step('zen_strategy_10', CFG, paper_view(paper_row()), True, later)   # the paper account has not closed it yet
    done = store.states['zen_strategy_10']['recent'][-1]
    assert len(broker.placed) == orders and done['exit_reason'] == 'Expiry'
    assert done['exit_value'] == pytest.approx(50.0) and done['pnl'] == pytest.approx((86.5 - 50.0) * 65)


# ------------------------------------------------------------------ account safety
def test_a_broker_position_mismatch_blocks_new_entries_until_it_clears():
    made, store, broker, _, sent = open_trade()
    made.end_round(NOW)
    assert made.mismatch is None and store.desk['live_unlocked'] is True
    # another algo in the same Dhan account holds the same two contracts: more of each is not a mismatch
    broker.book.update({'5001': -65 - 325, '5002': 65 + 325})
    made.end_round(NOW)
    made.end_round(NOW)
    assert made.mismatch is None
    broker.book['5001'] = 0                                               # the short leg was closed outside the desk
    made.end_round(NOW)
    assert made.mismatch is None                                          # one round of grace for a trailing position book
    made.end_round(NOW)
    assert 'security 5001: desk -65, broker 0' in made.mismatch
    assert 'BROKER POSITIONS DO NOT MATCH' in sent[-1][0] and store.desk['mismatch'] == made.mismatch
    made.states['zen_strategy_10']['open_trade'] = None                   # that trade is dealt with by hand
    enter(made, paper_row('sig-0002'))
    assert 'do not match' in store.states['zen_strategy_10']['skipped'][-1]['reason']


def test_the_daily_loss_limit_stops_new_entries_for_the_day():
    made, store, broker, provider, _ = open_trade(account={'daily_loss_limit': 2000})
    provider.book = {SELL: (131.0, 133.0, 132.5), BUY: (2.0, 2.4, 2.2)}
    made.step('zen_strategy_10', CFG, paper_view(None), True, NOW)        # loses about 2,900
    provider.book = {SELL: (90.0, 91.0, 90.5), BUY: (3.0, 3.5, 3.2)}
    enter(made, paper_row('sig-0002'))
    assert 'daily loss limit reached' in store.states['zen_strategy_10']['skipped'][-1]['reason']
    tomorrow = datetime(2026, 11, 24, 12, 15, tzinfo=IST)
    made.begin_round(tomorrow)
    enter(made, paper_row('sig-0003'), tomorrow)
    assert trade_of(store)['signal_id'] == 'sig-0003'


def test_a_strategy_the_owner_never_configured_costs_no_read_and_no_order():
    store = Store({'strategies': {}})
    broker = Broker()
    made = LiveDesk(store, Provider(), broker_factory=lambda: broker, env={'LIVE_TRADING_ENABLED': 'true'})
    made.begin_round(NOW)
    made.step('zen_strategy_05', CFG, paper_view(paper_row(), entered=True), True, NOW)
    made.end_round(NOW)
    assert (store.state_reads, store.saves, broker.placed, store.desk) == (0, 0, [], None)
    assert made.has_trade('zen_strategy_05') is False


def test_switched_off_with_a_trade_open_still_manages_the_exit():
    made, store, broker, _, _ = open_trade()
    store.account_doc['strategies']['zen_strategy_10']['mode'] = 'off'
    made.begin_round(NOW)
    made.step('zen_strategy_10', CFG, paper_view(None), True, NOW)
    assert store.states['zen_strategy_10']['open_trade'] is None and broker.positions() == {}
    made.step('zen_strategy_10', CFG, paper_view(paper_row('sig-0002'), entered=True), True, NOW)
    assert store.states['zen_strategy_10']['open_trade'] is None          # and takes no new one


def test_the_heartbeat_previews_the_lots_each_configured_strategy_would_trade():
    made, store, _, provider, _ = desk(capital=320000)
    provider.get_expiries = lambda: [EXPIRY]
    provider.get_lot_size = lambda expiry: 65
    made.step('zen_strategy_10', CFG, paper_view(None), True, NOW)
    made.step('zen_strategy_01', replace(registry.apply_profile('zen_strategy_01'), capital=320000), paper_view(None), True, NOW)
    store.account_doc['strategies']['zen_strategy_01'] = {'mode': 'dry_run', 'capital': 120000}
    made.begin_round(NOW)
    made.end_round(NOW)
    # capped at a 2.5% loss per stop: 2 lots every day; margin only: 2 lots, 1 on expiry day (90,090 a lot) and 1 on a
    # Monday, when both profiles deploy 80% of the capital
    assert store.desk['sizing'] == {'zen_strategy_10': {'lot_size': 65, 'normal': 2, 'expiry_day': 2, 'monday': 2},
                                    'zen_strategy_01': {'lot_size': 65, 'normal': 2, 'expiry_day': 1, 'monday': 1}}


# ------------------------------------------------------------------ dry run
def test_dry_run_fills_at_the_bid_and_ask_and_never_builds_a_broker():
    store = Store({'strategies': {'zen_strategy_10': {'mode': 'dry_run', 'capital': 120000}}})
    def no_broker():
        raise AssertionError('a dry run must not construct the real broker')
    made = LiveDesk(store, Provider(), broker_factory=no_broker, env={}, sleeper=lambda s: None, mono=lambda: 0.0)
    made.begin_round(NOW)
    enter(made)
    trade = trade_of(store)
    assert (trade['mode'], trade['state'], trade['entry_credit']) == ('dry_run', 'open', pytest.approx(86.5))
    made.step('zen_strategy_10', CFG, paper_view(None, paper_row(exit_reason='Time exit', exit_value=87.3)), True, NOW)
    state = store.states['zen_strategy_10']
    assert state['recent'][-1]['pnl'] == pytest.approx((86.5 - (91.0 - 3.0)) * 65)
    assert state['totals']['dry_run']['trades'] == 1 and 'live' not in state['totals'] and state['day'] is None
    made.end_round(NOW)
    assert made.mismatch is None


def test_as_shipped_no_order_can_reach_dhan():
    assert broker_module.LIVE_ORDERS is False
    # the real client cannot be built, with or without credentials, and cannot place even if it were
    with pytest.raises(BrokerError, match='switched off'):
        DhanBroker(session=SimpleNamespace(), auth=SimpleNamespace(client_id='1', token=lambda: 't'))
    orphan = object.__new__(DhanBroker)
    with pytest.raises(BrokerRejected, match='switched off'):
        orphan.place(correlation_id='c', side='BUY', security_id='1', quantity=65, price=1.0)
    # a strategy stored as live, on a server with the environment switch on, is treated as off
    def no_broker():
        raise AssertionError('the real broker must never be constructed')
    store = Store({'strategies': {'zen_strategy_10': {'mode': 'live', 'capital': 320000}}})
    made = LiveDesk(store, Provider(), broker_factory=no_broker, env={'LIVE_TRADING_ENABLED': 'true'},
                    sleeper=lambda s: None, mono=lambda: 0.0)
    made.begin_round(NOW)
    assert made.unlocked is False and made.settings('zen_strategy_10')['mode'] == 'off'
    enter(made)
    made.end_round(NOW)
    assert store.states == {} and store.saves == 0 and store.desk is None      # nothing was even recorded
    with pytest.raises(BrokerError):
        made.broker('live')


def test_as_shipped_dry_run_works_and_sends_nothing():
    store = Store({'strategies': {'zen_strategy_10': {'mode': 'dry_run', 'capital': 120000}}})
    made = LiveDesk(store, Provider(), env={'LIVE_TRADING_ENABLED': 'true'}, sleeper=lambda s: None, mono=lambda: 0.0)
    made.begin_round(NOW)
    enter(made)
    assert trade_of(store)['mode'] == 'dry_run' and trade_of(store)['state'] == 'open'
    made.step('zen_strategy_10', CFG, paper_view(None), True, NOW)
    made.end_round(NOW)
    assert store.states['zen_strategy_10']['recent'][-1]['state'] == 'closed' and made._live_broker is None
    assert store.desk['live_orders_built_in'] is False and store.desk['live_unlocked'] is False


def test_the_broker_client_cannot_reach_account_wide_controls():
    # Dhan's kill switch, P&L exit and exit-all-positions act on the whole account, including algos run
    # from Dhan's portal. The client has no method for them and its source names no such endpoint.
    import inspect
    import execution.broker as module
    source = inspect.getsource(module).lower()
    assert 'killswitch' not in source and 'pnlexit' not in source
    assert "'delete', '/positions'" not in source and '"delete", "/positions"' not in source
    assert sorted(name for name in vars(DhanBroker) if not name.startswith('_')) == [
        'BASE', 'MIN_GAP_SECONDS', 'available_balance', 'cancel', 'order', 'order_by_correlation', 'place', 'positions']


# ------------------------------------------------------------------ broker client
class Http:
    def __init__(self, answers):
        self.answers, self.calls = list(answers), []

    def request(self, method, url, headers=None, json=None, timeout=None):
        self.calls.append((method, url.replace(DhanBroker.BASE, ''), json, headers))
        status, body = self.answers.pop(0)
        return SimpleNamespace(status_code=status, content=b'x', json=lambda: body)


def dhan(answers):
    auth = SimpleNamespace(client_id='1100000000', token=lambda: 'tok', rejected=lambda token: True)
    http = Http(answers)
    return DhanBroker(session=http, auth=auth, sleeper=lambda s: None), http


def test_dhan_order_request_and_statuses():
    broker, http = dhan([(200, {'orderId': '77', 'orderStatus': 'PENDING'}),
                         (200, {'orderId': '77', 'orderStatus': 'TRADED', 'filledQty': 65, 'averageTradedPrice': 90.0})])
    placed = broker.place(correlation_id='Lsig-SE0', side='SELL', security_id='5001', quantity=65, price=89.0)
    method, path, body, headers = http.calls[0]
    assert (method, path) == ('POST', '/orders') and headers['access-token'] == 'tok'
    assert body == {'dhanClientId': '1100000000', 'correlationId': 'Lsig-SE0', 'transactionType': 'SELL',
                    'exchangeSegment': 'NSE_FNO', 'productType': 'MARGIN', 'orderType': 'LIMIT', 'validity': 'DAY',
                    'securityId': '5001', 'quantity': 65, 'disclosedQuantity': 0, 'price': 89.0, 'triggerPrice': 0,
                    'afterMarketOrder': False}
    assert (placed.order_id, placed.final) == ('77', False)
    done = broker.order('77')
    assert (done.status, done.filled_qty, done.avg_price, done.final) == ('TRADED', 65, 90.0, True)


def test_dhan_refusals_are_rejections_and_silence_is_unknown():
    broker, _ = dhan([(400, {'errorType': 'Order_Error', 'errorCode': 'DH-906', 'errorMessage': 'IP not whitelisted'})])
    with pytest.raises(BrokerRejected, match='DH-906 IP not whitelisted'):
        broker.place(correlation_id='c', side='BUY', security_id='1', quantity=65, price=None)
    broker, http = dhan([(502, {})])
    with pytest.raises(BrokerError) as caught:
        broker.place(correlation_id='c', side='BUY', security_id='1', quantity=65, price=None)
    assert not isinstance(caught.value, BrokerRejected) and len(http.calls) == 1      # an order is never re-sent blindly
    assert http.calls[0][2]['orderType'] == 'MARKET'


def test_dhan_expired_token_is_renewed_once_before_the_order_is_placed():
    broker, http = dhan([(401, {}), (200, {'orderId': '9', 'orderStatus': 'TRANSIT'})])
    assert broker.place(correlation_id='c', side='BUY', security_id='1', quantity=65, price=1.0).order_id == '9'
    assert len(http.calls) == 2


def test_dhan_correlation_lookup_confirms_a_miss_against_the_order_book():
    broker, _ = dhan([(404, {'errorCode': 'DH-907'}), (200, [{'orderId': '5', 'correlationId': 'abc', 'orderStatus': 'TRADED',
                                                              'filledQty': 65, 'averageTradedPrice': 3.5}])])
    assert broker.order_by_correlation('abc').order_id == '5'
    broker, _ = dhan([(404, {}), (200, [{'orderId': '6', 'correlationId': 'other', 'orderStatus': 'TRADED'}])])
    assert broker.order_by_correlation('abc') is None
    broker, _ = dhan([(404, {}), (500, {})])
    with pytest.raises(BrokerError):
        broker.order_by_correlation('abc')


def test_dhan_positions_and_funds():
    broker, _ = dhan([(200, [{'exchangeSegment': 'NSE_FNO', 'securityId': '5001', 'netQty': -65},
                             {'exchangeSegment': 'NSE_FNO', 'securityId': '5002', 'netQty': 65},
                             {'exchangeSegment': 'NSE_FNO', 'securityId': '5003', 'netQty': 0},
                             {'exchangeSegment': 'NSE_EQ', 'securityId': '1333', 'netQty': 10}]),
                      (200, {'availabelBalance': 98440.0})])
    assert broker.positions() == {'5001': -65, '5002': 65}
    assert broker.available_balance() == 98440.0


def test_sim_broker_rests_an_order_that_does_not_cross():
    sim = SimBroker()
    resting = sim.place(correlation_id='a', side='SELL', security_id='1', quantity=65, price=95.0, market={'bid': 90.0, 'ask': 91.0})
    assert resting.status == 'PENDING'
    sim.cancel(resting.order_id)
    assert sim.order_by_correlation('a').status == 'CANCELLED' and sim.order_by_correlation('zz') is None


# ------------------------------------------------------------------ runner hook
def test_the_runner_tells_the_desk_what_the_paper_account_holds():
    import main
    from strategy.engine import EngineResult, ExitEvent

    class PaperStore:
        def __init__(self):
            self.row = None
        def open_position_row(self): return self.row
        def insert_position(self, position, direction):
            self.row = paper_row(position.signal_id, id=1, entry_ts=NOW, exit_due=NOW, units=130, max_loss=0, max_profit=0,
                                 spot_at_entry=24050.0, alpha=None, alpha2=None, allocated_capital=320000.0)
            return self.row
        def close_position(self, row_id, event):
            closed, self.row = self.row, None
            closed.exit_reason, closed.exit_value = event.reason, event.exit_value
            return closed
        def set_state(self, key, value): pass
        def get_state(self, key): return None
        def claim_minute(self, minute): return True
        def finish_minute(self, *args): pass
        def pending_emails(self, attempts): return []
        def load_snapshots(self, since): return __import__('pandas').DataFrame()
        def save_snapshot_rows(self, rows): pass
        @contextmanager
        def session(self): yield self
        @contextmanager
        def lock(self): yield True

    steps = []
    cfg = main.Config()
    cfg = main.replace(cfg, runtime=main.replace(cfg.runtime, strategy_name='zen_strategy_10'))
    provider = SimpleNamespace(get_expiries=lambda: [EXPIRY], get_option_chain=Provider().get_option_chain,
                               get_lot_size=lambda expiry: 65, get_spot_bars=lambda now: None,
                               get_expiry_settlement=lambda expiry: None)
    calendar = SimpleNamespace(is_trading_day=lambda day: True, next_trading_day=lambda day: day)
    runner = main.Runner(cfg, PaperStore(), provider, calendar, SimpleNamespace(send_entry=None, send_exit=None))
    runner.session = SimpleNamespace(check=lambda now: SimpleNamespace(is_open=True, reason='', state=SimpleNamespace(value='OPEN')))
    runner.live = SimpleNamespace(step=lambda *args: steps.append(args))
    position = SimpleNamespace(signal_id='sig-0009')
    runner.engine = SimpleNamespace(strategy_name='zen_strategy_10', note_exit=lambda *a: None, _stale=lambda *a: True,
                                    evaluate=lambda view, held: EngineResult('entry', 'BULLISH', position=position))
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(main, 'row_to_position', lambda row: row)
        patch.setenv('PAPER_FIREBASE_ENABLED', 'false')
        assert runner.locked_cycle(NOW)['status'] == 'entry'
        name, strategy, view, market_open, now = steps[-1]
        assert (name, strategy, market_open, now) == ('zen_strategy_10', runner.cfg.strategy, True, NOW)
        assert view['entered'] is True and view['open'].signal_id == 'sig-0009' and view['closed'] is None
        runner.engine.evaluate = lambda view, held: EngineResult('none', 'position held')
        runner.locked_cycle(NOW.replace(minute=16))
        assert steps[-1][2]['entered'] is False and steps[-1][2]['open'].signal_id == 'sig-0009'
        event = ExitEvent('Stop loss', NOW, 130.3, -5590.0, -1.75)
        runner.engine.evaluate = lambda view, held: EngineResult('exit', 'Stop loss', exit=event)
        runner.locked_cycle(NOW.replace(minute=17))
        view = steps[-1][2]
        assert view['open'] is None and (view['closed'].exit_reason, view['closed'].exit_value) == ('Stop loss', 130.3)
        runner.session = SimpleNamespace(check=lambda now: SimpleNamespace(is_open=False, reason='closed', state=SimpleNamespace(value='CLOSED')))
        runner.locked_cycle(NOW.replace(hour=16))
        assert steps[-1][2] is None and steps[-1][3] is False              # closed market: nothing is known, nothing is sent
        runner.live = SimpleNamespace(step=lambda *args: 1 / 0)             # a desk failure never fails the paper cycle
        runner.session = SimpleNamespace(check=lambda now: SimpleNamespace(is_open=True, reason='', state=SimpleNamespace(value='OPEN')))
        runner.engine.evaluate = lambda view, held: EngineResult('none', 'no signal')
        assert runner.locked_cycle(NOW.replace(minute=30))['status'] == 'no_action'
