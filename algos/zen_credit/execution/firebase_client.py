"""Reuse TradeBud's server credentials without copying or exposing secrets."""
import json
import os
from pathlib import Path


def get_firestore_client():
    import firebase_admin
    from firebase_admin import credentials, firestore
    from dotenv import dotenv_values
    repo = Path(__file__).resolve().parents[3]
    values = {}
    for path in (repo / 'backend/.env',):
        values.update({key: value for key, value in dotenv_values(path).items() if value not in (None, "")})
    values.update({key: value for key, value in os.environ.items() if value})
    try:
        app = firebase_admin.get_app('tradebud-algos')
    except ValueError:
        raw = values.get('FIREBASE_SERVICE_ACCOUNT_JSON')
        path = values.get('FIREBASE_SERVICE_ACCOUNT_PATH')
        if raw:
            cred = credentials.Certificate(json.loads(raw))
        elif path:
            candidate = Path(path)
            if not candidate.is_absolute(): candidate = repo / 'backend' / candidate
            cred = credentials.Certificate(str(candidate))
        else:
            cred = credentials.ApplicationDefault()
        app = firebase_admin.initialize_app(cred, name='tradebud-algos')
    return firestore.client(app=app)
