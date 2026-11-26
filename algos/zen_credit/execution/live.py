"""Live order desk: mirrors a strategy's paper position with real Dhan orders.

The paper engine stays the only decision maker. When it opens a position this desk opens the same spread
at the owner's deployed capital, and when the paper position is gone (stop, target, time exit, or the
owner asks) it closes it. Nothing here changes a signal, a stop or the paper ledger.

What it handles that the paper account assumes away:

- Fills. Orders are marketable limits against the live bid/ask. An entry is skipped when the spread would
  cost more than ``slippage_cap`` points versus the paper price; an exit is never skipped and widens its
  price each attempt, ending in a market order. Every fill is recorded next to the paper price, so
  slippage is measured per trade, stops included.
- Two legs. The hedge is bought first and the short leg sold only against what filled. A short leg that
  does not fill has its hedge sold back. On exit the short leg is bought back first.
- Rejections and margin. Funds are checked against the estimated margin before the first order; a
  rejection ends the entry and is reported with the broker's reason.
- Restarts and outages. The trade and every order's correlation id are stored before the request is
  sent, so a timeout or restart resumes from the broker's own record instead of ordering twice. Exits
  are level-triggered: a live trade without its paper position is closed on the next cycle, however
  the exit minute was missed.
- The account. Each round checks that the broker still holds at least what the desk's trades need; a
  shortfall blocks new entries and alerts the owner. A kill switch and a daily loss limit also block
  entries. Both are this desk's own flags.
- Other trading in the same account. The desk only ever places, reads and cancels its own orders (each
  carries its own tag) and only exits its own quantities. It never calls Dhan's kill switch, P&L exit or
  exit-all-positions APIs, so algos run from Dhan's portal and manual trades are not touched. They do
  share the account's funds.

Modes per strategy (Firestore ``algo_live/account``, written by the owner API): ``off``, ``dry_run``
(same flow against a simulated broker that fills at the bid/ask) and ``live``. ``live`` additionally
needs LIVE_TRADING_ENABLED=true in the server environment.

Live trading is currently switched off in the code (``execution.broker.LIVE_ORDERS`` is False): a
stored ``live`` mode is treated as ``off`` and the real broker cannot be built, so only paper and dry
run exist and no request that could place an order is ever made.

State: ``algo_live_state/{strategy}`` (open trade, totals, recent trades), read only for strategies the
owner configured and only when there is something to act on.
"""
from __future__ import annotations

import logging
import math
import os
import time
import zlib
from dataclasses import replace
from datetime import date, datetime, timedelta

import execution.broker as broker_module
from execution.broker import BrokerError, BrokerRejected, SimBroker
from risk.position_sizing import build_risk_plan
from utils.time import now_ist, to_ist

log = logging.getLogger('paper.live')

MIN_CAPITAL, MAX_CAPITAL = 120_000.0, 320_000.0
MODES = ('off', 'dry_run', 'live')
TICK = 0.05
FREEZE_UNITS = 1800                 # NSE quantity freeze for NIFTY options; above it one order is refused
DEFAULT_SLIPPAGE_CAP = 3.0          # points of entry credit given up before the entry is skipped
HEDGE_GIVE_UP_MINUTES = 3           # a hedge leg nobody bids for is left to expire after this many tries
KEEP = 30                           # recent trades / skips / alerts kept in the state document
LEG_CODES = {'hedge_entry': 'HE', 'short_entry': 'SE', 'hedge_unwind': 'HU', 'short_exit': 'SX', 'hedge_exit': 'HX'}
EMPTY_TOTALS = {'trades': 0, 'winners': 0, 'realized_pnl': 0.0, 'entry_slippage_points': 0.0,
                'exit_slippage_points': 0.0, 'slippage_rupees': 0.0, 'stop_trades': 0,
                'stop_slippage_points': 0.0, 'failed': 0, 'skipped': 0}


def iso(moment: datetime) -> str:
    return to_ist(moment).isoformat()


def tick(price: float, up: bool) -> float:
    steps = price / TICK
    steps = math.ceil(steps - 1e-9) if up else math.floor(steps + 1e-9)
    return max(TICK, round(steps * TICK, 2))


def touch(quote: dict | None, side: str):
    """The price a marketable order meets: the ask for a BUY, the bid for a SELL; last price if absent."""
    if not quote:
        return None
    value = quote.get('ask' if side == 'BUY' else 'bid')
    return value if value is not None else quote.get('ltp')


def new_leg(side: str, security_id: str, qty: int) -> dict:
    return {'side': side, 'security_id': str(security_id), 'qty': int(qty), 'filled': 0, 'avg': None, 'orders': []}


def correlation(strategy: str, signal_id: str, leg: str, attempt: int) -> str:
    """Order tag, unique per strategy, signal, leg and attempt (Dhan allows 30 characters). Two strategies
    can open the same spread in the same minute and so share a signal id; the strategy prefix keeps one
    from ever reading the other's order."""
    return f'L{zlib.crc32(strategy.encode()) & 0xffff:04x}{signal_id[:14]}-{LEG_CODES[leg]}{attempt}'


def is_long_option(paper) -> bool:
    """A paper row for one bought option (see strategy.engine.Position.structure) rather than a credit spread."""
    return getattr(paper, 'structure', None) == 'long_option'


def buys_options(strategy: str) -> bool:
    from strategy.registry import get_strategy
    try:
        return getattr(get_strategy(strategy), 'STRUCTURE', 'credit_spread') == 'long_option'
    except ValueError:
        return False


def premium_fraction(strategy: str) -> float:
    """Share of the deployed capital an option-buying strategy spends on premium per trade."""
    from strategy.registry import get_strategy
    return float(getattr(get_strategy(strategy), 'PREMIUM_FRACTION', 0.15))


def trade_cash(trade: dict) -> float:
    """Rupees received minus rupees paid across every fill of the trade."""
    cash = 0.0
    for leg in trade['legs'].values():
        if leg['filled'] and leg['avg'] is not None:
            cash += (1 if leg['side'] == 'SELL' else -1) * leg['filled'] * leg['avg']
    return round(cash, 2)


def net_holdings(trade: dict) -> dict[str, int]:
    """Net quantity this trade should show at the broker, by security id."""
    net: dict[str, int] = {}
    for leg in trade['legs'].values():
        if leg['orders'] or leg.get('counts'):
            net[leg['security_id']] = net.get(leg['security_id'], 0) + (1 if leg['side'] == 'BUY' else -1) * leg['filled']
    return net


def intrinsic(option_type: str, strike: float, spot: float) -> float:
    return round(max(spot - strike, 0.0) if option_type == 'CE' else max(strike - spot, 0.0), 2)


class LiveStore:
    """Firestore documents of the desk. The account document belongs to the owner API; the desk only reads it."""

    def __init__(self, db):
        self.db = db

    def account(self) -> dict:
        snap = self.db.collection('algo_live').document('account').get(timeout=10)
        return snap.to_dict() or {} if snap.exists else {}

    def state(self, name: str) -> dict | None:
        snap = self.db.collection('algo_live_state').document(name).get(timeout=10)
        return snap.to_dict() if snap.exists else None

    def save_state(self, name: str, state: dict) -> None:
        self.db.collection('algo_live_state').document(name).set(state, timeout=10)

    def archive(self, name: str, trade: dict) -> None:
        key = f"{trade['signal_id']}_{trade['mode']}"
        self.db.collection('algo_live_state').document(name).collection('trades').document(key).set(trade, timeout=10)

    def save_desk(self, payload: dict) -> None:
        self.db.collection('algo_live_state').document('_desk').set(payload, timeout=10)


class LiveDesk:
    def __init__(self, store, provider, broker_factory=None, notifier=None, env=None, names=None,
                 sleeper=time.sleep, mono=time.monotonic, fill_wait=4.0, poll_seconds=1.0, budget_seconds=25.0):
        self.store, self.provider, self.notifier = store, provider, notifier
        self.env = os.environ if env is None else env
        self.names = names or {}
        self.sleep, self.mono = sleeper, mono
        self.fill_wait, self.poll_seconds, self.budget_seconds = fill_wait, poll_seconds, budget_seconds
        self._broker_factory = broker_factory
        self._live_broker = None
        self._sim = SimBroker()
        self.account: dict | None = None        # this round's settings; None when they could not be read
        self.states: dict[str, dict] = {}
        self.cfgs: dict[str, object] = {}       # each stepped strategy's profile, for the sizing preview
        self.touched: set[str] = set()
        self.mismatch: str | None = None
        self._mismatch_rounds = 0
        self.broker_error: str | None = None

    # ------------------------------------------------------------------ settings
    @property
    def unlocked(self) -> bool:
        return bool(broker_module.LIVE_ORDERS) and str(self.env.get('LIVE_TRADING_ENABLED', '')).strip().lower() == 'true'

    def configured(self, name: str) -> bool:
        return name in ((self.account or {}).get('strategies') or {})

    def settings(self, name: str) -> dict:
        raw = ((self.account or {}).get('strategies') or {}).get(name) or {}
        mode = raw.get('mode') if raw.get('mode') in MODES else 'off'
        if mode == 'live' and not broker_module.LIVE_ORDERS:
            mode = 'off'                    # live trading is switched off in the code
        try:
            capital = float(raw.get('capital') or 0.0)
        except (TypeError, ValueError):
            capital = 0.0
        try:
            cap = float(raw.get('slippage_cap')) if raw.get('slippage_cap') is not None else DEFAULT_SLIPPAGE_CAP
        except (TypeError, ValueError):
            cap = DEFAULT_SLIPPAGE_CAP
        max_lots = raw.get('max_lots')
        return {'mode': mode, 'capital': capital, 'slippage_cap': max(0.0, cap),
                'max_lots': int(max_lots) if isinstance(max_lots, (int, float)) and max_lots >= 1 else None,
                'exit_now': raw.get('exit_now')}

    def broker(self, mode: str):
        if mode != 'live':
            return self._sim
        if not self.unlocked:
            raise BrokerError('live trading is locked on the server (LIVE_TRADING_ENABLED)')
        if self._live_broker is None:
            if self._broker_factory is None:
                from execution.broker import DhanBroker
                self._broker_factory = DhanBroker
            self._live_broker = self._broker_factory()
        return self._live_broker

    def label(self, name: str) -> str:
        return self.names.get(name) or 'Algo'

    # ------------------------------------------------------------------ state
    def _blank(self) -> dict:
        return {'open_trade': None, 'totals': {}, 'day': None, 'recent': [], 'skipped': [], 'alerts': [],
                'residuals': {}, 'updated_at': None}

    def _load(self, name: str, fresh: bool) -> dict | None:
        """Cached state, read again when something is about to be acted on. None: never configured."""
        cached = self.states.get(name)
        if cached is not None and not fresh:
            return cached
        if cached is None and not self.configured(name):
            return None
        try:
            found = self.store.state(name)
        except Exception as exc:
            log.warning('live_state_read_failed strategy=%s error=%s', name, type(exc).__name__)
            return cached
        state = {**self._blank(), **(found or {})}
        self.states[name] = state
        return state

    def _save(self, name: str, state: dict, now: datetime | None = None) -> None:
        state['updated_at'] = iso(now or now_ist())
        self.store.save_state(name, state)

    def has_trade(self, name: str) -> bool:
        state = self._load(name, fresh=False)
        return bool(state and state.get('open_trade'))

    def _alert(self, name: str, state: dict | None, subject: str, body: str = '', now: datetime | None = None) -> None:
        title = f'{self.label(name)}: {subject}'
        log.warning('live_alert strategy=%s subject=%s detail=%s', name, subject, body or '-')
        if state is not None:
            state['alerts'] = (state.get('alerts') or [])[-(KEEP - 1):] + [
                {'at': iso(now or now_ist()), 'subject': subject, 'detail': body[:300]}]
        if self.notifier is not None:
            try:
                self.notifier._send(f'Algo Lab live | {title}', body or subject)
            except Exception as exc:  # an alert must never stop an order being managed
                log.warning('live_alert_email_failed error=%s', type(exc).__name__)

    # ------------------------------------------------------------------ round
    def begin_round(self, now: datetime) -> None:
        self.touched = set()
        try:
            self.account = self.store.account() or {}
        except Exception as exc:
            self.account = None
            log.warning('live_settings_unavailable error=%s', type(exc).__name__)

    def end_round(self, now: datetime) -> None:
        """Finish trades whose strategy did not run this round, reconcile with the broker, publish the heartbeat."""
        market_open = now.weekday() < 5 and (9, 15) <= (now.hour, now.minute) < (15, 30)
        for name, state in list(self.states.items()):
            if name not in self.touched and state.get('open_trade'):
                self.step(name, None, None, market_open, now)
        self._reconcile(now)
        active = any(self.settings(name)['mode'] != 'off' for name in ((self.account or {}).get('strategies') or {}))
        if active or any(state.get('open_trade') for state in self.states.values()):
            try:
                self.store.save_desk({'at': iso(now), 'live_unlocked': self.unlocked, 'mismatch': self.mismatch,
                                      'live_orders_built_in': bool(broker_module.LIVE_ORDERS),
                                      'broker_error': self.broker_error, 'sizing': self._sizing(now),
                                      'kill_switch': bool((self.account or {}).get('kill_switch')),
                                      'settings_readable': self.account is not None})
            except Exception as exc:
                log.warning('live_heartbeat_failed error=%s', type(exc).__name__)

    def _sizing(self, now: datetime) -> dict:
        """Lots each configured strategy would trade at its deployed capital, for the owner's page."""
        try:
            ahead = [expiry for expiry in self.provider.get_expiries() if expiry >= now.date()]
            lot_size = int(self.provider.get_lot_size(min(ahead)))
        except Exception:
            return {}
        monday = now.date() + timedelta(days=(7 - now.weekday()) % 7 or 7)
        preview = {}
        for name, cfg in self.cfgs.items():
            settings = self.settings(name)
            if settings['mode'] == 'off' or not MIN_CAPITAL <= settings['capital'] <= MAX_CAPITAL:
                continue
            if buys_options(name):
                # Lots depend on the option's price at the entry; show the premium the strategy may spend instead.
                preview[name] = {'lot_size': lot_size, 'premium_budget': round(settings['capital'] * premium_fraction(name)),
                                 'normal': None, 'expiry_day': None, 'monday': None}
                continue

            def lots(day, expiry_day):
                plan = build_risk_plan(100.0, 10.0, float(cfg.spread_distance), lot_size, expiry_day,
                                       replace(cfg, capital=settings['capital']), day)
                return min(plan.lots, settings['max_lots']) if settings['max_lots'] else plan.lots
            try:
                preview[name] = {'lot_size': lot_size, 'normal': lots(monday + timedelta(days=1), False),
                                 'expiry_day': lots(monday + timedelta(days=1), True),
                                 'monday': lots(monday, False) if cfg.monday_capital_fraction < 1 else None}
            except ValueError:
                continue
        return preview

    # ------------------------------------------------------------------ one strategy
    def step(self, name: str, strategy_cfg, view: dict | None, market_open: bool, now: datetime) -> None:
        """``view``: {'open': paper row or None, 'closed': row closed this cycle or None, 'entered': bool},
        or None when this cycle did not evaluate the paper position (closed market, data error)."""
        self.touched.add(name)
        if strategy_cfg is not None:
            self.cfgs[name] = strategy_cfg
        now = to_ist(now)
        settings = self.settings(name)
        cached = self.states.get(name)
        entering = bool(view and view.get('entered') and settings['mode'] != 'off')
        state = self._load(name, fresh=bool(entering or (cached and cached.get('open_trade'))))
        if state is None:
            return
        deadline = self.mono() + self.budget_seconds
        paper = view.get('open') if view else None
        trade = state.get('open_trade')
        if trade and trade['state'] == 'entering':
            self._drive_entry(name, state, trade, False, market_open, now, deadline)
            trade = state.get('open_trade')
            if trade and trade['state'] == 'entering':
                return
        if trade and trade['state'] in ('open', 'exiting'):
            reason = self._exit_reason(trade, settings, view, paper, now)
            if reason:
                if trade['state'] == 'open':
                    self._begin_exit(name, state, trade, reason, view, now)
                self._drive_exit(name, state, trade, market_open, now, deadline)
        if state.get('open_trade'):
            return
        if entering and paper is not None and strategy_cfg is not None:
            done = [row.get('signal_id') for row in state.get('recent', [])] + [row.get('signal_id') for row in state.get('skipped', [])]
            if paper.signal_id not in done:
                self._enter(name, state, strategy_cfg, settings, paper, market_open, now, deadline)

    def _exit_reason(self, trade, settings, view, paper, now) -> str | None:
        if trade['state'] == 'exiting':
            return trade.get('exit_reason') or 'Exit'
        if view is not None and (paper is None or paper.signal_id != trade['signal_id']):
            closed = view.get('closed')
            if closed is not None and closed.signal_id == trade['signal_id'] and closed.exit_reason:
                return str(closed.exit_reason)
            return 'Paper position closed'
        for stamp in (settings.get('exit_now'), (self.account or {}).get('exit_all')):
            try:
                if stamp and datetime.fromisoformat(str(stamp)) > datetime.fromisoformat(trade['opened_at']):
                    return 'Exit requested'
            except (TypeError, ValueError):
                continue
        if now.date() > date.fromisoformat(trade['expiry']):
            return 'Expiry'
        return None

    # ------------------------------------------------------------------ quotes
    def _quote(self, trade: dict, strike: float) -> dict | None:
        try:
            chain = self.provider.get_option_chain(date.fromisoformat(trade['expiry']))
            quote = chain.quote(float(strike), trade['option_type'])
        except Exception as exc:
            log.warning('live_quote_unavailable error=%s', type(exc).__name__)
            return None
        if quote is None:
            return None
        return {'bid': quote.bid, 'ask': quote.ask, 'ltp': quote.ltp}

    # ------------------------------------------------------------------ entry
    def _skip(self, name, state, settings, paper, reason, now) -> None:
        totals = state['totals'].setdefault(settings['mode'], dict(EMPTY_TOTALS))
        totals['skipped'] += 1
        state['skipped'] = (state.get('skipped') or [])[-(KEEP - 1):] + [
            {'signal_id': paper.signal_id, 'at': iso(now), 'mode': settings['mode'], 'reason': reason}]
        self._alert(name, state, 'entry skipped', reason, now)
        self._save(name, state, now)

    def _enter(self, name, state, strategy_cfg, settings, paper, market_open, now, deadline) -> None:
        mode, capital, cap = settings['mode'], settings['capital'], settings['slippage_cap']
        account = self.account

        def refuse(reason):
            self._skip(name, state, settings, paper, reason, now)

        if account is None:
            return refuse('live settings could not be read')
        if account.get('kill_switch'):
            return refuse('kill switch is on')
        if mode == 'live' and not self.unlocked:
            return refuse('live trading is locked on the server (LIVE_TRADING_ENABLED is not true)')
        if not MIN_CAPITAL <= capital <= MAX_CAPITAL:
            return refuse(f'deployed capital must be between {MIN_CAPITAL:,.0f} and {MAX_CAPITAL:,.0f}')
        if not market_open:
            return refuse('market is closed')
        if mode == 'live' and self.mismatch:
            return refuse(f'broker positions do not match the desk ({self.mismatch})')
        limit = account.get('daily_loss_limit')
        if mode == 'live' and isinstance(limit, (int, float)) and limit > 0:
            today = now.date().isoformat()
            for other in (account.get('strategies') or {}):      # every configured strategy counts, once per process
                self._load(other, fresh=False)
            lost = -sum((s.get('day') or {}).get('realized', 0.0) for s in self.states.values()
                        if (s.get('day') or {}).get('date') == today)
            if lost >= limit:
                return refuse(f'daily loss limit reached ({lost:,.0f} of {limit:,.0f})')
        if paper.sell_price is None or paper.buy_price is None or paper.net_credit is None:
            return refuse('paper entry has no prices')
        expiry = paper.expiry if isinstance(paper.expiry, date) else date.fromisoformat(str(paper.expiry)[:10])
        long_option = is_long_option(paper)
        if long_option:
            # One bought option: the premium is the whole outlay; size it as the strategy does, on the deployed capital.
            fraction = premium_fraction(name)
            lots = int(capital * fraction // (float(paper.buy_price) * int(paper.lot_size)))
            lots = min(lots, settings['max_lots']) if settings['max_lots'] else lots
            if lots < 1:
                return refuse('deployed capital is below the premium of one lot')
            outlay = round(float(paper.buy_price) * lots * int(paper.lot_size), 2)
        else:
            width = abs(float(paper.sell_strike) - float(paper.buy_strike))
            try:
                plan = build_risk_plan(float(paper.sell_price), float(paper.buy_price), width, int(paper.lot_size),
                                       now.date() == expiry, replace(strategy_cfg, capital=capital), now.date())
            except ValueError as exc:
                return refuse(f'sizing: {exc}')
            lots = min(plan.lots, settings['max_lots']) if settings['max_lots'] else plan.lots
            if lots < 1:
                return refuse('deployed capital is below the margin of one lot')
            outlay = round(plan.margin_per_lot * lots, 2)
        units = lots * int(paper.lot_size)
        if units > FREEZE_UNITS:
            return refuse(f'{units} units exceeds the exchange freeze quantity')
        try:
            sell_id = self.provider.security_id(expiry, float(paper.sell_strike), paper.option_type)
            buy_id = self.provider.security_id(expiry, float(paper.buy_strike), paper.option_type)
        except Exception as exc:
            return refuse(f'contract lookup failed ({type(exc).__name__})')
        trade = {'signal_id': paper.signal_id, 'strategy': name, 'mode': mode, 'state': 'entering', 'step': 'hedge',
                 'opened_at': iso(now), 'expiry': expiry.isoformat(), 'option_type': paper.option_type,
                 'sell_strike': float(paper.sell_strike), 'buy_strike': float(paper.buy_strike),
                 'sell_security_id': str(sell_id), 'buy_security_id': str(buy_id),
                 'lots': lots, 'lot_size': int(paper.lot_size), 'units': units, 'capital': capital,
                 'slippage_cap': cap, 'margin_estimate': outlay, 'structure': 'long_option' if long_option else 'credit_spread',
                 'paper': {'sell_price': float(paper.sell_price), 'buy_price': float(paper.buy_price),
                           'net_credit': float(paper.net_credit), 'lots': int(paper.lots),
                           'stop_loss': paper.stop_loss, 'target': paper.target},
                 'legs': ({'hedge_entry': new_leg('BUY', buy_id, units)} if long_option else
                          {'hedge_entry': new_leg('BUY', buy_id, units), 'short_entry': new_leg('SELL', sell_id, units)}),
                 'entry_credit': None, 'exit_value': None, 'pnl': None, 'exit_reason': None, 'closed_at': None,
                 'entry_slippage': None, 'exit_slippage': None, 'paper_exit': None, 'exit_minutes': 0, 'notes': []}
        hedge_touch = touch(self._quote(trade, trade['buy_strike']), 'BUY')
        short_touch = 0.0 if long_option else touch(self._quote(trade, trade['sell_strike']), 'SELL')
        if short_touch is None or hedge_touch is None:
            return refuse('no live quote for one of the legs')
        worse = trade['paper']['net_credit'] - (short_touch - hedge_touch)
        if worse > cap:
            what = 'option' if long_option else 'spread'
            return refuse(f'{what} is {worse:.2f} points worse than the paper price (cap {cap:.2f})')
        if mode == 'live':
            try:
                available = self.broker(mode).available_balance()
            except BrokerError as exc:
                return refuse(f'broker unavailable: {exc}')
            if available < trade['margin_estimate']:
                return refuse(f"funds: {available:,.0f} available, about {trade['margin_estimate']:,.0f} needed")
        state['open_trade'] = trade
        self._save(name, state, now)
        self._drive_entry(name, state, trade, True, market_open, now, deadline)

    def _drive_entry(self, name, state, trade, fresh, market_open, now, deadline) -> None:
        """``fresh``: the entry minute itself. Later minutes only settle what was sent and tidy up."""
        legs, paper = trade['legs'], trade['paper']
        if trade['step'] == 'hedge':
            at = touch(self._quote(trade, trade['buy_strike']), 'BUY') if fresh else None
            prices = [tick(at + 1.0, True), tick(at + 2.0, True)] if at is not None else []
            if self._work(name, state, trade, 'hedge_entry', prices, deadline, now, stop_on_reject=True) == 'pending':
                return
            if not legs['hedge_entry']['filled']:
                what = 'option' if trade.get('structure') == 'long_option' else 'hedge leg'
                return self._finish(name, state, trade, 'failed', self._why(legs['hedge_entry'], f'{what} did not fill'), now)
            if trade.get('structure') == 'long_option':
                return self._opened_long(name, state, trade, now)
            legs['short_entry']['qty'] = legs['hedge_entry']['filled']
            trade['step'] = 'short'
        if trade['step'] == 'short':
            quote = self._quote(trade, trade['sell_strike']) if fresh else None
            at = touch(quote, 'SELL')
            prices = []
            if at is not None:
                floor = tick(paper['net_credit'] - trade['slippage_cap'] + legs['hedge_entry']['avg'], True)
                first = max(floor, tick(at - 1.0, False))
                prices = [first] if first == floor else [first, floor]
            if self._work(name, state, trade, 'short_entry', prices, deadline, now, stop_on_reject=True) == 'pending':
                return
            excess = legs['hedge_entry']['filled'] - legs['short_entry']['filled']
            if excess > 0:
                legs['hedge_unwind'] = new_leg('SELL', trade['buy_security_id'], excess)
                trade['step'] = 'unwind'
            else:
                trade['step'] = 'done'
        if trade['step'] == 'unwind':
            if not market_open:
                return
            outcome = self._work(name, state, trade, 'hedge_unwind', self._sell_ladder(trade, trade['buy_strike']),
                                 deadline, now, stop_on_reject=False)
            if outcome == 'pending':
                return
            if outcome != 'filled':
                trade['exit_minutes'] += 1
                if trade['exit_minutes'] < HEDGE_GIVE_UP_MINUTES:
                    self._save(name, state, now)
                    return
                if legs['short_entry']['filled']:
                    # Still part of this trade: the exit sells every hedge unit that is left.
                    trade['notes'].append('extra hedge units could not be sold back at entry; they are sold at exit')
                else:
                    self._leave_hedge(state, trade, legs['hedge_unwind'])
            trade['step'] = 'done'
        short = legs['short_entry']['filled']
        if not short:
            return self._finish(name, state, trade, 'failed', self._why(legs['short_entry'], 'short leg did not fill'), now)
        trade.update(state='open', units=short, lots=short // trade['lot_size'], exit_minutes=0,
                     entry_credit=round(legs['short_entry']['avg'] - legs['hedge_entry']['avg'], 2))
        trade['entry_slippage'] = round(paper['net_credit'] - trade['entry_credit'], 2)
        self._alert(name, state, 'entered', f"{trade['mode']}: sold {trade['sell_strike']:.0f} / bought {trade['buy_strike']:.0f} "
                    f"{trade['option_type']} x {trade['lots']} lots, credit {trade['entry_credit']:.2f} "
                    f"(paper {paper['net_credit']:.2f})", now)
        self._save(name, state, now)

    def _opened_long(self, name, state, trade, now) -> None:
        """A bought option filled: the trade is open. Its 'credit' is minus the premium paid, like the paper row."""
        leg, paper = trade['legs']['hedge_entry'], trade['paper']
        trade.update(state='open', step='done', units=leg['filled'], lots=leg['filled'] // trade['lot_size'], exit_minutes=0,
                     entry_credit=round(-leg['avg'], 2))
        trade['entry_slippage'] = round(paper['net_credit'] - trade['entry_credit'], 2)
        self._alert(name, state, 'entered', f"{trade['mode']}: bought {trade['buy_strike']:.0f} {trade['option_type']} x "
                    f"{trade['lots']} lots at {leg['avg']:.2f} (paper {paper['buy_price']:.2f})", now)
        self._save(name, state, now)

    @staticmethod
    def _why(leg, fallback) -> str:
        for order in reversed(leg['orders']):
            if order.get('reason'):
                return f"{fallback}: {order['reason']}"
        return fallback

    # ------------------------------------------------------------------ exit
    def _begin_exit(self, name, state, trade, reason, view, now) -> None:
        legs = trade['legs']
        hedge_left = legs['hedge_entry']['filled'] - (legs.get('hedge_unwind') or {}).get('filled', 0)
        long_option = trade.get('structure') == 'long_option'
        if not long_option:
            legs['short_exit'] = new_leg('BUY', trade['sell_security_id'], legs['short_entry']['filled'])
        legs['hedge_exit'] = new_leg('SELL', trade['buy_security_id'], hedge_left)
        closed = view.get('closed') if view else None
        if closed is not None and closed.signal_id == trade['signal_id']:
            trade['paper_exit'] = {'reason': closed.exit_reason, 'value': closed.exit_value}
        trade.update(state='exiting', step='hedge' if long_option else 'short', exit_reason=reason, exit_started_at=iso(now),
                     exit_minutes=0)
        self._save(name, state, now)

    def _buy_ladder(self, trade, strike) -> list:
        at = touch(self._quote(trade, strike), 'BUY')
        return [None] if at is None else [tick(at + 1.0, True), tick(at + 3.0, True), tick(at + 6.0, True), None]

    def _sell_ladder(self, trade, strike) -> list:
        at = touch(self._quote(trade, strike), 'SELL')
        return [None] if at is None else [tick(max(at - 0.5, TICK), False), tick(max(at - 1.5, TICK), False), None]

    def _drive_exit(self, name, state, trade, market_open, now, deadline) -> None:
        legs = trade['legs']
        expiry = date.fromisoformat(trade['expiry'])
        if now.date() > expiry:
            return self._settle(name, state, trade, now, deadline)
        if not market_open:
            return
        if trade['step'] == 'short':
            outcome = self._work(name, state, trade, 'short_exit', self._buy_ladder(trade, trade['sell_strike']),
                                 deadline, now, stop_on_reject=False)
            if outcome != 'filled':
                if outcome != 'pending':
                    trade['exit_minutes'] += 1
                    if trade['exit_minutes'] in (1, 5) or trade['exit_minutes'] % 15 == 0:
                        self._alert(name, state, 'EXIT NOT FILLED', self._why(legs['short_exit'], 'short leg is still open')
                                    + f" after {trade['exit_minutes']} attempt(s); retrying every minute", now)
                    self._save(name, state, now)
                return
            trade.update(step='hedge', exit_minutes=0)
        if trade['step'] == 'hedge':
            if legs['hedge_exit']['qty'] > 0:
                outcome = self._work(name, state, trade, 'hedge_exit', self._sell_ladder(trade, trade['buy_strike']),
                                     deadline, now, stop_on_reject=False)
                if outcome == 'pending':
                    return
                if outcome != 'filled':
                    trade['exit_minutes'] += 1
                    if trade.get('structure') == 'long_option':
                        # The bought option is the whole position: keep offering it every minute rather than abandon it.
                        if trade['exit_minutes'] in (1, 5) or trade['exit_minutes'] % 15 == 0:
                            self._alert(name, state, 'EXIT NOT FILLED', self._why(legs['hedge_exit'], 'option is still held')
                                        + f" after {trade['exit_minutes']} attempt(s); retrying every minute", now)
                        self._save(name, state, now)
                        return
                    if trade['exit_minutes'] < HEDGE_GIVE_UP_MINUTES:
                        self._save(name, state, now)
                        return
                    self._leave_hedge(state, trade, legs['hedge_exit'])
            self._close(name, state, trade, now)

    def _leave_hedge(self, state, trade, leg) -> None:
        left = leg['qty'] - leg['filled']
        if left > 0:
            sid = leg['security_id']
            held = (state.get('residuals') or {}).get(sid, {}).get('qty', 0)
            state.setdefault('residuals', {})[sid] = {'qty': held + left, 'expiry': trade['expiry']}
            trade['notes'].append(f'{left} units of the hedge leg found no buyer and were left to expire (valued at zero)')

    def _settle(self, name, state, trade, now, deadline) -> None:
        """The contract has expired: book what was still open at its intrinsic value."""
        legs = trade['legs']
        for key in ('short_exit', 'hedge_exit'):
            if key in legs and self._work(name, state, trade, key, [], deadline, now, stop_on_reject=False) == 'pending':
                return
        spot, estimated = self._settlement(date.fromisoformat(trade['expiry']), now)
        if spot is None:
            trade['exit_minutes'] += 1
            if trade['exit_minutes'] == 1:
                self._alert(name, state, 'expired, settlement price not available yet', '', now)
                self._save(name, state, now)
            return
        hedge_left = legs['hedge_exit']['qty'] - legs['hedge_exit']['filled']
        if 'short_exit' in legs:
            short_left = legs['short_exit']['qty'] - legs['short_exit']['filled']
            legs['short_settle'] = {'side': 'BUY', 'security_id': trade['sell_security_id'], 'qty': short_left, 'filled': short_left,
                                    'avg': intrinsic(trade['option_type'], trade['sell_strike'], spot), 'orders': [], 'counts': True}
        legs['hedge_settle'] = {'side': 'SELL', 'security_id': trade['buy_security_id'], 'qty': hedge_left, 'filled': hedge_left,
                                'avg': intrinsic(trade['option_type'], trade['buy_strike'], spot), 'orders': [], 'counts': True}
        trade['exit_reason'] = 'Expiry'
        trade['notes'].append(f"settled at NIFTY {spot:.2f}" + (' (index close, not the official settlement)' if estimated else ''))
        self._close(name, state, trade, now)

    def _settlement(self, expiry: date, now: datetime):
        try:
            official = self.provider.get_expiry_settlement(expiry)
            if official is not None and official.spot and math.isfinite(official.spot):
                return float(official.spot), False
        except Exception as exc:
            log.warning('live_settlement_lookup_failed error=%s', type(exc).__name__)
        try:
            bars = self.provider.get_spot_bars(now)
            day = bars[bars.index.date == expiry]
            if len(day):
                return float(day['close'].iloc[-1]), True
        except Exception as exc:
            log.warning('live_settlement_estimate_failed error=%s', type(exc).__name__)
        return None, False

    def _close(self, name, state, trade, now) -> None:
        legs = trade['legs']
        bought = sum(legs[key]['filled'] * legs[key]['avg'] for key in ('short_exit', 'short_settle')
                     if key in legs and legs[key]['filled'])
        sold = sum(legs[key]['filled'] * legs[key]['avg'] for key in ('hedge_exit', 'hedge_settle')
                   if key in legs and legs[key]['filled'])
        if trade['units']:
            trade['exit_value'] = round((bought - sold) / trade['units'], 2)
        paper_exit = trade.get('paper_exit') or {}
        if trade['exit_value'] is not None and isinstance(paper_exit.get('value'), (int, float)):
            trade['exit_slippage'] = round(trade['exit_value'] - paper_exit['value'], 2)
        self._finish(name, state, trade, 'closed', trade.get('exit_reason') or 'Exit', now)

    # ------------------------------------------------------------------ finish
    def _finish(self, name, state, trade, outcome, reason, now) -> None:
        trade.update(state=outcome, closed_at=iso(now), pnl=trade_cash(trade))
        if outcome == 'failed':
            trade['exit_reason'] = reason
        totals = state['totals'].setdefault(trade['mode'], dict(EMPTY_TOTALS))
        if outcome == 'closed':
            totals['trades'] += 1
            totals['winners'] += int(trade['pnl'] > 0)
            entry_slip, exit_slip = trade.get('entry_slippage') or 0.0, trade.get('exit_slippage') or 0.0
            totals['entry_slippage_points'] = round(totals['entry_slippage_points'] + entry_slip, 2)
            totals['exit_slippage_points'] = round(totals['exit_slippage_points'] + exit_slip, 2)
            totals['slippage_rupees'] = round(totals['slippage_rupees'] + (entry_slip + exit_slip) * trade['units'], 2)
            if 'stop' in str(trade.get('exit_reason') or '').lower():
                totals['stop_trades'] += 1
                totals['stop_slippage_points'] = round(totals['stop_slippage_points'] + entry_slip + exit_slip, 2)
        else:
            totals['failed'] += 1
        totals['realized_pnl'] = round(totals['realized_pnl'] + trade['pnl'], 2)
        if trade['mode'] == 'live':
            today = now.date().isoformat()
            day = state.get('day') if (state.get('day') or {}).get('date') == today else {'date': today, 'realized': 0.0}
            day['realized'] = round(day['realized'] + trade['pnl'], 2)
            state['day'] = day
        summary = {key: value for key, value in trade.items() if key != 'legs'}
        summary['fills'] = {key: {'side': leg['side'], 'qty': leg['filled'], 'avg': leg['avg']}
                            for key, leg in trade['legs'].items() if leg['filled']}
        state['recent'] = (state.get('recent') or [])[-(KEEP - 1):] + [summary]
        state['open_trade'] = None
        if outcome == 'closed':
            self._alert(name, state, 'exited', f"{trade['mode']}: {reason}, P&L {trade['pnl']:+,.2f} on {trade['lots']} lots"
                        + (f", slippage {(trade.get('entry_slippage') or 0) + (trade.get('exit_slippage') or 0):+.2f} points"
                           if trade.get('entry_slippage') is not None else ''), now)
        else:
            self._alert(name, state, 'ENTRY FAILED', f"{trade['mode']}: {reason}; cost {trade['pnl']:+,.2f}", now)
        self._save(name, state, now)
        try:
            self.store.archive(name, trade)
        except Exception as exc:
            log.warning('live_archive_failed strategy=%s error=%s', name, type(exc).__name__)

    # ------------------------------------------------------------------ orders
    @staticmethod
    def _apply(leg, order, status) -> None:
        order.update(order_id=status.order_id or order.get('order_id'), status=status.status, final=status.final,
                     filled=int(status.filled_qty or 0))
        if status.avg_price is not None:
            order['avg'] = float(status.avg_price)
        if status.reason:
            order['reason'] = status.reason
        done = [(o['filled'], o['avg']) for o in leg['orders'] if o['filled'] and o.get('avg') is not None]
        leg['filled'] = sum(qty for qty, _ in done)
        leg['avg'] = round(sum(qty * avg for qty, avg in done) / leg['filled'], 4) if leg['filled'] else None

    def _resolve(self, broker, leg, order, deadline) -> bool:
        """Bring one order to a final state: wait briefly for the fill, then cancel what rests. False: still unknown."""
        try:
            if order['order_id'] is None:
                found = broker.order_by_correlation(order['cid'])
                if found is None:
                    order.update(status='NOT_PLACED', final=True)
                    return True
                self._apply(leg, order, found)
            waited = 0.0
            while not order['final'] and waited < self.fill_wait and self.mono() < deadline:
                self.sleep(self.poll_seconds)
                waited += self.poll_seconds
                self._apply(leg, order, broker.order(order['order_id']))
            if not order['final']:
                broker.cancel(order['order_id'])
                for _ in range(3):
                    self.sleep(self.poll_seconds)
                    self._apply(leg, order, broker.order(order['order_id']))
                    if order['final']:
                        break
            self.broker_error = None
            return bool(order['final'])
        except BrokerError as exc:
            self.broker_error = str(exc)[:200]
            order['reason'] = self.broker_error
            return False

    def _work(self, name, state, trade, key, prices, deadline, now, stop_on_reject) -> str:
        """Fill ``trade['legs'][key]``, one order per price in ``prices`` (None = market order).
        Returns 'filled', 'short' (attempts used up), 'rejected', or 'pending' (an order's fate is unknown or
        time ran out; call again next cycle)."""
        leg = trade['legs'][key]
        if leg['qty'] <= 0:
            return 'filled'
        try:
            broker = self.broker(trade['mode'])
        except BrokerError as exc:
            self.broker_error = str(exc)[:200]
            return 'pending' if leg['orders'] and not leg['orders'][-1]['final'] else 'short'
        queue = list(prices)
        strike = trade['sell_strike'] if leg['security_id'] == trade['sell_security_id'] else trade['buy_strike']
        while True:
            order = leg['orders'][-1] if leg['orders'] else None
            if order is not None and not order['final']:
                settled = self._resolve(broker, leg, order, deadline)
                self._save(name, state, now)
                if not settled:
                    return 'pending'
                if order['status'] == 'REJECTED' and stop_on_reject:
                    return 'rejected'
            if leg['filled'] >= leg['qty']:
                return 'filled'
            if not queue:
                return 'short'
            if self.mono() >= deadline:
                return 'pending'
            price = queue.pop(0)
            attempt = len(leg['orders'])
            order = {'cid': correlation(name, trade['signal_id'], key, attempt), 'order_id': None, 'price': price,
                     'qty': leg['qty'] - leg['filled'], 'status': 'NEW', 'filled': 0, 'avg': None, 'final': False,
                     'reason': None, 'at': iso(now)}
            leg['orders'].append(order)
            self._save(name, state, now)                      # stored before it is sent
            try:
                placed = broker.place(correlation_id=order['cid'], side=leg['side'], security_id=leg['security_id'],
                                      quantity=order['qty'], price=price, market=self._quote(trade, strike))
            except BrokerRejected as exc:
                order.update(status='REJECTED', final=True, reason=str(exc)[:200])
                log.warning('live_order_rejected strategy=%s leg=%s reason=%s', name, key, order['reason'])
                self._save(name, state, now)
                if stop_on_reject:
                    return 'rejected'
                continue
            except BrokerError as exc:
                self.broker_error = order['reason'] = str(exc)[:200]
                self._save(name, state, now)
                return 'pending'                              # unknown: settled by correlation id next cycle
            self._apply(leg, order, placed)
            self._save(name, state, now)

    # ------------------------------------------------------------------ reconciliation
    def _reconcile(self, now: datetime) -> None:
        today = now.date().isoformat()
        expected: dict[str, int] = {}
        unsettled = False
        for name, state in self.states.items():
            residuals = state.get('residuals') or {}
            for sid in [sid for sid, row in residuals.items() if row.get('expiry', '') < today]:
                residuals.pop(sid)
            trade = state.get('open_trade')
            live = trade is not None and trade['mode'] == 'live'
            if live:
                unsettled = unsettled or any(o and not o['final'] for leg in trade['legs'].values() for o in leg['orders'][-1:])
                for sid, qty in net_holdings(trade).items():
                    expected[sid] = expected.get(sid, 0) + qty
            if live or any(row.get('qty') for row in residuals.values()):
                for sid, row in residuals.items():
                    expected[sid] = expected.get(sid, 0) + int(row.get('qty', 0))
        expected = {sid: qty for sid, qty in expected.items() if qty}
        if not expected or unsettled or not self.unlocked:
            if not expected:
                self.mismatch, self._mismatch_rounds = None, 0
            return
        try:
            actual = self.broker('live').positions()
        except BrokerError as exc:
            self.broker_error = str(exc)[:200]
            return
        # The account is shared: Dhan's own algos and manual trades may hold the same contracts, so the net
        # quantity there can exceed the desk's. Only a shortfall is a problem: it means part of a desk trade
        # is no longer at the broker (closed by hand or by Dhan's risk system).
        wrong = {sid: (qty, actual.get(sid, 0)) for sid, qty in expected.items()
                 if (actual.get(sid, 0) > qty if qty < 0 else actual.get(sid, 0) < qty)}
        if not wrong:
            if self.mismatch:
                log.warning('live_positions_match_again')
            self.mismatch, self._mismatch_rounds = None, 0
            return
        self._mismatch_rounds += 1
        if self._mismatch_rounds < 2:                         # the position book can trail a fill by a moment
            return
        detail = '; '.join(f'security {sid}: desk {want}, broker {have}' for sid, (want, have) in sorted(wrong.items()))
        if detail != self.mismatch:
            self.mismatch = detail
            for name, state in self.states.items():
                trade = state.get('open_trade')
                if trade and trade['mode'] == 'live':
                    self._alert(name, state, 'BROKER POSITIONS DO NOT MATCH', detail + '. New live entries are blocked '
                                'until they match; check the Dhan account.', now)
                    try:
                        self._save(name, state, now)
                    except Exception as exc:
                        log.warning('live_state_save_failed strategy=%s error=%s', name, type(exc).__name__)


def paper_view(open_row, closed_row=None, entered=False) -> dict:
    return {'open': open_row, 'closed': closed_row, 'entered': bool(entered)}


__all__ = ['LiveDesk', 'LiveStore', 'paper_view', 'MIN_CAPITAL', 'MAX_CAPITAL', 'MODES']
