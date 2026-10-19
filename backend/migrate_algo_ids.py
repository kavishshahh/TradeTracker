"""Copy Firestore algo documents from the old strategy ids to the renamed ones.

Old ids: strategy_01, strategy_02, strategy_03.
New ids: zen_strategy_01, zen_strategy_02, ratio_strategy_03.

Run from the repo root (dry run by default; nothing is written):
    algos/.venv/Scripts/python.exe backend/migrate_algo_ids.py
    algos/.venv/Scripts/python.exe backend/migrate_algo_ids.py --apply

Copies, never deletes: algo_catalog/{id}, algo_paper_state/{id}, every
algo_engines/{id}/* subcollection (control, positions, closed, signals, runs,
snapshots, state, emails) and users/*/algo_follows/{id}. Existing documents at
the new id are left untouched. Stop the paper worker/scheduler before applying
so a live cycle cannot write to the old namespace mid-copy; delete the old
documents yourself once the dashboard shows the renamed strategies.
"""
import argparse
import sys
from pathlib import Path

RENAMES = {'strategy_01': 'zen_strategy_01', 'strategy_02': 'zen_strategy_02', 'strategy_03': 'ratio_strategy_03'}
ENGINE_SUBCOLLECTIONS = ('control', 'positions', 'closed', 'signals', 'runs', 'snapshots', 'state', 'emails')


def copy_document(src, dst, apply, log):
    snap = src.get()
    if not snap.exists:
        return 0
    if dst.get().exists:
        log(f'keep existing {dst.path}')
        return 0
    log(f'copy {src.path} -> {dst.path}')
    if apply:
        dst.set(snap.to_dict())
    return 1


def copy_collection(src, dst, apply, log, batch_size=400):
    count = 0
    docs = list(src.stream())
    for i in range(0, len(docs), batch_size):
        chunk = docs[i:i + batch_size]
        for doc in chunk:
            target = dst.document(doc.id)
            if target.get().exists:
                continue
            if apply:
                target.set(doc.to_dict())
            count += 1
    log(f'{"copied" if apply else "would copy"} {count} of {len(docs)} documents {src.id} -> {dst.id}')
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--apply', action='store_true', help='write the copies; default is a dry run')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / 'algos/zen_credit'))
    from execution.firebase_client import get_firestore_client
    db = get_firestore_client()
    log = print
    total = 0
    for old, new in RENAMES.items():
        for collection in ('algo_catalog', 'algo_paper_state'):
            total += copy_document(db.collection(collection).document(old), db.collection(collection).document(new), args.apply, log)
        old_engine = db.collection('algo_engines').document(old)
        new_engine = db.collection('algo_engines').document(new)
        total += copy_document(old_engine, new_engine, args.apply, log)
        for sub in ENGINE_SUBCOLLECTIONS:
            total += copy_collection(old_engine.collection(sub), new_engine.collection(sub), args.apply, log)
        for user in db.collection('users').stream():
            follows = user.reference.collection('algo_follows')
            total += copy_document(follows.document(old), follows.document(new), args.apply, log)
    print(('Applied' if args.apply else 'Dry run complete; would write') + f' {total} documents. Old documents are untouched.')


if __name__ == '__main__':
    main()
