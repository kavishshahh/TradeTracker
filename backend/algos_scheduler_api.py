"""Protected Cloudflare-to-backend paper evaluation; no broker order routes."""
from datetime import datetime, timezone
import hmac
import os
from pathlib import Path
import sys
import threading
import logging

log = logging.getLogger(__name__)

from fastapi import APIRouter, Header, HTTPException


def create_scheduler_router(db, coordinator_factory=None, clock=None):
    router = APIRouter(prefix='/algos', tags=['Paper scheduler'])
    instance = None
    startup_lock = threading.Lock()
    clock = clock or (lambda: datetime.now(timezone.utc))

    def get_coordinator():
        nonlocal instance
        with startup_lock:
            if instance is None:
                if coordinator_factory:
                    instance = coordinator_factory(db)
                else:
                    path = Path(__file__).resolve().parents[1] / 'algos/zen_credit'
                    if str(path) not in sys.path:
                        sys.path.insert(0, str(path))
                    from execution.coordinator import PaperCoordinator
                    instance = PaperCoordinator(db)
        return instance

    @router.post('/run-paper-cycle')
    def run_cycle(x_paper_scheduler_token: str | None = Header(None), x_scheduled_at: str | None = Header(None)):
        expected = os.getenv('PAPER_SCHEDULER_TOKEN', '')
        if not expected:
            raise HTTPException(503, 'Paper scheduler is not configured')
        if not x_paper_scheduler_token or not hmac.compare_digest(expected, x_paper_scheduler_token):
            raise HTTPException(401, 'Invalid scheduler credential')
        try:
            scheduled = datetime.fromisoformat((x_scheduled_at or '').replace('Z', '+00:00'))
            if scheduled.tzinfo is None:
                raise ValueError('timezone')
            age = (clock() - scheduled).total_seconds()
            if not -10 <= age <= 45:
                raise ValueError('stale event')
        except (ValueError, TypeError):
            raise HTTPException(422, 'Missing or stale scheduled timestamp') from None
        if db is None:
            raise HTTPException(503, 'Paper storage unavailable')
        try:
            result = get_coordinator().run_once()
        except Exception as exc:
            log.error('paper_scheduler_failed scheduled_at=%s error=%s', scheduled.isoformat(), type(exc).__name__)
            raise HTTPException(503, 'Paper evaluation unavailable; inspect backend logs and credentials') from None
        if result.get('status') == 'busy':
            raise HTTPException(409, 'Another paper cycle is running')
        if result.get('status') == 'error':
            # Only compact status/reason fields, never quote payloads or credentials.
            raise HTTPException(503, {'status': 'error', 'strategies': {key: item.get('status') for key, item in result.get('strategies', {}).items()}})
        return {'status': 'ok', 'execution': 'paper_only', 'strategies': {key: item.get('status') for key, item in result.get('strategies', {}).items()}}

    return router
