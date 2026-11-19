"""Write the short public `summary` of each strategy to the live catalogue.
Run from the repo root: algos/.venv/Scripts/python.exe backend/set_catalog_summaries.py
One merge write per strategy and no bulk reads. seed_algos_catalog.py never touches
existing records, so this is how a new summary reaches Firestore. The summary is what
everyone but the owner sees as the description; it must not describe the method.
"""
import json
import sys
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / 'algos/zen_credit'))
    from execution.firebase_client import get_firestore_client
    db = get_firestore_client()
    records = json.loads((Path(__file__).parent / 'seed_data/algos_catalog.json').read_text(encoding='utf-8'))
    for record in records:
        if not record.get('summary'):
            print(record['id'], 'has no summary in the seed; skipped')
            continue
        db.collection('algo_catalog').document(record['id']).set({'summary': record['summary']}, merge=True)
        print(record['id'], 'summary set')


if __name__ == '__main__':
    main()
