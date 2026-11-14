r"""One-off setup for the private Polymarket section. Writes only to its own Firestore documents.

  .venv\Scripts\python.exe seed.py --grant someone@example.com     # allow an email to see the section
  .venv\Scripts\python.exe seed.py --revoke someone@example.com
  .venv\Scripts\python.exe seed.py --catalog                       # publish backtest summaries
  .venv\Scripts\python.exe seed.py --show

Access lives in Firestore document feature_access/polymarket_algos {emails: [...]}; you can
also edit that list by hand in the Firebase console. The API re-reads it within a minute.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from store import firestore_client, iso   # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--grant", action="append", default=[])
    ap.add_argument("--revoke", action="append", default=[])
    ap.add_argument("--catalog", action="store_true")
    ap.add_argument("--show", action="store_true")
    a = ap.parse_args()
    db = firestore_client()
    ref = db.collection("feature_access").document("polymarket_algos")
    if a.grant or a.revoke:
        doc = ref.get()
        emails = set((doc.to_dict() or {}).get("emails", [])) if doc.exists else set()
        emails |= {e.strip().lower() for e in a.grant}
        emails -= {e.strip().lower() for e in a.revoke}
        ref.set({"emails": sorted(emails), "updated_at": iso()})
    if a.catalog:
        for path in sorted((Path(__file__).resolve().parent / "backtests").glob("*.json")):
            db.collection("poly_catalog").document(path.stem).set({**json.loads(path.read_text()), "published_at": iso()})
            print("published", path.stem)
    doc = ref.get()
    print("access:", (doc.to_dict() or {}).get("emails") if doc.exists else "no document (section hidden for everyone)")
    if a.show:
        for d in db.collection("poly_paper_state").stream():
            s = d.to_dict()
            print(d.id, {k: s.get(k) for k in ("equity", "cash", "realized_pnl", "n_settled", "updated_at")}, "open:", len(s.get("positions", [])))


if __name__ == "__main__":
    main()
