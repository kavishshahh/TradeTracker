"""Insert verified catalogue metadata once; existing DB records are preserved.
Run from the repo root: algos/.venv/Scripts/python.exe backend/seed_algos_catalog.py
The JSON is migration input only. Strategy execution remains in Python.
"""
import json
import sys
from pathlib import Path

def main():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / 'algos/zen_credit'))
    from execution.firebase_client import get_firestore_client
    from google.api_core.exceptions import AlreadyExists
    db = get_firestore_client()
    records = json.loads((Path(__file__).parent / 'seed_data/algos_catalog.json').read_text(encoding='utf-8'))
    for record in records:
        ref = db.collection('algo_catalog').document(record['id'])
        try:
            ref.create(record)
            status = 'inserted'
        except AlreadyExists:
            status = 'preserved existing'
        saved = ref.get().to_dict()
        print(record['id'], status, 'monthly rows:', len(saved.get('monthly', [])), 'trades:', saved.get('metrics', {}).get('trade_count'))

if __name__ == '__main__':
    main()
