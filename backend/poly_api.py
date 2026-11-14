"""Polymarket paper algos: private, read-only views of the paper accounts. No order routes.

Separate from the Indian-market Algo Lab: its own routes (/poly/*), its own Firestore
collections (poly_paper_state, poly_paper_trades, poly_catalog) and no shared code. The paper trader itself is
a standalone feed-driven process (polymarket/worker.py); this API only reads what it saved.

Who may see this section is decided by Firestore, not code: the document
`feature_access/polymarket_algos` holds `emails: [...]`. A signed-in user is allowed only
when their verified Firebase email is in that list. Everyone else gets `allowed: false`
from /poly/access and 404 from the data route, so the section does not exist for them.
"""
import logging
import time

from fastapi import APIRouter, Depends, HTTPException

log = logging.getLogger(__name__)

ACCESS_DOC = ('feature_access', 'polymarket_algos')
ACCESS_TTL_SECONDS = 60.0
EMAIL_TTL_SECONDS = 600.0


def create_poly_router(db, get_current_user, email_lookup=None, clock=time.monotonic):
    router = APIRouter(prefix='/poly', tags=['Polymarket paper algos'])
    access = {'emails': None, 'at': 0.0}
    emails = {}

    def lookup_email(uid):
        if email_lookup:
            return email_lookup(uid)
        from firebase_admin import auth
        record = auth.get_user(uid)
        return record.email if record.email_verified else None

    def allowed_emails():
        now = clock()
        if access['emails'] is None or now - access['at'] > ACCESS_TTL_SECONDS:
            doc = db.collection(ACCESS_DOC[0]).document(ACCESS_DOC[1]).get()
            listed = (doc.to_dict() or {}).get('emails', []) if doc.exists else []
            access['emails'] = {str(item).strip().lower() for item in listed if item}
            access['at'] = now
        return access['emails']

    def is_allowed(uid):
        if db is None:
            return False
        try:
            now = clock()
            hit = emails.get(uid)
            if not hit or now - hit[1] > EMAIL_TTL_SECONDS:
                emails[uid] = hit = (lookup_email(uid), now)
            return bool(hit[0]) and hit[0].strip().lower() in allowed_emails()
        except Exception as exc:
            # Fail closed: any lookup problem hides the section.
            log.warning('poly_access_check_failed error=%s', type(exc).__name__)
            return False

    @router.get('/access')
    async def get_access(current_user: str = Depends(get_current_user)):
        return {'allowed': is_allowed(current_user)}

    @router.get('/paper')
    async def paper(current_user: str = Depends(get_current_user)):
        if not is_allowed(current_user):
            raise HTTPException(404, 'Not found')
        try:
            states = {doc.id: doc.to_dict() for doc in db.collection('poly_paper_state').stream()}
            catalog = {doc.id: doc.to_dict() for doc in db.collection('poly_catalog').stream()}
        except Exception as exc:
            log.warning('poly_api_unavailable error=%s', type(exc).__name__)
            raise HTTPException(503, 'Polymarket paper data is unavailable') from None
        return {'strategies': states, 'catalog': catalog, 'execution': 'paper_only'}

    @router.get('/trades')
    async def trades(current_user: str = Depends(get_current_user)):
        """Complete paper ledger (every buy and settlement). Read on demand for export, not on the poll."""
        if not is_allowed(current_user):
            raise HTTPException(404, 'Not found')
        try:
            rows = [doc.to_dict() for doc in db.collection('poly_paper_trades').stream()]
        except Exception as exc:
            log.warning('poly_api_unavailable error=%s', type(exc).__name__)
            raise HTTPException(503, 'Polymarket trade ledger is unavailable') from None
        return {'trades': sorted(rows, key=lambda row: row.get('t', 0)), 'execution': 'paper_only'}

    return router
