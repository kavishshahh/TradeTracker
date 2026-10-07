"""Authenticated algo catalogue and paper account views; no broker order routes."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel


class FollowRequest(BaseModel):
    enabled: bool


def create_algos_router(db, get_current_user):
    router = APIRouter(prefix='/algos', tags=['Paper algorithms'])

    def require_db():
        if db is None:
            raise HTTPException(503, 'Paper account storage is unavailable')

    def read_catalog():
        require_db()
        try:
            records = [{**doc.to_dict(), 'id': doc.id, 'execution': 'paper_only'}
                       for doc in db.collection('algo_catalog').stream()
                       if doc.to_dict().get('enabled', True)]
            return sorted(records, key=lambda row: (row.get('order', 0), row['id']))
        except Exception:
            raise HTTPException(503, 'Strategy catalogue is unavailable') from None

    @router.get('/catalog')
    async def catalog(current_user: str = Depends(get_current_user)):
        return {'strategies': read_catalog(), 'execution': 'paper_only'}

    @router.get('/paper')
    async def paper(current_user: str = Depends(get_current_user)):
        require_db()
        try:
            followed = db.collection('users').document(current_user).collection('algo_follows')
            subscriptions = {doc.id: doc.to_dict().get('enabled', False) for doc in followed.stream()}
            states = {}
            for name in [item['id'] for item in read_catalog()]:
                doc = db.collection('algo_paper_state').document(name).get()
                states[name] = doc.to_dict() if doc.exists else None
            return {'following': subscriptions, 'strategies': states, 'execution': 'paper_only'}
        except Exception:
            raise HTTPException(503, 'Paper account data is unavailable') from None

    @router.put('/follow/{strategy_id}')
    async def follow(strategy_id: str, body: FollowRequest, current_user: str = Depends(get_current_user)):
        require_db()
        if strategy_id not in {item['id'] for item in read_catalog()}:
            raise HTTPException(404, 'Unknown strategy')
        try:
            db.collection('users').document(current_user).collection('algo_follows').document(strategy_id).set({
                'enabled': body.enabled, 'updated_at': datetime.now(timezone.utc).isoformat()})
        except Exception:
            raise HTTPException(503, 'Could not save your selection') from None
        return {'strategy_id': strategy_id, 'enabled': body.enabled, 'execution': 'paper_only'}

    return router
