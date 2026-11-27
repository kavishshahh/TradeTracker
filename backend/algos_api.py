"""Authenticated algo catalogue and paper account views. No route here sends an order: the owner's
live settings (/algos/live) are only stored, and the worker's live desk acts on them.

Three tiers, decided by Firestore, not code:
- Every signed-in user sees the catalogue's public fields (names, descriptions, backtest
  metrics and monthly returns) and each paper account's summary numbers.
- Users whose verified email is listed in `feature_access/algo_lab` (`emails: [...]`) also
  see the trades: the backtest ledger, open positions and the closed paper ledger.
- The owner (ALGO_LAB_OWNER_EMAIL) additionally receives each strategy's rules,
  limitations and tuning parameters, and manages the list from Settings > Admin.

Anyone may ask for access: POST /algos/access/request writes one document to
`algo_access_requests/{uid}` (email, requested_at, status) for the owner to grant or decline.

Live trading (owner only): `algo_live/account` holds, per strategy, the mode (off, dry_run, live), the
capital to deploy and optional limits, plus the account-wide kill switch and daily loss limit. The worker
(algos/zen_credit/execution/live.py) reads that document every round and publishes what it did to
`algo_live_state/{strategy}`; these routes read those and never talk to the broker.
"""
from datetime import datetime, timedelta, timezone
import json
import logging
import os
import re
import time
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

log = logging.getLogger(__name__)

# The catalogue changes only when a strategy is re-published, yet every Algo Lab
# poll (each 30s per open tab) used to stream it again. One cached copy per
# process serves all users and bounds the Firestore reads it costs.
CATALOG_TTL_SECONDS = 60.0
ACCESS_DOC = ('feature_access', 'algo_lab')
REQUESTS_COLLECTION = 'algo_access_requests'
DEFAULT_OWNER_EMAIL = 'kavishshah30@gmail.com'
ACCESS_TTL_SECONDS = 60.0
EMAIL_TTL_SECONDS = 600.0
# Catalogue fields anyone may see. Rules, limitations, exit policy, tuning parameters and the
# full description are enough to rebuild an algo, so they are sent to the owner only; everyone
# else reads the short `summary` as the description.
PUBLIC_FIELDS = ('id', 'name', 'version', 'summary', 'underlying', 'category', 'capital',
                 'period_start', 'period_end', 'metrics', 'monthly', 'order', 'enabled', 'execution', 'feed', 'pnl_basis')
IST = timezone(timedelta(hours=5, minutes=30))
EMAIL_PATTERN = re.compile(r'[^@\s]+@[^@\s]+\.[^@\s]+')
# Deployed capital per strategy; the same bounds are enforced again by the desk before any order.
LIVE_MIN_CAPITAL, LIVE_MAX_CAPITAL = 120_000, 320_000
LIVE_MODES = ('off', 'dry_run', 'live')
# Live trading is switched off (owner's decision, 22 Nov 2026): only off and dry_run can be saved. The
# worker has its own switch (LIVE_ORDERS in algos/zen_credit/execution/broker.py); both must change to go live.
LIVE_TRADING_AVAILABLE = False
LIVE_ACCOUNT = ('algo_live', 'account')
LIVE_STATE = 'algo_live_state'
# Write-ups of strategies that were researched and not listed. A file shipped with the API: no Firestore read.
RESEARCH_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'seed_data', 'algo_research.json')
# Chart data for each listed algo's Robustness tab, built by algos/reports/build_robustness.py. Served from the
# file, so it costs no database read.
ROBUSTNESS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'seed_data', 'algo_robustness.json')


class FollowRequest(BaseModel):
    enabled: bool


class EmailAccess(BaseModel):
    email: str
    allowed: bool


class Decision(BaseModel):
    allowed: bool


class LiveStrategy(BaseModel):
    mode: str
    capital: float
    max_lots: int | None = None
    slippage_cap: float | None = None


class LiveAccount(BaseModel):
    kill_switch: bool | None = None
    daily_loss_limit: float | None = None      # 0 clears the limit
    exit_all: bool = False


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def create_algos_router(db, get_current_user, catalog_ttl=CATALOG_TTL_SECONDS, clock=time.monotonic,
                        email_lookup=None, owner_email=None, live_available=None):
    router = APIRouter(prefix='/algos', tags=['Paper algorithms'])
    cache = {'rows': None, 'at': None}
    equity_cache = {}                         # strategy id -> (read at, response)
    access = {'emails': None, 'at': 0.0}
    emails = {}
    owner = (owner_email or os.environ.get('ALGO_LAB_OWNER_EMAIL') or DEFAULT_OWNER_EMAIL).strip().lower()
    live_modes = LIVE_MODES if (LIVE_TRADING_AVAILABLE if live_available is None else live_available) else LIVE_MODES[:2]

    def unavailable(route, exc, detail):
        # Firestore errors were invisible behind a bare 503; the type name says
        # whether it is the read quota (ResourceExhausted) or connectivity.
        log.warning('algos_api_unavailable route=%s error=%s', route, type(exc).__name__)
        raise HTTPException(503, detail) from None

    def require_db():
        if db is None:
            raise HTTPException(503, 'Paper account storage is unavailable')

    # --- who is asking -------------------------------------------------------------------------
    def lookup_email(uid):
        """(email, verified). A test lookup may return just the email, taken as verified."""
        if email_lookup:
            found = email_lookup(uid)
            return found if isinstance(found, tuple) else (found, True)
        from firebase_admin import auth
        record = auth.get_user(uid)
        return record.email, bool(record.email_verified)

    def email_of(uid, verified_only=False):
        """The user's email, lower-cased; None when unknown. Cached per process.
        Requests and the allow-list take any email the account signed up with. Only the
        owner check needs Firebase to have verified it, or anyone could sign up with a
        password as the owner's address and read the rules."""
        try:
            now = clock()
            hit = emails.get(uid)
            if not hit or now - hit[2] > EMAIL_TTL_SECONDS:
                found, verified = lookup_email(uid)
                emails[uid] = hit = (found.strip().lower() if found else None, bool(verified), now)
            return hit[0] if hit[0] and (hit[1] or not verified_only) else None
        except Exception as exc:
            # Fail closed: an unknown caller is an outsider.
            log.warning('algo_access_email_lookup_failed error=%s', type(exc).__name__)
            return None

    def allowed_emails(force=False):
        if db is None:
            return set()
        now = clock()
        if force or access['emails'] is None or now - access['at'] > ACCESS_TTL_SECONDS:
            doc = db.collection(ACCESS_DOC[0]).document(ACCESS_DOC[1]).get()
            listed = (doc.to_dict() or {}).get('emails', []) if doc.exists else []
            access['emails'] = {str(item).strip().lower() for item in listed if item}
            access['at'] = now
        return access['emails']

    def is_owner(uid):
        return email_of(uid, verified_only=True) == owner

    def is_allowed(uid):
        email = email_of(uid)
        if not email:
            return False
        if email == owner:
            return is_owner(uid)
        try:
            return email in allowed_emails()
        except Exception as exc:
            log.warning('algo_access_check_failed error=%s', type(exc).__name__)
            return False

    def require_access(uid):
        if not is_allowed(uid):
            raise HTTPException(403, 'Past trades are shared by invitation. Request access from the Algo Lab page.')

    def without_trades(state):
        """A paper account for someone without access: the summary numbers stay, every trade goes."""
        if not state:
            return state
        return {**state, 'open_position': None, 'closed_positions': [], 'ledger_limit': 0,
                'in_trade': bool(state.get('open_position')), 'trades_hidden': True}

    def require_owner(uid):
        # The admin routes do not exist for anyone but the owner.
        if not is_owner(uid):
            raise HTTPException(404, 'Not found')

    def set_allowed(email, allowed):
        current = set(allowed_emails(force=True))
        (current.add if allowed else current.discard)(email)
        db.collection(ACCESS_DOC[0]).document(ACCESS_DOC[1]).set({'emails': sorted(current)}, merge=True)
        access['emails'], access['at'] = current, clock()
        return sorted(current)

    def request_status(uid):
        """'none', 'pending' or 'denied' for a user who is not allowed yet."""
        if db is None:
            return 'none'
        try:
            doc = db.collection(REQUESTS_COLLECTION).document(uid).get()
        except Exception as exc:
            log.warning('algo_access_request_read_failed error=%s', type(exc).__name__)
            return 'none'
        status = (doc.to_dict() or {}).get('status') if doc.exists else None
        return status if status in ('pending', 'denied') else 'none'

    def public(row):
        shown = {key: value for key, value in row.items() if key in PUBLIC_FIELDS}
        # A record without a summary gets a line that says nothing about how it trades.
        shown['description'] = row.get('summary') or f"{row.get('category', 'Strategy')} on {row.get('underlying', 'NIFTY 50')}."
        return shown

    # --- catalogue -----------------------------------------------------------------------------
    def read_catalog():
        require_db()
        now = clock()
        if cache['rows'] is not None and now - cache['at'] < catalog_ttl:
            return cache['rows']
        try:
            records = [{**doc.to_dict(), 'id': doc.id, 'execution': 'paper_only'}
                       for doc in db.collection('algo_catalog').stream()
                       if doc.to_dict().get('enabled', True)]
        except Exception as exc:
            unavailable('catalog', exc, 'Strategy catalogue is unavailable')
        cache['rows'] = sorted(records, key=lambda row: (row.get('order', 0), row['id']))
        cache['at'] = now
        return cache['rows']

    @router.get('/access')
    async def get_access(current_user: str = Depends(get_current_user)):
        owner_flag = is_owner(current_user)
        allowed = owner_flag or is_allowed(current_user)
        return {'allowed': allowed, 'owner': owner_flag, 'request': 'granted' if allowed else request_status(current_user)}

    @router.post('/access/request')
    async def request_access(current_user: str = Depends(get_current_user)):
        require_db()
        if is_allowed(current_user):
            return {'allowed': True, 'request': 'granted'}
        email = email_of(current_user)
        if not email:
            raise HTTPException(400, 'Your account has no email address to grant access to')
        try:
            db.collection(REQUESTS_COLLECTION).document(current_user).set({
                'uid': current_user, 'email': email, 'status': 'pending', 'requested_at': now_iso(), 'decided_at': None})
        except Exception as exc:
            unavailable('access_request', exc, 'Could not record your request')
        return {'allowed': False, 'request': 'pending'}

    @router.get('/access/admin')
    async def admin(current_user: str = Depends(get_current_user)):
        """Owner only: every request ever made and the current allow-list. Status is derived from the list,
        so an email revoked from the list shows its request as revoked without a second write."""
        require_owner(current_user)
        require_db()
        try:
            listed = sorted(allowed_emails(force=True))
            requests = [{**doc.to_dict(), 'uid': doc.id} for doc in db.collection(REQUESTS_COLLECTION).stream()]
        except Exception as exc:
            unavailable('access_admin', exc, 'Access requests are unavailable')
        for row in requests:
            stored = row.get('status', 'pending')
            row['status'] = 'granted' if row.get('email') in listed else ('revoked' if stored == 'granted' else stored)
        requests.sort(key=lambda row: row.get('requested_at') or '', reverse=True)
        return {'owner': owner, 'emails': listed, 'requests': requests}

    @router.put('/access/admin/emails')
    async def set_email_access(body: EmailAccess, current_user: str = Depends(get_current_user)):
        require_owner(current_user)
        require_db()
        email = body.email.strip().lower()
        if not EMAIL_PATTERN.fullmatch(email):
            raise HTTPException(422, 'Enter a valid email address')
        if email == owner:
            raise HTTPException(400, 'The owner always has access')
        try:
            listed = set_allowed(email, body.allowed)
        except Exception as exc:
            unavailable('access_admin', exc, 'Could not update access')
        return {'email': email, 'allowed': body.allowed, 'emails': listed}

    @router.put('/access/admin/requests/{uid}')
    async def decide_request(uid: str, body: Decision, current_user: str = Depends(get_current_user)):
        require_owner(current_user)
        require_db()
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', uid):
            raise HTTPException(404, 'Unknown request')
        try:
            ref = db.collection(REQUESTS_COLLECTION).document(uid)
            doc = ref.get()
            email = (doc.to_dict() or {}).get('email') if doc.exists else None
            if not email:
                raise HTTPException(404, 'Unknown request')
            if email == owner:
                raise HTTPException(400, 'The owner always has access')
            listed = set_allowed(email, body.allowed)
            ref.set({'status': 'granted' if body.allowed else 'denied', 'decided_at': now_iso()}, merge=True)
        except HTTPException:
            raise
        except Exception as exc:
            unavailable('access_admin', exc, 'Could not update access')
        return {'uid': uid, 'email': email, 'allowed': body.allowed, 'emails': listed}

    @router.get('/catalog')
    async def catalog(current_user: str = Depends(get_current_user)):
        full = is_owner(current_user)
        rows = read_catalog()
        return {'strategies': rows if full else [public(row) for row in rows], 'execution': 'paper_only',
                'detail': 'full' if full else 'public'}

    @router.get('/research')
    async def research(current_user: str = Depends(get_current_user)):
        # The notes name the rules of unlisted strategies, so like the catalogue rules they are the owner's only.
        require_owner(current_user)
        try:
            with open(RESEARCH_FILE, encoding='utf-8') as handle:
                return json.load(handle)
        except (OSError, ValueError) as exc:
            unavailable('research', exc, 'Research notes unavailable')

    @router.get('/robustness/{strategy_id}')
    async def robustness(strategy_id: str, current_user: str = Depends(get_current_user)):
        """Reliability-check results of one listed algo, for its Robustness tab. Open to everyone who may see
        past trades; the names of the settings moved in the sensitivity check describe the rules, so only the
        owner sees them and everyone else gets numbered changes."""
        require_access(current_user)
        try:
            with open(ROBUSTNESS_FILE, encoding='utf-8') as handle:
                body = json.load(handle)
        except (OSError, ValueError) as exc:
            unavailable('robustness', exc, 'Robustness checks unavailable')
        row = (body.get('algos') or {}).get(strategy_id)
        if row is None:
            raise HTTPException(404, 'No robustness checks for this strategy')
        if not is_owner(current_user):
            rows = (row.get('sensitivity') or {}).get('rows') or []
            row = {**row, 'sensitivity': {**row['sensitivity'], 'rows': [{**item, 'change': f'Setting change {index + 1}'} for index, item in enumerate(rows)]}} if rows else row
        return {**row, 'basis': body.get('basis'), 'strategy_id': strategy_id}

    # --- live trading (owner only) --------------------------------------------------------------
    def live_account():
        doc = db.collection(LIVE_ACCOUNT[0]).document(LIVE_ACCOUNT[1]).get()
        return (doc.to_dict() or {}) if doc.exists else {}

    def save_live_account(account, uid):
        account.update(updated_at=now_iso(), updated_by=email_of(uid))
        db.collection(LIVE_ACCOUNT[0]).document(LIVE_ACCOUNT[1]).set(account)
        return account

    def known_strategy(strategy_id):
        if not re.fullmatch(r'[a-z0-9_]{1,64}', strategy_id) or strategy_id not in {item['id'] for item in read_catalog()}:
            raise HTTPException(404, 'Unknown strategy')

    @router.get('/live')
    async def live(current_user: str = Depends(get_current_user)):
        """The owner's live settings and what the desk last reported: the account document, the desk
        heartbeat and one state document per configured strategy."""
        require_owner(current_user)
        require_db()
        try:
            account = live_account()
            states = {}
            for name in (account.get('strategies') or {}):
                doc = db.collection(LIVE_STATE).document(name).get()
                states[name] = doc.to_dict() if doc.exists else None
            desk = db.collection(LIVE_STATE).document('_desk').get()
        except Exception as exc:
            unavailable('live', exc, 'Live trading status is unavailable')
        return {'account': account, 'states': states, 'desk': desk.to_dict() if desk.exists else None,
                'limits': {'min_capital': LIVE_MIN_CAPITAL, 'max_capital': LIVE_MAX_CAPITAL, 'modes': list(live_modes)}}

    @router.put('/live/strategies/{strategy_id}')
    async def set_live_strategy(strategy_id: str, body: LiveStrategy, current_user: str = Depends(get_current_user)):
        require_owner(current_user)
        require_db()
        known_strategy(strategy_id)
        if body.mode == 'live' and 'live' not in live_modes:
            raise HTTPException(422, 'Live trading is switched off. Only Off and Dry run are available.')
        if body.mode not in live_modes:
            raise HTTPException(422, 'Mode must be off, dry_run or live')
        if not LIVE_MIN_CAPITAL <= body.capital <= LIVE_MAX_CAPITAL:
            raise HTTPException(422, f'Capital must be between {LIVE_MIN_CAPITAL:,} and {LIVE_MAX_CAPITAL:,}')
        if body.max_lots is not None and not 1 <= body.max_lots <= 20:
            raise HTTPException(422, 'Maximum lots must be between 1 and 20')
        if body.slippage_cap is not None and not 0 <= body.slippage_cap <= 20:
            raise HTTPException(422, 'Slippage cap must be between 0 and 20 points')
        try:
            account = live_account()
            strategies = dict(account.get('strategies') or {})
            # exit_now is a past request; it stays so an already answered one is not replayed as new.
            strategies[strategy_id] = {**(strategies.get(strategy_id) or {}), 'mode': body.mode, 'capital': float(body.capital),
                                       'max_lots': body.max_lots, 'slippage_cap': body.slippage_cap, 'updated_at': now_iso()}
            account['strategies'] = strategies
            save_live_account(account, current_user)
        except Exception as exc:
            unavailable('live', exc, 'Could not save live settings')
        log.warning('algo_live_setting strategy=%s mode=%s capital=%s', strategy_id, body.mode, body.capital)
        return {'strategy_id': strategy_id, **strategies[strategy_id]}

    @router.post('/live/strategies/{strategy_id}/exit')
    async def exit_live_strategy(strategy_id: str, current_user: str = Depends(get_current_user)):
        """Ask the desk to close this strategy's live trade on its next round. Stores a request; sends nothing."""
        require_owner(current_user)
        require_db()
        known_strategy(strategy_id)
        try:
            account = live_account()
            strategies = dict(account.get('strategies') or {})
            if strategy_id not in strategies:
                raise HTTPException(404, 'This strategy has no live settings')
            strategies[strategy_id] = {**strategies[strategy_id], 'exit_now': now_iso()}
            account['strategies'] = strategies
            save_live_account(account, current_user)
        except HTTPException:
            raise
        except Exception as exc:
            unavailable('live', exc, 'Could not record the exit request')
        log.warning('algo_live_exit_requested strategy=%s', strategy_id)
        return {'strategy_id': strategy_id, 'exit_now': strategies[strategy_id]['exit_now']}

    @router.put('/live/account')
    async def set_live_account(body: LiveAccount, current_user: str = Depends(get_current_user)):
        require_owner(current_user)
        require_db()
        if body.daily_loss_limit is not None and not 0 <= body.daily_loss_limit <= 10_000_000:
            raise HTTPException(422, 'Daily loss limit must be zero or a positive amount')
        try:
            account = live_account()
            if body.kill_switch is not None:
                account['kill_switch'] = body.kill_switch
            if body.daily_loss_limit is not None:
                account['daily_loss_limit'] = body.daily_loss_limit or None
            if body.exit_all:
                account['exit_all'] = now_iso()
            save_live_account(account, current_user)
        except Exception as exc:
            unavailable('live', exc, 'Could not save live settings')
        log.warning('algo_live_account kill_switch=%s exit_all=%s', account.get('kill_switch'), body.exit_all)
        return {key: account.get(key) for key in ('kill_switch', 'daily_loss_limit', 'exit_all')}

    @router.get('/paper')
    async def paper(current_user: str = Depends(get_current_user)):
        """Per-poll cost: the user's follows plus one state document per catalogued strategy.
        Without access the trades are stripped from every account before it leaves."""
        allowed = is_allowed(current_user)
        names = [item['id'] for item in read_catalog()]
        try:
            followed = db.collection('users').document(current_user).collection('algo_follows')
            subscriptions = {doc.id: doc.to_dict().get('enabled', False) for doc in followed.stream()}
            states = {}
            for name in names:
                doc = db.collection('algo_paper_state').document(name).get()
                state = doc.to_dict() if doc.exists else None
                states[name] = state if allowed else without_trades(state)
        except Exception as exc:
            unavailable('paper', exc, 'Paper account data is unavailable')
        return {'following': subscriptions, 'strategies': states, 'execution': 'paper_only', 'access': allowed}

    @router.get('/backtest/{strategy_id}')
    async def backtest(strategy_id: str, current_user: str = Depends(get_current_user)):
        """One strategy's backtest trade ledger: a single document read, fetched on demand by the browser."""
        require_access(current_user)
        require_db()
        if not re.fullmatch(r'[a-z0-9_]{1,64}', strategy_id):
            raise HTTPException(404, 'Unknown strategy')
        try:
            doc = db.collection('algo_backtests').document(strategy_id).get()
        except Exception as exc:
            unavailable('backtest', exc, 'Backtest ledger is unavailable')
        if not doc.exists:
            raise HTTPException(404, 'No backtest ledger for this strategy')
        return {**doc.to_dict(), 'strategy_id': strategy_id, 'execution': 'paper_only'}

    @router.get('/equity/{strategy_id}')
    async def equity(strategy_id: str, current_user: str = Depends(get_current_user)):
        """Realised backtest P&L per IST exit date, for the equity chart on the algo page.

        Built from the same ledger document as /backtest, so a new backtest is published once. It carries
        dates and rupee totals only (no strikes, sides or times) and, like the monthly figures, is open to
        every signed-in user. One document read per listed strategy per catalogue TTL, whoever asks."""
        require_db()
        if strategy_id not in {item['id'] for item in read_catalog()}:
            raise HTTPException(404, 'Unknown strategy')
        now = clock()
        held = equity_cache.get(strategy_id)
        if held is not None and now - held[0] < catalog_ttl:
            return held[1]
        try:
            doc = db.collection('algo_backtests').document(strategy_id).get()
        except Exception as exc:
            unavailable('equity', exc, 'Backtest equity is unavailable')
        if not doc.exists:
            raise HTTPException(404, 'No backtest ledger for this strategy')
        totals = {}
        for trade in doc.to_dict().get('trades') or []:
            try:
                day = datetime.fromisoformat(trade['exit']).astimezone(IST).date().isoformat()
                totals[day] = totals.get(day, 0.0) + float(trade['pnl'])
            except (KeyError, TypeError, ValueError):
                continue                      # a trade without an exit time or P&L has nothing to plot
        body = {'strategy_id': strategy_id, 'days': [{'day': day, 'pnl': round(pnl, 2)} for day, pnl in sorted(totals.items())]}
        equity_cache[strategy_id] = (now, body)
        return body

    @router.put('/follow/{strategy_id}')
    async def follow(strategy_id: str, body: FollowRequest, current_user: str = Depends(get_current_user)):
        require_db()
        if strategy_id not in {item['id'] for item in read_catalog()}:
            raise HTTPException(404, 'Unknown strategy')
        try:
            db.collection('users').document(current_user).collection('algo_follows').document(strategy_id).set({
                'enabled': body.enabled, 'updated_at': now_iso()})
        except Exception as exc:
            unavailable('follow', exc, 'Could not save your selection')
        return {'strategy_id': strategy_id, 'enabled': body.enabled, 'execution': 'paper_only'}

    return router
