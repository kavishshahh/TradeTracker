"""Polymarket paper algos: private, read-only views of the paper accounts. No order routes.

Separate from the Indian-market Algo Lab: its own routes (/poly/*), its own Firestore
collections (poly_paper_state, poly_paper_trades, poly_catalog) and no shared code. The paper trader itself is
a standalone feed-driven process (polymarket/worker.py); this API only reads what it saved.

Who may see this section is decided by Firestore, not code: the document
`feature_access/polymarket_algos` holds `emails: [...]`. A signed-in user is allowed only
when their verified Firebase email is in that list. Everyone else gets `allowed: false`
from /poly/access and 404 from the data route, so the section does not exist for them.
"""
import gzip
import json
import logging
import math
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response

log = logging.getLogger(__name__)

ACCESS_DOC = ('feature_access', 'polymarket_algos')
GZIP_MIN_BYTES = 1024
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

    def reply(request, payload):
        """JSON, gzipped when the browser accepts it (the account documents are several hundred KB of text)."""
        if 'gzip' not in request.headers.get('accept-encoding', ''):
            return JSONResponse(jsonable_encoder(payload))
        # Same encoding as FastAPI's own JSON replies, then compressed.
        body = json.dumps(jsonable_encoder(payload), ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
        if len(body) < GZIP_MIN_BYTES:
            return Response(body, media_type='application/json')
        return Response(gzip.compress(body, compresslevel=6), media_type='application/json',
                        headers={'Content-Encoding': 'gzip', 'Vary': 'Accept-Encoding'})

    def stamp(value):
        """Firestore commit/read time as epoch seconds; None when the client library does not supply it."""
        try:
            return value.timestamp() if value is not None else None
        except Exception:
            return None

    @router.get('/paper')
    async def paper(request: Request, since: float | None = None, current_user: str = Depends(get_current_user)):
        """Account documents. With ``since`` (the ``as_of`` of the page's previous reply) only accounts whose
        document was written after it are sent, plus ``ids``, the full list of accounts, so the page can
        merge them into what it holds. Without it, everything is sent."""
        if not is_allowed(current_user):
            raise HTTPException(404, 'Not found')
        if since is not None and not (math.isfinite(since) and since >= 0):
            raise HTTPException(422, 'since must be a non-negative number of seconds')
        try:
            docs = list(db.collection('poly_paper_state').stream())
            catalog = {doc.id: doc.to_dict() for doc in db.collection('poly_catalog').stream()}
        except Exception as exc:
            log.warning('poly_api_unavailable error=%s', type(exc).__name__)
            raise HTTPException(503, 'Polymarket paper data is unavailable') from None
        read_times = [t for t in (stamp(getattr(doc, 'read_time', None)) for doc in docs) if t is not None]
        # The oldest read time of the snapshot: anything written after it is sent next time, so nothing is missed.
        as_of = min(read_times) if read_times and len(read_times) == len(docs) else None
        def changed(doc):
            written = stamp(getattr(doc, 'update_time', None))
            return since is None or written is None or written > since
        states = {doc.id: doc.to_dict() for doc in docs if changed(doc)}
        payload = {'strategies': states, 'catalog': catalog, 'execution': 'paper_only', 'as_of': as_of}
        if since is not None:
            payload.update(partial=True, ids=[doc.id for doc in docs])
        return reply(request, payload)

    @router.get('/trades')
    async def trades(request: Request, since: float | None = None, current_user: str = Depends(get_current_user)):
        """Paper ledger (every buy and settlement), oldest first. The ledger is append-only, so the page keeps
        what it already has and passes ``since`` (epoch seconds of its newest row) to read only rows at or after
        it: one Firestore read per returned bet instead of one per bet ever placed. Without ``since`` the
        whole ledger is returned (first visit, or the browser has no cached copy)."""
        if not is_allowed(current_user):
            raise HTTPException(404, 'Not found')
        if since is not None and not (math.isfinite(since) and since >= 0):
            raise HTTPException(422, 'since must be a non-negative number of seconds')
        try:
            query = db.collection('poly_paper_trades')
            if since is not None:
                from google.cloud.firestore_v1.base_query import FieldFilter
                query = query.where(filter=FieldFilter('t', '>=', since))
            rows = [doc.to_dict() for doc in query.stream()]
        except Exception as exc:
            log.warning('poly_api_unavailable error=%s', type(exc).__name__)
            raise HTTPException(503, 'Polymarket trade ledger is unavailable') from None
        return reply(request, {'trades': sorted(rows, key=lambda row: row.get('t', 0)), 'execution': 'paper_only'})

    return router
