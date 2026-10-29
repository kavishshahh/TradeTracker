"""Authenticated algo catalogue and paper account views; no broker order routes."""
from datetime import datetime, timezone
import logging
import re
import time
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

log = logging.getLogger(__name__)

# The catalogue changes only when a strategy is re-published, yet every Algo Lab
# poll (each 30s per open tab) used to stream it again. One cached copy per
# process serves all users and bounds the Firestore reads it costs.
CATALOG_TTL_SECONDS = 60.0


class FollowRequest(BaseModel):
    enabled: bool


def create_algos_router(db, get_current_user, catalog_ttl=CATALOG_TTL_SECONDS, clock=time.monotonic):
    router = APIRouter(prefix='/algos', tags=['Paper algorithms'])
    cache = {'rows': None, 'at': None}

    def unavailable(route, exc, detail):
        # Firestore errors were invisible behind a bare 503; the type name says
        # whether it is the read quota (ResourceExhausted) or connectivity.
        log.warning('algos_api_unavailable route=%s error=%s', route, type(exc).__name__)
        raise HTTPException(503, detail) from None

    def require_db():
        if db is None:
            raise HTTPException(503, 'Paper account storage is unavailable')

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

    @router.get('/catalog')
    async def catalog(current_user: str = Depends(get_current_user)):
        return {'strategies': read_catalog(), 'execution': 'paper_only'}

    @router.get('/paper')
    async def paper(current_user: str = Depends(get_current_user)):
        """Per-poll cost: the user's follows plus one state document per catalogued strategy."""
        names = [item['id'] for item in read_catalog()]
        try:
            followed = db.collection('users').document(current_user).collection('algo_follows')
            subscriptions = {doc.id: doc.to_dict().get('enabled', False) for doc in followed.stream()}
            states = {}
            for name in names:
                doc = db.collection('algo_paper_state').document(name).get()
                states[name] = doc.to_dict() if doc.exists else None
        except Exception as exc:
            unavailable('paper', exc, 'Paper account data is unavailable')
        return {'following': subscriptions, 'strategies': states, 'execution': 'paper_only'}

    @router.get('/backtest/{strategy_id}')
    async def backtest(strategy_id: str, current_user: str = Depends(get_current_user)):
        """One strategy's backtest trade ledger: a single document read, fetched on demand by the browser."""
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

    @router.put('/follow/{strategy_id}')
    async def follow(strategy_id: str, body: FollowRequest, current_user: str = Depends(get_current_user)):
        require_db()
        if strategy_id not in {item['id'] for item in read_catalog()}:
            raise HTTPException(404, 'Unknown strategy')
        try:
            db.collection('users').document(current_user).collection('algo_follows').document(strategy_id).set({
                'enabled': body.enabled, 'updated_at': datetime.now(timezone.utc).isoformat()})
        except Exception as exc:
            unavailable('follow', exc, 'Could not save your selection')
        return {'strategy_id': strategy_id, 'enabled': body.enabled, 'execution': 'paper_only'}

    return router
