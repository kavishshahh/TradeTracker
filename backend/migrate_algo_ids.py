"""Copy Firestore algo documents from the old strategy ids to the renamed ones.

Old ids: strategy_01, strategy_02, strategy_03.
New ids: zen_strategy_01, zen_strategy_02, ratio_strategy_03.

Run from the repo root (dry run by default; nothing is written):
    algos/.venv/Scripts/python.exe backend/migrate_algo_ids.py
    algos/.venv/Scripts/python.exe backend/migrate_algo_ids.py --apply
    algos/.venv/Scripts/python.exe backend/migrate_algo_ids.py --delete-old

--apply copies, never deletes: algo_catalog/{id}, algo_paper_state/{id}, every
algo_engines/{id}/* subcollection (control, positions, closed, signals, runs,
snapshots, state, emails) and users/*/algo_follows/{id}. Existing documents at
the new id are left untouched. Stop the paper worker/scheduler before applying
so a live cycle cannot write to the old namespace mid-copy.

--delete-old removes the old-id documents only after checking that every one of
them has a counterpart under the new id (same document ids in every
subcollection); any missing copy aborts before a single delete. Subcollection
documents are deleted explicitly because Firestore does not cascade.
"""
import argparse
import sys
from pathlib import Path

RENAMES = {'strategy_01': 'zen_strategy_01', 'strategy_02': 'zen_strategy_02', 'strategy_03': 'ratio_strategy_03'}
ENGINE_SUBCOLLECTIONS = ('control', 'positions', 'closed', 'signals', 'runs', 'snapshots', 'state', 'emails')
BATCH = 400


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


def copy_collection(src, dst, apply, log, batch_size=BATCH):
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


def old_references(db, old, new):
    """Yield (old_ref, new_ref) pairs for every old-id document that exists."""
    for collection in ('algo_catalog', 'algo_paper_state', 'algo_engines'):
        ref = db.collection(collection).document(old)
        if ref.get().exists:
            yield ref, db.collection(collection).document(new)
    old_engine = db.collection('algo_engines').document(old)
    new_engine = db.collection('algo_engines').document(new)
    for sub in ENGINE_SUBCOLLECTIONS:
        for doc in old_engine.collection(sub).stream():
            yield doc.reference, new_engine.collection(sub).document(doc.id)
    for user in db.collection('users').stream():
        ref = user.reference.collection('algo_follows').document(old)
        if ref.get().exists:
            yield ref, user.reference.collection('algo_follows').document(new)


def delete_old(db, log):
    pairs = []
    missing = []
    for old, new in RENAMES.items():
        for old_ref, new_ref in old_references(db, old, new):
            pairs.append(old_ref)
            if not new_ref.get().exists:
                missing.append((old_ref.path, new_ref.path))
    if missing:
        for o, n in missing[:20]:
            log(f'MISSING copy: {o} -> {n}')
        raise SystemExit(f'{len(missing)} old documents have no copy under the new id; nothing deleted')
    log(f'verified {len(pairs)} old documents all have copies; deleting')
    for i in range(0, len(pairs), BATCH):
        batch = db.batch()
        for ref in pairs[i:i + BATCH]:
            batch.delete(ref)
        batch.commit()
        log(f'deleted {min(i + BATCH, len(pairs))} / {len(pairs)}')
    return len(pairs)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--apply', action='store_true', help='write the copies; default is a dry run')
    parser.add_argument('--delete-old', action='store_true', help='delete old-id documents after verifying their copies exist')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / 'algos/zen_credit'))
    from execution.firebase_client import get_firestore_client
    db = get_firestore_client()
    log = print
    if args.delete_old:
        count = delete_old(db, log)
        print(f'Deleted {count} old-id documents. Remaining catalogue ids: {sorted(d.id for d in db.collection("algo_catalog").stream())}')
        return
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
