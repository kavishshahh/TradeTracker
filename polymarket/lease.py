"""Single-worker guard. Only one paper worker may trade the accounts at a time (for example the
cloud worker and a copy left running on a PC). The holder is recorded in Firestore document
poly_worker/lease and renewed with every heartbeat; a holder that stops renewing for TTL seconds
is considered gone and can be replaced. A clean shutdown releases the lease at once, so a
redeploy hands over in seconds.
"""
import os
import socket
import time
import uuid

COLLECTION, DOC = "poly_worker", "lease"
TTL = 300                 # seconds without renewal before another worker may take over


class Lease:
    def __init__(self, db, ttl=TTL, clock=time.time):
        self.db, self.ttl, self.clock = db, ttl, clock
        self.owner = f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:6]}"
        self.renewed_at = 0.0
        self.holder = None            # who holds it when we do not

    def _ref(self):
        return self.db.collection(COLLECTION).document(DOC)

    def _claim(self, read, write):
        """Take or renew the lease unless a live other owner has it. Returns True when it is ours."""
        now = self.clock()
        cur = read() or {}
        if cur.get("owner") not in (None, self.owner) and now - float(cur.get("renewed_at", 0)) < self.ttl:
            self.holder = cur.get("owner")
            return False
        write({"owner": self.owner, "renewed_at": now,
               "started_at": cur.get("started_at", now) if cur.get("owner") == self.owner else now})
        self.renewed_at, self.holder = now, None
        return True

    def acquire(self):
        """Blocking Firestore call; atomic on a real Firestore client."""
        ref = self._ref()
        if hasattr(self.db, "transaction"):
            from google.cloud import firestore

            @firestore.transactional
            def txn(transaction):
                snap = ref.get(transaction=transaction)
                return self._claim(lambda: snap.to_dict() if snap.exists else None,
                                   lambda data: transaction.set(ref, data))
            return txn(self.db.transaction())
        snap = ref.get()                                  # in-memory store used by tests and --dry
        return self._claim(lambda: snap.to_dict() if snap.exists else None, ref.set)

    renew = acquire

    def fresh(self, margin=60):
        """True while our last successful renewal is recent enough that nobody else can have taken over."""
        return self.clock() - self.renewed_at < self.ttl - margin

    def release(self):
        """Give the lease up on a clean shutdown, but only if it is still ours."""
        ref = self._ref()
        snap = ref.get()
        if snap.exists and (snap.to_dict() or {}).get("owner") == self.owner:
            ref.set({"owner": None, "renewed_at": 0, "released_by": self.owner})
