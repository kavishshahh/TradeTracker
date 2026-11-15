"""Paper accounts persisted in Firestore, in collections used only by this folder:

  poly_paper_state/{strategy}   account, positions, recent fills, settled bets, equity curve, heartbeat
  poly_paper_trades/{id}        every paper buy and every settlement, one document each, kept forever
  poly_catalog/{strategy}       backtest summary (written by seed.py)
  feature_access/polymarket_algos   {emails: [...]} - who may see the section (written by seed.py)
  poly_worker/lease             which worker process currently trades the accounts (lease.py)
  poly_paper_archive/{strategy}_v{n}   the account as it stood when its rules changed
"""
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import threading
import time

from pmq.core import Portfolio

STATE = "poly_paper_state"
TRADES = "poly_paper_trades"
ARCHIVE = "poly_paper_archive"
KEEP_FILLS, KEEP_SETTLED, KEEP_CURVE = 150, 300, 600
CURVE_EVERY = 1800
META_KEYS = ("outcome_name", "token_id", "event_slug", "end", "entry_price")


def iso(t=None):
    return datetime.fromtimestamp(t or time.time(), timezone.utc).isoformat()


def firestore_client():
    from dotenv import load_dotenv
    import firebase_admin
    from firebase_admin import credentials, firestore
    backend = Path(__file__).resolve().parents[1] / "backend"
    load_dotenv(backend / ".env")
    if not firebase_admin._apps:
        raw = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
        source = json.loads(raw) if raw else os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH", str(backend / "firebase-service-account.json"))
        firebase_admin.initialize_app(credentials.Certificate(source))
    return firestore.client()


class Account:
    """One strategy's paper account: a Portfolio plus the document that mirrors it."""
    def __init__(self, db, strategy, bankroll):
        self.db, self.s = db, strategy
        doc = db.collection(STATE).document(strategy.name).get()
        d = doc.to_dict() if doc.exists else None
        version = getattr(strategy, "account_version", 1)
        previous = []
        if d and "start_cash" in d and d.get("account_version", 1) != version:
            # The rules changed: keep the old account as a record and start a fresh one, so results
            # from different rules are never mixed.
            old = d.get("account_version", 1)
            db.collection(ARCHIVE).document(f"{strategy.name}_v{old}").set(json.loads(json.dumps(d, default=str)))
            previous = d.get("previous", []) + [dict(
                version=old, started_at=d.get("started_at"), ended_at=iso(), start_cash=d.get("start_cash"),
                equity=d.get("equity"), realized_pnl=d.get("realized_pnl"), n_settled=d.get("n_settled", 0),
                n_wins=d.get("n_wins", 0), open_at_end=len(d.get("positions", [])))]
            d = None
        if not d or "start_cash" not in d:
            d = dict(strategy=strategy.name, start_cash=bankroll, cash=bankroll, started_at=iso(), positions=[],
                     fills=[], settled=[], equity_curve=[], realized_pnl=0.0, n_settled=0, n_wins=0, n_fills=0,
                     account_version=version, previous=previous)
        self.d = d
        self.pf = Portfolio(d["start_cash"])
        self.pf.cash = d["cash"]
        self.meta = {}
        for p in d["positions"]:
            k = (p["cid"], p["outcome"])
            self.pf.pos[k] = dict(shares=p["shares"], cost=p["cost"], question=p["question"], opened=p["opened"])
            self.meta[k] = {key: p.get(key) for key in META_KEYS}
        self.recent_entries = []      # timestamps of recent fills, for pacing
        self.pending = []             # (doc id, trade record) not yet written to the permanent ledger
        self._flush_lock = threading.Lock()
        self.last_mark = {k: p.get("mark") for k, p in ((((p["cid"], p["outcome"])), p) for p in d["positions"]) if p.get("mark") is not None}
        if not d.get("ledger_started"):
            # First run with the ledger: copy the trades already in the account document.
            for row in d["fills"]:
                self._queue("fill", row)
            for row in d["settled"]:
                self._queue("settled", row)
            d["ledger_started"] = iso()

    def _queue(self, kind, row):
        doc_id = f"{self.s.name}_{int(row['t'] * 1000)}_{row['cid'][2:14]}_{row['outcome']}_{kind}"
        self.pending.append((doc_id, {**row, "kind": kind, "strategy": self.s.name,
                                      "version": self.d.get("account_version", 1)}))

    def held_events(self):
        return {m.get("event_slug") for m in self.meta.values() if m.get("event_slug")}

    def record_fill(self, fill, market):
        self.pf.apply(fill)
        self.meta[(fill.cid, fill.outcome)] = dict(
            outcome_name=market["outcomes"][fill.outcome], token_id=market["token_ids"][fill.outcome],
            event_slug=market.get("event_slug"), end=market.get("end"), entry_price=fill.price)
        self.d["fills"].append({**asdict(fill), "ts": iso(fill.t), "outcome_name": market["outcomes"][fill.outcome]})
        self.d["n_fills"] = self.d.get("n_fills", 0) + 1
        self._queue("fill", self.d["fills"][-1])
        self.recent_entries.append(fill.t)

    def settle(self, cid, payouts, now):
        names = {o: self.meta.get((c, o), {}).get("outcome_name") for (c, o) in list(self.pf.pos) if c == cid}
        before = len(self.pf.settled)
        self.pf.settle(cid, payouts, now)
        for r in self.pf.settled[before:]:
            self.d["settled"].append({**r, "ts": iso(r["t"]), "outcome_name": names.get(r["outcome"]),
                                      "cost": round(r["cost"], 4), "payout": round(r["payout"], 4), "pnl": round(r["pnl"], 4)})
            self.d["realized_pnl"] = round(self.d.get("realized_pnl", 0) + r["pnl"], 4)
            self.d["n_settled"] = self.d.get("n_settled", 0) + 1
            self.d["n_wins"] = self.d.get("n_wins", 0) + (1 if r["pnl"] > 0 else 0)
            self._queue("settled", self.d["settled"][-1])
            self.meta.pop((cid, r["outcome"]), None)
        return len(self.pf.settled) - before

    def document(self, marks, extra):
        pf, d = self.pf, self.d
        # A book can be briefly missing (reconnect, new subscription). Use the last bid seen rather than
        # snapping the position back to cost; positions never marked at all are still valued at cost.
        for k, v in marks.items():
            if v is not None:
                self.last_mark[k] = v
        self.last_mark = {k: v for k, v in self.last_mark.items() if k in pf.pos}
        marks = {k: (v if v is not None else self.last_mark.get(k)) for k, v in marks.items()}
        d["positions"] = [dict(cid=c, outcome=o, shares=round(p["shares"], 4), cost=round(p["cost"], 4), question=p["question"],
                               opened=p["opened"], mark=marks.get((c, o)), **self.meta.get((c, o), {}))
                          for (c, o), p in pf.pos.items()]
        equity = pf.equity({k: v for k, v in marks.items() if v is not None})
        curve = d["equity_curve"]
        if not curve or time.time() - curve[-1]["t"] >= CURVE_EVERY:
            curve.append(dict(t=int(time.time()), equity=round(equity, 4)))
        d.update(cash=round(pf.cash, 4), equity=round(equity, 4), exposure=round(pf.exposure(), 4),
                 fills=d["fills"][-KEEP_FILLS:], settled=d["settled"][-KEEP_SETTLED:], equity_curve=curve[-KEEP_CURVE:],
                 updated_at=iso(), status="in_positions" if pf.pos else "scanning", execution="paper_only",
                 name=self.s.name, description=self.s.description, origin=self.s.origin,
                 params={k: v for k, v in self.s.params.items() if not k.startswith("_")}, **extra)
        return json.loads(json.dumps(d, default=str))

    def flush_ledger(self):
        """Write queued trades to the permanent ledger. A trade stays queued until its write succeeds."""
        with self._flush_lock:        # never two writers on the queue, even a thread orphaned at shutdown
            while self.pending:
                doc_id, row = self.pending[0]
                self.db.collection(TRADES).document(doc_id).set(json.loads(json.dumps(row, default=str)))
                self.pending.pop(0)

    def save(self, marks, extra):
        self.flush_ledger()
        self.db.collection(STATE).document(self.s.name).set(self.document(marks, extra))


class MemoryDb:
    """Firestore stand-in for --dry runs: nothing leaves the process."""
    def __init__(self):
        self.docs = {}

    def collection(self, name):
        return _Col(self, name)


class _Col:
    def __init__(self, db, name):
        self.db, self.name = db, name

    def document(self, doc_id):
        return _Doc(self.db, f"{self.name}/{doc_id}")


class _Doc:
    def __init__(self, db, path):
        self.db, self.path, self.exists = db, path, path in db.docs

    def get(self):
        return _Doc(self.db, self.path)

    def to_dict(self):
        return json.loads(json.dumps(self.db.docs.get(self.path)))

    def set(self, data, merge=False):
        self.db.docs[self.path] = {**(self.db.docs.get(self.path, {}) if merge else {}), **json.loads(json.dumps(data, default=str))}
