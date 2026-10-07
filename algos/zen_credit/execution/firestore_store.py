"""Firestore-only paper execution state, isolated by strategy.

All writes use a transactional lease with a fencing token. Snapshot documents
contain one minute of strike rows, avoiding one read per strike. Closed totals
are updated atomically with the exit, not computed from a truncated ledger.
"""
from contextlib import contextmanager
from dataclasses import fields
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
import uuid
import pandas as pd
from execution.store import PositionRecord, StoreUnavailable, SNAPSHOT_COLUMNS, _aware
from utils.time import IST


def clean(value):
    if isinstance(value, dict): return {key: clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)): return [clean(item) for item in value]
    if isinstance(value, datetime):
        if value.tzinfo is None: raise ValueError('Firestore timestamps must be timezone aware')
        return value.astimezone(timezone.utc)
    if isinstance(value, date): return value.isoformat()
    if hasattr(value, 'item'): return clean(value.item())
    if isinstance(value, float) and not math.isfinite(value): return None
    return value


class FirestoreStore:
    def __init__(self, strategy_name, client=None, transaction_runner=None, now=None, lease_seconds=300):
        if not strategy_name or '/' in strategy_name: raise ValueError('Invalid strategy namespace')
        if client is None:
            from execution.firebase_client import get_firestore_client
            client = get_firestore_client()
        self.client = client
        self.strategy_name = strategy_name
        self.root = client.collection('algo_engines').document(strategy_name)
        self.runtime = self.root.collection('control').document('runtime')
        self.lease = self.root.collection('control').document('lease')
        self._owner = None
        self._now = now or (lambda: datetime.now(timezone.utc))
        self.lease_seconds = lease_seconds
        self._snapshot_cache = {}
        self._history_loaded_since = None
        if transaction_runner is None:
            from google.cloud.firestore import transactional
            transaction_runner = lambda fn: transactional(fn)(client.transaction(max_attempts=5))
        self._run = transaction_runner

    def _call(self, fn):
        try: return fn()
        except StoreUnavailable: raise
        except Exception as exc:
            if type(exc).__module__.startswith('google.') or (exc.__cause__ is not None and type(exc.__cause__).__module__.startswith('google.')):
                raise StoreUnavailable(f'Firestore unavailable ({type(exc).__name__})') from None
            raise

    def _get(self, ref, tx=None):
        # Let the SDK see transaction conflicts so its retry decorator can rerun.
        read = lambda: ref.get(transaction=tx, timeout=15, retry=None)
        snap = read() if tx is not None else self._call(read)
        return snap.to_dict() if snap.exists else None

    def _stream(self, query): return self._call(lambda: list(query.stream(timeout=30, retry=None)))
    def ensure_schema(self): self._get(self.runtime)
    def close(self): pass

    @contextmanager
    def session(self): yield self

    @contextmanager
    def lock(self):
        if self._owner is not None: raise RuntimeError('Nested Firestore lease is not supported')
        owner = uuid.uuid4().hex
        def acquire(tx):
            existing = self._get(self.lease, tx)
            now = self._now()
            if existing and existing['expires_at'] > now: return False
            tx.set(self.lease, {'owner': owner, 'expires_at': now + timedelta(seconds=self.lease_seconds)})
            return True
        acquired = self._call(lambda: self._run(acquire))
        if acquired: self._owner = owner
        try: yield acquired
        finally:
            if acquired:
                self._owner = None
                def release(tx):
                    existing = self._get(self.lease, tx)
                    if existing and existing.get('owner') == owner: tx.delete(self.lease)
                self._call(lambda: self._run(release))

    def _write(self, fn):
        if self._owner is None:
            with self.lock() as acquired:
                if not acquired: raise StoreUnavailable('Firestore strategy lease is busy')
                return self._write(fn)
        owner = self._owner
        def fenced(tx):
            lease = self._get(self.lease, tx)
            now = self._now()
            if not lease or lease.get('owner') != owner or lease['expires_at'] <= now:
                raise StoreUnavailable('Firestore lease expired or was replaced; write refused')
            result = fn(tx)
            tx.set(self.lease, {'owner': owner, 'expires_at': now + timedelta(seconds=self.lease_seconds)})
            return result
        return self._call(lambda: self._run(fenced))

    def _key(self, value): return hashlib.sha256(str(value).encode()).hexdigest()
    def claim_minute(self, minute):
        ref = self.root.collection('runs').document(self._key(clean(minute).isoformat()))
        def claim(tx):
            if self._get(ref, tx): return False
            tx.set(ref, {'minute':clean(minute),'result':'started','detail':''})
            return True
        return self._write(claim)

    def finish_minute(self, minute, result, detail=''):
        ref = self.root.collection('runs').document(self._key(clean(minute).isoformat()))
        def finish(tx):
            data = self._get(ref, tx)
            if data:
                data.update(result=result, detail=detail[:2000]); tx.set(ref, data)
        self._write(finish)

    def set_state(self, key, value):
        ref = self.root.collection('state').document(self._key(key))
        self._write(lambda tx: tx.set(ref, {'key':key,'value':value}))
    def get_state(self, key):
        data = self._get(self.root.collection('state').document(self._key(key)))
        return data['value'] if data else None
    def holiday_cache_get(self):
        raw = self.get_state('nse_holidays'); return json.loads(raw) if raw else None
    def holiday_cache_set(self, value): self.set_state('nse_holidays', json.dumps(value))

    def save_snapshot_rows(self, rows):
        grouped = {}
        for row in rows:
            row = clean({key:row.get(key) for key in SNAPSHOT_COLUMNS})
            minute = row['minute']; key = self._key(minute.isoformat())
            grouped.setdefault(key, {'minute':minute,'rows':{}})['rows'][f"{row['expiry']}_{row['strike']}"] = row
        def save(tx):
            existing = {key:self._get(self.root.collection('snapshots').document(key), tx) for key in grouped}
            changed = {}; count = 0
            for key, incoming in grouped.items():
                document = existing[key] or {'minute':incoming['minute'],'rows':{}}
                for row_key, row in incoming['rows'].items():
                    if row_key not in document['rows']: document['rows'][row_key] = row; count += 1
                if len(json.dumps(document, default=str).encode()) > 750_000:
                    raise ValueError('Snapshot minute exceeds safe Firestore document size')
                changed[key] = document
            for key, document in changed.items(): tx.set(self.root.collection('snapshots').document(key), document)
            return count, changed
        count, changed = self._write(save)
        self._snapshot_cache.update(changed)
        return count

    def load_snapshots(self, since):
        since = clean(since)
        self._snapshot_cache = {key:doc for key,doc in self._snapshot_cache.items() if doc['minute'] >= since}
        # Load all required history on cold start, then only the latest minute onward.
        # Keep the last minute inclusive because its second expiry may arrive later.
        cursor = since if self._history_loaded_since is None or since < self._history_loaded_since else max(
            (doc['minute'] for doc in self._snapshot_cache.values()), default=since)
        query = self.root.collection('snapshots').where('minute','>=',cursor).order_by('minute')
        for snap in self._stream(query): self._snapshot_cache[snap.id] = snap.to_dict()
        self._history_loaded_since = since
        rows = [row for doc in self._snapshot_cache.values() for row in doc['rows'].values()]
        frame = pd.DataFrame(rows, columns=SNAPSHOT_COLUMNS)
        if not frame.empty:
            frame['minute'] = pd.to_datetime(frame.minute,utc=True).dt.tz_convert(IST)
            frame['expiry'] = pd.to_datetime(frame.expiry).dt.date
            frame = frame.sort_values(['minute','expiry','strike']).reset_index(drop=True)
        return frame

    def prune_snapshots(self, older_than_days=10):
        # Optional maintenance; bounded cache retention is already applied on reads.
        cutoff = self._now() - timedelta(days=older_than_days)
        query = self.root.collection('snapshots').where('minute','<',cutoff).limit(200)
        refs = [doc.reference for doc in self._stream(query)]
        if refs:
            self._write(lambda tx: [tx.delete(ref) for ref in refs])

    @staticmethod
    def _record(data):
        if data is None: return None
        data = dict(data)
        data['expiry'] = date.fromisoformat(data['expiry']) if isinstance(data['expiry'],str) else data['expiry']
        for key in ('entry_ts','exit_due','exit_ts'): data[key] = _aware(data.get(key))
        return PositionRecord(**{field.name:data.get(field.name) for field in fields(PositionRecord)})

    def open_position_row(self):
        state = self._get(self.runtime) or {}
        row_id = state.get('open_id')
        return self._record(self._get(self.root.collection('positions').document(str(row_id)))) if row_id is not None else None

    def insert_position(self, p, direction):
        signal = self.root.collection('signals').document(self._key(p.signal_id))
        def insert(tx):
            runtime = self._get(self.runtime,tx) or {}
            recorded = self._get(signal,tx)
            if runtime.get('open_id') is not None or recorded: return None
            row_id = runtime.get('last_id',0) + 1
            values = {field.name:None for field in fields(PositionRecord)}
            values.update({key:getattr(p,key) for key in ('signal_id','entry_ts','expiry','option_type',
                'sell_strike','buy_strike','lots','lot_size','units','spot_at_entry','sell_price','buy_price',
                'net_credit','stop_loss','target','max_loss','max_profit','exit_due','alpha','alpha2','allocated_capital')})
            values.update(id=row_id,status='open',strategy_state='IN_POSITION',direction=direction,
                entry_spread_price=p.net_credit,entry_email_status='pending',entry_email_attempts=0,
                exit_email_status='none',exit_email_attempts=0)
            values = clean(values)
            runtime.update(last_id=row_id,open_id=row_id)
            tx.set(self.runtime,runtime); tx.set(signal,{'position_id':row_id})
            tx.set(self.root.collection('positions').document(str(row_id)),values)
            tx.set(self.root.collection('emails').document(f'{row_id}_entry'),{'row_id':row_id,'kind':'entry'})
            return values
        return self._record(self._write(insert))

    def close_position(self, row_id, ev):
        ref = self.root.collection('positions').document(str(row_id))
        def close(tx):
            runtime = self._get(self.runtime,tx) or {}
            row = self._get(ref,tx)
            if not row or row['status'] != 'open' or runtime.get('open_id') != row_id: return None
            row.update(status='closed',strategy_state='FLAT',exit_ts=clean(ev.exit_ts),
                exit_value=clean(ev.exit_value),exit_reason=ev.reason,pnl=clean(ev.pnl),
                pnl_pct=clean(ev.pnl_pct),exit_email_status='pending')
            stats = runtime.get('stats',{'closed_trades':0,'winners':0,'unknown_pnl':0,'realized_pnl':0.0})
            stats['closed_trades'] += 1
            if row['pnl'] is None: stats['unknown_pnl'] += 1
            else:
                stats['realized_pnl'] += row['pnl']; stats['winners'] += int(row['pnl'] > 0)
            runtime.update(open_id=None,stats=stats)
            tx.set(ref,row); tx.set(self.runtime,runtime)
            tx.set(self.root.collection('closed').document(str(row_id)),row)
            tx.set(self.root.collection('emails').document(f'{row_id}_exit'),{'row_id':row_id,'kind':'exit'})
            return row
        return self._record(self._write(close))

    def closed_positions(self, limit=50):
        query = self.root.collection('closed').order_by('id',direction='DESCENDING').limit(limit)
        return [self._record(snap.to_dict()) for snap in self._stream(query)]

    def set_email_status(self, row_id, kind, status):
        if kind not in ('entry','exit'): raise ValueError(kind)
        ref = self.root.collection('positions').document(str(row_id))
        queue = self.root.collection('emails').document(f'{row_id}_{kind}')
        def update(tx):
            row = self._get(ref,tx)
            if row is None: return
            row[f'{kind}_email_status'] = status; row[f'{kind}_email_attempts'] += 1
            tx.set(ref,row)
            if row['status']=='closed': tx.set(self.root.collection('closed').document(str(row_id)),row)
            if status=='sent' or row[f'{kind}_email_attempts'] >= 5: tx.delete(queue)
        self._write(update)

    def pending_emails(self, max_attempts=5):
        result = []
        for snap in self._stream(self.root.collection('emails')):
            item = snap.to_dict(); row = self._record(self._get(self.root.collection('positions').document(str(item['row_id']))))
            kind = item['kind']
            if row and getattr(row,f'{kind}_email_status') in ('pending','failed') and getattr(row,f'{kind}_email_attempts') < max_attempts:
                result.append((kind,row))
        return result

    def paper_totals_and_mark(self, opened):
        runtime = self._get(self.runtime) or {}
        totals = runtime.get('stats',{'closed_trades':0,'winners':0,'unknown_pnl':0,'realized_pnl':0.0})
        mark = None
        if opened:
            frame = self.load_snapshots(self._now() - timedelta(days=10))
            side = 'ce_ltp' if opened.option_type=='CE' else 'pe_ltp'
            if not frame.empty:
                selected = frame.loc[(frame.expiry==opened.expiry)&(frame.minute<=self._now())]
                sold = selected.loc[selected.strike==opened.sell_strike,['minute',side]]
                bought = selected.loc[selected.strike==opened.buy_strike,['minute',side]]
                paired = sold.merge(bought,on='minute',suffixes=('_sell','_buy')).dropna()
                if not paired.empty:
                    quote = paired.sort_values('minute').iloc[-1]
                    mark = {'minute':quote.minute,'sell':float(quote[f'{side}_sell']),'buy':float(quote[f'{side}_buy'])}
        return totals,mark

    def publish_dashboard(self, payload):
        ref = self.client.collection('algo_paper_state').document(self.strategy_name)
        self._write(lambda tx: tx.set(ref,clean(payload)))
