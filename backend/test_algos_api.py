"""Offline checks; no Firebase, broker or production database calls."""
import asyncio
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from fastapi import FastAPI, Header, HTTPException
from algos_api import create_algos_router


class Document:
    def __init__(self, db, path): self.db, self.path = db, path
    def collection(self, name): return Collection(self.db, self.path + '/' + name)
    def set(self, payload): self.db[self.path] = payload
    def get(self):
        return SimpleNamespace(exists=self.path in self.db, to_dict=lambda: self.db.get(self.path))


class Collection:
    def __init__(self, db, path): self.db, self.path = db, path
    def document(self, name): return Document(self.db, self.path + '/' + name)
    def stream(self):
        for path, payload in self.db.items():
            if path.startswith(self.path + '/') and '/' not in path[len(self.path) + 1:]:
                yield SimpleNamespace(id=path.split('/')[-1], to_dict=lambda payload=payload: payload)


class Database(dict):
    def collection(self, name): return Collection(self, name)


async def request(app, path, method='GET', user=None, body=None):
    messages = []
    headers = [(b'host', b'localhost'), (b'content-type', b'application/json')]
    if user: headers.append((b'authorization', ('Bearer ' + user).encode()))
    payload = json.dumps(body).encode() if body is not None else b''
    async def receive(): return {'type': 'http.request', 'body': payload, 'more_body': False}
    async def send(message): messages.append(message)
    await app({'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','scheme':'http',
               'method':method,'path':path,'raw_path':path.encode(),'query_string':b'',
               'root_path':'','headers':headers,'client':('127.0.0.1',1),'server':('localhost',80)}, receive, send)
    status = next(item['status'] for item in messages if item['type']=='http.response.start')
    content = b''.join(item.get('body', b'') for item in messages if item['type']=='http.response.body')
    return status, json.loads(content)


class APIAuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.db = Database({'algo_catalog/strategy_01': {'name': 'One'}, 'algo_catalog/strategy_02': {'name': 'Two'}})
        self.catalog_keys = set(self.db)
        async def user(authorization: str = Header(None)):
            if authorization not in ('Bearer alice','Bearer bob'): raise HTTPException(401)
            return authorization.split()[1]
        self.app = FastAPI()
        self.app.include_router(create_algos_router(self.db, user))

    def test_auth_required_for_all_routes(self):
        for path, method, body in [('/algos/catalog','GET',None),('/algos/paper','GET',None),('/algos/follow/strategy_01','PUT',{'enabled':True})]:
            self.assertEqual(asyncio.run(request(self.app,path,method,body=body))[0],401)
        self.assertEqual(set(self.db), self.catalog_keys)

    def test_follow_is_user_scoped_idempotent_and_does_not_start_worker(self):
        for _ in range(2):
            status, _ = asyncio.run(request(self.app,'/algos/follow/strategy_01','PUT','alice',{'enabled':True,'user_id':'bob'}))
            self.assertEqual(status,200)
        self.assertEqual(set(self.db),self.catalog_keys | {'users/alice/algo_follows/strategy_01'})
        _, alice = asyncio.run(request(self.app,'/algos/paper',user='alice'))
        _, bob = asyncio.run(request(self.app,'/algos/paper',user='bob'))
        self.assertTrue(alice['following']['strategy_01'])
        self.assertEqual(bob['following'],{})
        self.assertIsNone(alice['strategies']['strategy_01'])

    def test_catalogue_is_live_database_data_and_has_no_static_fallback(self):
        _, body = asyncio.run(request(self.app, '/algos/catalog', user='alice'))
        self.assertEqual(len(body['strategies']), 2)
        self.db['algo_catalog/strategy_03'] = {'name': 'New', 'id': 'spoofed', 'execution': 'live'}
        _, body = asyncio.run(request(self.app, '/algos/catalog', user='alice'))
        row = next(item for item in body['strategies'] if item['id'] == 'strategy_03')
        self.assertEqual(row['execution'], 'paper_only')
        self.db['algo_catalog/strategy_03']['enabled'] = False
        self.assertEqual(asyncio.run(request(self.app, '/algos/follow/strategy_03', 'PUT', 'alice', {'enabled': True}))[0], 404)
        self.db.clear()
        _, body = asyncio.run(request(self.app, '/algos/catalog', user='alice'))
        self.assertEqual(body['strategies'], [])

    def test_unknown_strategy_and_unavailable_storage_fail_explicitly(self):
        status, _ = asyncio.run(request(self.app,'/algos/follow/unknown','PUT','alice',{'enabled':True}))
        self.assertEqual(status,404)
        app = FastAPI()
        async def user(): return 'alice'
        app.include_router(create_algos_router(None,user))
        self.assertEqual(asyncio.run(request(app,'/algos/paper'))[0],503)
        self.assertEqual(asyncio.run(request(app,'/algos/catalog'))[0],503)


class PaperSnapshotTests(unittest.TestCase):
    def test_synchronized_spread_mtm_is_separate_from_full_ledger_realized_total(self):
        from datetime import datetime, timezone
        module_path=Path(__file__).resolve().parents[1]/'algos/zen_credit/execution/firebase_paper.py'
        spec=importlib.util.spec_from_file_location('paper_snapshot_under_test',module_path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        trade=SimpleNamespace(**{field:None for field in module.FIELDS})
        trade.option_type='CE';trade.expiry='2026-10-06';trade.sell_strike=22750;trade.buy_strike=23150
        trade.units=325;trade.entry_spread_price=130.95
        class Cursor:
            calls=0
            def execute(self,*args): self.calls+=1
            def fetchone(self):
                return {'closed_trades':250,'winners':150,'unknown_pnl':0,'realized_pnl':10000} if self.calls==1 else {'sell':31.15,'buy':6.5,'minute':datetime(2026,10,1,9,23,tzinfo=timezone.utc)}
            def __enter__(self): return self
            def __exit__(self,*args): pass
        class Store:
            def open_position_row(self): return trade
            def closed_positions(self,limit): return []
            def get_state(self,key): return '2026-10-01T14:53:00+05:30'
            def _cursor(self,**kwargs): return Cursor()
        runner=SimpleNamespace(store=Store(),strategy_name='strategy_02',last_context={},cfg=SimpleNamespace(strategy=SimpleNamespace(capital=320000),data=SimpleNamespace(provider='nse')))
        state=module.build_snapshot(runner,{'status':'no_action'})
        self.assertEqual(state['realized_pnl'],10000)
        self.assertEqual(state['closed_trades'],250)
        self.assertEqual(state['win_rate_pct'],60)
        self.assertAlmostEqual(state['unrealized_pnl'],34547.5)
        self.assertIsNotNone(state['valuation_ts'])
        self.assertEqual(state['execution'],'paper_only')


if __name__=='__main__': unittest.main()
