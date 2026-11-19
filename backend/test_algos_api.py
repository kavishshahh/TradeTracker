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
    def set(self, payload, merge=False):
        self.db[self.path] = {**self.db[self.path], **payload} if merge and self.path in self.db else payload
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


async def request(app, path, method='GET', user=None, body=None, extra_headers=None):
    messages = []
    headers = [(b'host', b'localhost'), (b'content-type', b'application/json')]
    headers.extend((key.encode(), value.encode()) for key, value in (extra_headers or {}).items())
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


OWNER, GUEST, OUTSIDER = 'owner@example.com', 'guest@example.com', 'outsider@example.com'
# alice owns Algo Lab, bob is on the allow-list, carol is signed in but not listed, dave has no verified email.
EMAILS = {'alice': OWNER, 'bob': GUEST, 'carol': OUTSIDER, 'dave': None}
ACCESS = 'feature_access/algo_lab'
DATA_ROUTES = [('/algos/catalog','GET',None),('/algos/paper','GET',None),('/algos/backtest/zen_strategy_01','GET',None),('/algos/follow/zen_strategy_01','PUT',{'enabled':True})]
ADMIN_ROUTES = [('/algos/access/admin','GET',None),('/algos/access/admin/emails','PUT',{'email': OUTSIDER, 'allowed': True}),('/algos/access/admin/requests/carol','PUT',{'allowed': True})]


def make_app(db, user, **options):
    options.setdefault('email_lookup', EMAILS.get)
    options.setdefault('owner_email', ' Owner@Example.com ')
    app = FastAPI()
    app.include_router(create_algos_router(db, user, **options))
    return app


class APIAuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.db = Database({'algo_catalog/zen_strategy_01': {'name': 'One', 'description': 'how it works', 'summary': 'what it is', 'rules': ['secret'], 'limitations': 'x', 'exit_policy': 'y', 'volatility_window': 150, 'metrics': {'trade_count': 1}},
                            'algo_catalog/zen_strategy_02': {'name': 'Two', 'description': 'how it works', 'category': 'Overnight credit spread', 'underlying': 'NIFTY 50'}, ACCESS: {'emails': [' Guest@Example.com ']}})
        self.catalog_keys = set(self.db)
        async def user(authorization: str = Header(None)):
            if authorization not in ('Bearer alice','Bearer bob','Bearer carol','Bearer dave'): raise HTTPException(401)
            return authorization.split()[1]
        # catalog_ttl=0: these tests change the catalogue between requests and expect to see it at once.
        self.app = make_app(self.db, user, catalog_ttl=0)

    def test_auth_required_for_all_routes(self):
        for path, method, body in DATA_ROUTES + ADMIN_ROUTES + [('/algos/access','GET',None),('/algos/access/request','POST',None)]:
            self.assertEqual(asyncio.run(request(self.app,path,method,body=body))[0],401)
        self.assertEqual(set(self.db), self.catalog_keys)

    def test_trades_need_a_listed_or_owner_email_but_stats_are_open(self):
        self.db['algo_backtests/zen_strategy_01'] = {'trade_count': 1, 'trades': [{'pnl': 10.0}]}
        self.db['algo_paper_state/zen_strategy_01'] = {'capital': 1.0, 'realized_pnl': 5.0, 'ledger_limit': 50,
                                                      'open_position': {'sell_strike': 1}, 'closed_positions': [{'pnl': 1.0}]}
        for who in ('carol', 'dave'):                                                               # not listed / no verified email
            self.assertEqual(asyncio.run(request(self.app,'/algos/backtest/zen_strategy_01',user=who))[0],403)
            status, body = asyncio.run(request(self.app,'/algos/catalog',user=who))
            self.assertEqual((status, body['detail'], len(body['strategies'])), (200, 'public', 2))
            status, body = asyncio.run(request(self.app,'/algos/paper',user=who))
            account = body['strategies']['zen_strategy_01']
            self.assertEqual((status, body['access']), (200, False))
            self.assertEqual((account['realized_pnl'], account['capital']), (5.0, 1.0))                # summary numbers stay
            self.assertEqual((account['open_position'], account['closed_positions'], account['ledger_limit']), (None, [], 0))
            self.assertEqual((account['in_trade'], account['trades_hidden']), (True, True))
            self.assertIsNone(body['strategies']['zen_strategy_02'])
        self.assertEqual(asyncio.run(request(self.app,'/algos/follow/zen_strategy_01','PUT','carol',{'enabled': True}))[0],200)
        for who in ('bob', 'alice'):                                                                 # listed / owner
            self.assertEqual(asyncio.run(request(self.app,'/algos/backtest/zen_strategy_01',user=who))[0],200)
            status, body = asyncio.run(request(self.app,'/algos/paper',user=who))
            self.assertEqual((status, body['access']), (200, True))
            self.assertEqual(body['strategies']['zen_strategy_01']['closed_positions'], [{'pnl': 1.0}])
            self.assertNotIn('trades_hidden', body['strategies']['zen_strategy_01'])

    def test_only_the_owner_receives_rules_and_tuning(self):
        _, owner = asyncio.run(request(self.app,'/algos/catalog',user='alice'))
        _, guest = asyncio.run(request(self.app,'/algos/catalog',user='bob'))
        full = next(row for row in owner['strategies'] if row['id']=='zen_strategy_01')
        basic = next(row for row in guest['strategies'] if row['id']=='zen_strategy_01')
        self.assertEqual((owner['detail'], guest['detail']), ('full', 'public'))
        self.assertEqual((full['rules'], full['description'], full['summary']), (['secret'], 'how it works', 'what it is'))
        for secret in ('rules','limitations','exit_policy','volatility_window'):
            self.assertNotIn(secret, basic)
        self.assertEqual((basic['name'], basic['metrics'], basic['execution']), ('One', {'trade_count': 1}, 'paper_only'))
        self.assertEqual((basic['description'], basic['summary']), ('what it is', 'what it is'))     # the summary stands in for the description
        plain = next(row for row in guest['strategies'] if row['id']=='zen_strategy_02')
        self.assertEqual(plain['description'], 'Overnight credit spread on NIFTY 50.')                 # no summary: a line that says nothing about the method

    def test_access_status_and_request_flow(self):
        get = lambda who: asyncio.run(request(self.app,'/algos/access',user=who))[1]
        self.assertEqual(get('alice'), {'allowed': True, 'owner': True, 'request': 'granted'})
        self.assertEqual(get('bob'), {'allowed': True, 'owner': False, 'request': 'granted'})
        self.assertEqual(get('carol'), {'allowed': False, 'owner': False, 'request': 'none'})
        self.assertEqual(asyncio.run(request(self.app,'/algos/access/request','POST','dave'))[0], 400)
        status, body = asyncio.run(request(self.app,'/algos/access/request','POST','carol'))
        self.assertEqual((status, body), (200, {'allowed': False, 'request': 'pending'}))
        self.assertEqual(self.db['algo_access_requests/carol']['email'], OUTSIDER)
        self.assertEqual(get('carol')['request'], 'pending')
        self.assertEqual(asyncio.run(request(self.app,'/algos/access/request','POST','bob'))[1], {'allowed': True, 'request': 'granted'})

    def test_admin_routes_exist_only_for_the_owner(self):
        for who in ('bob','carol','dave'):
            for path, method, body in ADMIN_ROUTES:
                self.assertEqual(asyncio.run(request(self.app,path,method,who,body=body))[0],404)
        self.assertEqual(set(self.db), self.catalog_keys)

    def test_research_notes_are_the_owners_only_and_cost_no_database_read(self):
        for who in ('bob','carol','dave'):                                   # listed guests included: notes name rules
            self.assertEqual(asyncio.run(request(self.app,'/algos/research',user=who))[0],404)
        self.assertEqual(asyncio.run(request(self.app,'/algos/research',user=None))[0],401)
        reads = self.db.reads if hasattr(self.db,'reads') else None
        status, body = asyncio.run(request(self.app,'/algos/research',user='alice'))
        self.assertEqual(status,200)
        self.assertEqual([note['id'] for note in body['notes']], ['zen_strategy_09','zen_strategy_07'])
        for note in body['notes']:
            self.assertTrue(note['verdict'].startswith('Not listed'))
            self.assertEqual({'name','note','edge_points','gross','mid','high'} - set(note['costs'][0]), set())
        self.assertTrue(body['method'])
        if reads is not None: self.assertEqual(self.db.reads, reads)
        self.assertEqual(set(self.db), self.catalog_keys)

    def test_owner_grants_declines_and_revokes(self):
        asyncio.run(request(self.app,'/algos/access/request','POST','carol'))
        _, body = asyncio.run(request(self.app,'/algos/access/admin',user='alice'))
        self.assertEqual((body['owner'], body['emails']), (OWNER, [GUEST]))
        self.assertEqual([(row['uid'], row['email'], row['status']) for row in body['requests']], [('carol', OUTSIDER, 'pending')])
        # Grant: the email joins the list and the data routes open at once.
        status, body = asyncio.run(request(self.app,'/algos/access/admin/requests/carol','PUT','alice',{'allowed': True}))
        self.assertEqual((status, body['emails']), (200, [GUEST, OUTSIDER]))
        self.assertEqual(self.db[ACCESS]['emails'], [GUEST, OUTSIDER])
        self.assertEqual(self.db['algo_access_requests/carol']['status'], 'granted')
        self.db['algo_backtests/zen_strategy_01'] = {'trade_count': 0, 'trades': []}
        self.assertEqual(asyncio.run(request(self.app,'/algos/backtest/zen_strategy_01',user='carol'))[0], 200)
        self.assertNotIn('rules', asyncio.run(request(self.app,'/algos/catalog',user='carol'))[1]['strategies'][0])
        # Revoke by email: the request shows as revoked and the trades close again.
        asyncio.run(request(self.app,'/algos/access/admin/emails','PUT','alice',{'email': ' Outsider@Example.com', 'allowed': False}))
        self.assertEqual(asyncio.run(request(self.app,'/algos/backtest/zen_strategy_01',user='carol'))[0], 403)
        _, body = asyncio.run(request(self.app,'/algos/access/admin',user='alice'))
        self.assertEqual(body['requests'][0]['status'], 'revoked')
        # Decline: recorded on the request, nothing added to the list.
        asyncio.run(request(self.app,'/algos/access/admin/requests/carol','PUT','alice',{'allowed': False}))
        self.assertEqual(asyncio.run(request(self.app,'/algos/access',user='carol'))[1]['request'], 'denied')
        self.assertEqual(self.db[ACCESS]['emails'], [GUEST])
        # Direct grant without a request; bad input is rejected; the owner cannot be listed.
        asyncio.run(request(self.app,'/algos/access/admin/emails','PUT','alice',{'email': 'new@example.com', 'allowed': True}))
        self.assertEqual(self.db[ACCESS]['emails'], [GUEST, 'new@example.com'])
        self.assertEqual(asyncio.run(request(self.app,'/algos/access/admin/emails','PUT','alice',{'email': 'nope', 'allowed': True}))[0], 422)
        self.assertEqual(asyncio.run(request(self.app,'/algos/access/admin/emails','PUT','alice',{'email': OWNER, 'allowed': True}))[0], 400)
        self.assertEqual(asyncio.run(request(self.app,'/algos/access/admin/requests/nobody','PUT','alice',{'allowed': True}))[0], 404)

    def test_missing_access_document_admits_only_the_owner_to_trades(self):
        del self.db[ACCESS]
        self.db['algo_backtests/zen_strategy_01'] = {'trade_count': 0, 'trades': []}
        self.assertEqual(asyncio.run(request(self.app,'/algos/backtest/zen_strategy_01',user='bob'))[0], 403)
        self.assertEqual(asyncio.run(request(self.app,'/algos/backtest/zen_strategy_01',user='alice'))[0], 200)
        asyncio.run(request(self.app,'/algos/access/admin/emails','PUT','alice',{'email': GUEST, 'allowed': True}))
        self.assertEqual(self.db[ACCESS], {'emails': [GUEST]})
        self.assertEqual(asyncio.run(request(self.app,'/algos/backtest/zen_strategy_01',user='bob'))[0], 200)

    def test_follow_is_user_scoped_idempotent_and_does_not_start_worker(self):
        for _ in range(2):
            status, _ = asyncio.run(request(self.app,'/algos/follow/zen_strategy_01','PUT','alice',{'enabled':True,'user_id':'bob'}))
            self.assertEqual(status,200)
        self.assertEqual(set(self.db),self.catalog_keys | {'users/alice/algo_follows/zen_strategy_01'})
        _, alice = asyncio.run(request(self.app,'/algos/paper',user='alice'))
        _, bob = asyncio.run(request(self.app,'/algos/paper',user='bob'))
        self.assertTrue(alice['following']['zen_strategy_01'])
        self.assertEqual(bob['following'],{})
        self.assertIsNone(alice['strategies']['zen_strategy_01'])

    def test_catalogue_is_live_database_data_and_has_no_static_fallback(self):
        _, body = asyncio.run(request(self.app, '/algos/catalog', user='alice'))
        self.assertEqual(len(body['strategies']), 2)
        self.db['algo_catalog/ratio_strategy_03'] = {'name': 'New', 'id': 'spoofed', 'execution': 'live'}
        _, body = asyncio.run(request(self.app, '/algos/catalog', user='alice'))
        row = next(item for item in body['strategies'] if item['id'] == 'ratio_strategy_03')
        self.assertEqual(row['execution'], 'paper_only')
        self.db['algo_catalog/ratio_strategy_03']['enabled'] = False
        self.assertEqual(asyncio.run(request(self.app, '/algos/follow/ratio_strategy_03', 'PUT', 'alice', {'enabled': True}))[0], 404)
        self.db.clear()
        _, body = asyncio.run(request(self.app, '/algos/catalog', user='alice'))
        self.assertEqual(body['strategies'], [])

    def test_backtest_ledger_is_one_document_and_missing_ids_are_404(self):
        self.db['algo_backtests/zen_strategy_01'] = {'trade_count': 1, 'trades': [{'pnl': 10.0}], 'strategy_id': 'spoofed'}
        status, body = asyncio.run(request(self.app, '/algos/backtest/zen_strategy_01', user='alice'))
        self.assertEqual(status, 200)
        self.assertEqual((body['strategy_id'], body['trade_count'], body['execution']), ('zen_strategy_01', 1, 'paper_only'))
        self.assertEqual(asyncio.run(request(self.app, '/algos/backtest/zen_strategy_02', user='alice'))[0], 404)
        self.assertEqual(asyncio.run(request(self.app, '/algos/backtest/Bad.Id', user='alice'))[0], 404)

    def test_catalogue_is_cached_per_process_and_paper_poll_does_not_restream_it(self):
        clock=[0.0];streams=[]
        class Counting(Database):
            def collection(self,name):
                streams.append(name);return Database.collection(self,name)
        db=Counting(self.db)
        async def user(authorization: str = Header(None)): return 'alice'
        app=make_app(db,user,catalog_ttl=60,clock=lambda:clock[0])
        for _ in range(3): self.assertEqual(asyncio.run(request(app,'/algos/paper',user='alice'))[0],200)
        asyncio.run(request(app,'/algos/catalog',user='alice'))
        self.assertEqual(streams.count('algo_catalog'),1)                 # one stream serves every poll
        self.assertEqual(streams.count('algo_paper_state'),6)             # one state read per strategy per poll
        clock[0]=61.0
        asyncio.run(request(app,'/algos/catalog',user='alice'))
        self.assertEqual(streams.count('algo_catalog'),2)                 # refreshed after the TTL

    def test_unavailable_storage_is_logged_with_the_error_type(self):
        class Broken:
            def collection(self,name):
                class Exploding:
                    def stream(self): raise RuntimeError('quota')
                return Exploding()
        async def user(): return 'alice'
        app=make_app(Broken(),user,catalog_ttl=0)
        with self.assertLogs('algos_api',level='WARNING') as captured:
            self.assertEqual(asyncio.run(request(app,'/algos/catalog'))[0],503)
        self.assertIn('algos_api_unavailable route=catalog error=RuntimeError',' '.join(captured.output))

    def test_unknown_strategy_and_unavailable_storage_fail_explicitly(self):
        status, _ = asyncio.run(request(self.app,'/algos/follow/unknown','PUT','alice',{'enabled':True}))
        self.assertEqual(status,404)
        async def user(): return 'alice'
        app = make_app(None,user)
        self.assertEqual(asyncio.run(request(app,'/algos/paper'))[0],503)
        self.assertEqual(asyncio.run(request(app,'/algos/catalog'))[0],503)
        self.assertEqual(asyncio.run(request(app,'/algos/backtest/zen_strategy_01'))[0],503)


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
        runner=SimpleNamespace(store=Store(),strategy_name='zen_strategy_02',last_context={},cfg=SimpleNamespace(strategy=SimpleNamespace(capital=320000),data=SimpleNamespace(provider='nse')))
        state=module.build_snapshot(runner,{'status':'no_action'})
        self.assertEqual(state['realized_pnl'],10000)
        self.assertEqual(state['closed_trades'],250)
        self.assertEqual(state['win_rate_pct'],60)
        self.assertAlmostEqual(state['unrealized_pnl'],34547.5)
        self.assertIsNotNone(state['valuation_ts'])
        self.assertEqual(state['execution'],'paper_only')


if __name__=='__main__': unittest.main()
