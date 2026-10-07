"""Offline serializable transaction fixtures; never use production credentials."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import threading
import pandas as pd
import pytest
from execution.firestore_store import FirestoreStore
from execution.store import StoreUnavailable, is_db_error
from strategy.engine import Position, ExitEvent


class Snapshot:
    def __init__(self, ref, value): self.reference=ref; self.id=ref.path.split('/')[-1]; self.value=deepcopy(value); self.exists=value is not None
    def to_dict(self): return deepcopy(self.value)


class Ref:
    def __init__(self, db, path): self.db=db; self.path=path
    def collection(self,name): return Query(self.db,self.path+'/'+name)
    def get(self,transaction=None,**kwargs):
        if transaction and transaction.writes: raise AssertionError('Transaction read after write')
        return Snapshot(self,self.db.values.get(self.path))


class Query:
    def __init__(self,db,path,filters=(),sort=None,limit=None): self.db=db;self.path=path;self.filters=filters;self.sort=sort;self.count=limit
    def document(self,name): return Ref(self.db,self.path+'/'+name)
    def where(self,field,op,value): return Query(self.db,self.path,self.filters+((field,op,value),),self.sort,self.count)
    def order_by(self,field,direction=None): return Query(self.db,self.path,self.filters,(field,direction),self.count)
    def limit(self,value): return Query(self.db,self.path,self.filters,self.sort,value)
    def stream(self,**kwargs):
        items=[(key,value) for key,value in self.db.values.items() if key.startswith(self.path+'/') and '/' not in key[len(self.path)+1:]]
        for field,op,wanted in self.filters:
            items=[(key,value) for key,value in items if (value[field]>=wanted if op=='>=' else value[field]<wanted)]
        if self.sort: items.sort(key=lambda pair:pair[1][self.sort[0]],reverse=self.sort[1]=='DESCENDING')
        if self.count is not None:items=items[:self.count]
        return [Snapshot(Ref(self.db,key),value) for key,value in items]


class FakeDB:
    def __init__(self): self.values={};self.lock=threading.RLock()
    def collection(self,name):return Query(self,name)
    def run(self,fn):
        class Transaction:
            def __init__(self):self.writes=[]
            def set(self,ref,value):self.writes.append((ref.path,deepcopy(value)))
            def delete(self,ref):self.writes.append((ref.path,None))
        with self.lock:
            tx=Transaction();result=fn(tx)
            for key,value in tx.writes:
                if value is None:self.values.pop(key,None)
                else:self.values[key]=value
            return result


@pytest.fixture
def setup():
    db=FakeDB();clock=[datetime(2026,10,7,5,tzinfo=timezone.utc)]
    def store(name='strategy_01'):return FirestoreStore(name,db,db.run,lambda:clock[0],lease_seconds=30)
    return db,clock,store


def position(signal='test'):
    stamp=datetime(2026,10,7,5,tzinfo=timezone.utc)
    return Position(signal,stamp,date(2026,10,13),'CE',23000,23400,1,65,65,120,20,100,145,None,19500,6500,stamp+timedelta(days=1),alpha=.1,alpha2=.1)


def test_lease_exclusion_expiry_and_stale_writer_fencing(setup):
    db,clock,factory=setup;a=factory();b=factory()
    with a.lock() as acquired:
        assert acquired
        with b.lock() as acquired:assert not acquired
        clock[0]+=timedelta(seconds=31)
        with b.lock() as acquired:
            assert acquired
            with pytest.raises(StoreUnavailable):a.claim_minute(clock[0])
            b.set_state('owner','new')
        with pytest.raises(StoreUnavailable):a.set_state('bad','stale')
    assert b.get_state('owner')=='new' and b.get_state('bad') is None


def test_two_strategies_are_independent_and_minutes_idempotent(setup):
    db,clock,factory=setup;a=factory();b=factory('strategy_02')
    with a.lock(),b.lock():
        assert a.claim_minute(clock[0])
        assert not a.claim_minute(clock[0].astimezone(timezone(timedelta(hours=5,minutes=30))))
        assert b.claim_minute(clock[0])
        a.set_state('nse_holidays','a');b.set_state('nse_holidays','b')
    assert a.get_state('nse_holidays')=='a' and b.get_state('nse_holidays')=='b'


def test_single_open_position_duplicate_signal_and_atomic_exit_totals(setup):
    db,clock,factory=setup;store=factory()
    with store.lock():
        row=store.insert_position(position(),'bearish');assert row.target is None
        assert store.insert_position(position('other'),'bearish') is None
        exit=ExitEvent('target',clock[0],20,5200,1.625)
        assert store.close_position(row.id,exit).pnl==5200
        assert store.close_position(row.id,exit) is None
        assert store.insert_position(position(),'bearish') is None
        next_row=store.insert_position(position('other'),'bearish');assert next_row.id==2
        assert store.open_position_row().signal_id=='other'
        totals,_=store.paper_totals_and_mark(None)
        assert totals=={'closed_trades':1,'winners':1,'unknown_pnl':0,'realized_pnl':5200}
        assert len(store.closed_positions())==1


def test_failed_transaction_does_not_partially_apply_and_db_error_is_recognized(setup):
    db,clock,factory=setup;store=factory()
    with store.lock():
        def fail(tx):
            tx.set(store.runtime,{'bad':True});raise ValueError('abort')
        with pytest.raises(ValueError):store._write(fail)
    assert store._get(store.runtime) is None
    assert is_db_error(StoreUnavailable('offline'))


def row(minute,strike,ce,expiry=date(2026,10,13)):
    return {'minute':minute,'expiry':expiry,'strike':strike,'spot':23000.,'ce_ltp':ce,'pe_ltp':10.,'ce_cum_volume':100.,'pe_cum_volume':100.}


def test_cold_history_after_current_save_and_incremental_second_expiry(setup):
    db,clock,factory=setup;first=factory()
    first.save_snapshot_rows([row(clock[0]-timedelta(minutes=2),23000,120)])
    restarted=factory()
    restarted.save_snapshot_rows([row(clock[0],23000,110)])
    history=restarted.load_snapshots(clock[0]-timedelta(minutes=3))
    assert len(history)==2
    restarted.save_snapshot_rows([row(clock[0],23000,999),row(clock[0],23000,50,date(2026,10,20))])
    history=restarted.load_snapshots(clock[0]-timedelta(minutes=3))
    assert len(history)==3
    assert history.loc[history.expiry==date(2026,10,13),'ce_ltp'].tolist()==[120,110]
    assert history.minute.dt.tz is not None


def test_unknown_exit_pnl_is_not_zero_and_marks_require_same_minute(setup):
    db,clock,factory=setup;store=factory()
    with store.lock():
        opened=store.insert_position(position(),'bearish')
        store.save_snapshot_rows([row(clock[0],23000,100),row(clock[0]-timedelta(minutes=1),23400,20)])
        totals,mark=store.paper_totals_and_mark(opened);assert mark is None
        store.save_snapshot_rows([row(clock[0],23400,20)])
        totals,mark=store.paper_totals_and_mark(opened);assert mark['sell']-mark['buy']==80
        store.close_position(opened.id,ExitEvent('unavailable',clock[0],None,None,None))
        totals,_=store.paper_totals_and_mark(None)
        assert totals['unknown_pnl']==1 and totals['closed_trades']==1


def test_email_retry_queue_and_dashboard_are_strategy_scoped(setup):
    db,clock,factory=setup;store=factory()
    with store.lock():
        opened=store.insert_position(position(),'bearish')
        assert len(store.pending_emails())==1
        store.set_email_status(opened.id,'entry','sent');assert store.pending_emails()==[]
        store.close_position(opened.id,ExitEvent('target',clock[0],20,5200,1.625))
        for _ in range(5):store.set_email_status(opened.id,'exit','failed')
        assert store.pending_emails()==[]
        store.publish_dashboard({'strategy':'strategy_01','realized_pnl':5200})
    assert db.values['algo_paper_state/strategy_01']['realized_pnl']==5200
    assert 'algo_paper_state/strategy_02' not in db.values


def test_runner_entry_duplicate_and_exit_use_firestore_without_postgres(setup, calendar, monkeypatch):
    from config import Config, DataConfig, EmailConfig, RuntimeConfig, StrategyConfig
    from main import Runner
    from notifications.email import EmailNotifier
    from tests.conftest import FakeProvider, FakeSMTP, ist
    from execution.firebase_paper import build_snapshot
    db, clock, factory = setup
    now = ist(2026,9,24,10,30)
    clock[0] = now.astimezone(timezone.utc)
    provider = FakeProvider([date(2026,9,29),date(2026,10,6)])
    provider.get_spot_bars = lambda asof: pd.DataFrame({'open':[provider.spot],'close':[provider.spot]},index=pd.DatetimeIndex([asof-timedelta(minutes=1)]))
    provider.now = now
    cfg = Config(strategy=StrategyConfig(),data=DataConfig(database_url=''),email=EmailConfig(enabled=False),runtime=RuntimeConfig(strategy_name='strategy_02'))
    runner = Runner(cfg,factory('strategy_02'),provider,calendar,EmailNotifier(cfg.email,smtp_factory=FakeSMTP))
    runner.engine.indicators = lambda view: (.1,.1,{})
    monkeypatch.setenv('PAPER_FIREBASE_ENABLED','true')
    assert runner.locked_cycle(now)['status']=='entry'
    assert runner.locked_cycle(now)['status']=='duplicate'
    opened = runner.store.open_position_row()
    assert opened.target is None
    clock[0]+=timedelta(minutes=1); provider.now=now+timedelta(minutes=1)
    # Force a stop through the existing engine result, while using real storage flow.
    from strategy.engine import EngineResult
    runner.engine.evaluate=lambda view,pos: EngineResult('exit','stop',exit=ExitEvent('stop',view.now,145,-2925,-.914))
    assert runner.locked_cycle(provider.now)['status']=='exit'
    state = build_snapshot(runner,{'status':'exit'})
    assert state['realized_pnl']==-2925 and state['closed_trades']==1
    assert state['open_position'] is None and len(state['closed_positions'])==1
    assert db.values['algo_paper_state/strategy_02']['realized_pnl']==-2925
    assert FakeSMTP.sent==[]
