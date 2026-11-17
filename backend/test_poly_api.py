"""Offline checks for the private Polymarket section; no Firebase or network calls."""
import asyncio
import json
from types import SimpleNamespace
import unittest

from fastapi import FastAPI, Header, HTTPException

from poly_api import create_poly_router


class Database(dict):
    """Path-keyed stand-in for the Firestore calls the router makes."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.queries = []
    def collection(self, name):
        db = self
        def document(doc_id):
            path = f'{name}/{doc_id}'
            return SimpleNamespace(get=lambda: SimpleNamespace(exists=path in db, to_dict=lambda: db.get(path)))
        def stream(keep=lambda payload: True):
            return [SimpleNamespace(id=path.split('/')[1], to_dict=lambda payload=payload: payload)
                    for path, payload in db.items() if path.startswith(name + '/') and keep(payload)]
        def where(filter):
            assert (filter.field_path, filter.op_string) == ('t', '>='), 'router only filters t >= since'
            db.queries.append((name, filter.value))
            return SimpleNamespace(stream=lambda: stream(lambda payload: payload.get('t', 0) >= filter.value))
        return SimpleNamespace(document=document, stream=stream, where=where)


async def request(app, path, user=None, gzip_ok=False, raw=False):
    messages = []
    headers = [(b'host', b'localhost')] + ([(b'authorization', ('Bearer ' + user).encode())] if user else [])
    headers += [(b'accept-encoding', b'gzip, deflate')] if gzip_ok else []
    async def receive(): return {'type': 'http.request', 'body': b'', 'more_body': False}
    async def send(message): messages.append(message)
    path, _, query = path.partition('?')
    await app({'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1', 'scheme': 'http', 'method': 'GET',
               'path': path, 'raw_path': path.encode(), 'query_string': query.encode(), 'root_path': '', 'headers': headers,
               'client': ('127.0.0.1', 1), 'server': ('localhost', 80)}, receive, send)
    start = next(item for item in messages if item['type'] == 'http.response.start')
    body = b''.join(item.get('body', b'') for item in messages if item['type'] == 'http.response.body')
    if raw:
        return start['status'], dict(start['headers']), body
    return start['status'], json.loads(body)

OWNER, OTHER = 'owner@example.com', 'other@example.com'


class PolyAccessTests(unittest.TestCase):
    def setUp(self):
        self.db = Database({
            'feature_access/polymarket_algos': {'emails': [' Owner@Example.com ']},
            'poly_paper_state/crypto_fair_value': {'equity': 25.0},
            'poly_catalog/crypto_fair_value': {'test': {'n': 1}},
            'poly_paper_trades/b': {'t': 2, 'kind': 'settled'},
            'poly_paper_trades/a': {'t': 1, 'kind': 'fill'},
        })
        self.emails = {'alice': OWNER, 'bob': OTHER, 'carol': None}   # carol: unverified email

        async def user(authorization: str = Header(None)):
            if authorization not in ('Bearer alice', 'Bearer bob', 'Bearer carol'):
                raise HTTPException(401)
            return authorization.split()[1]

        self.now = [0.0]
        self.app = FastAPI()
        self.app.include_router(create_poly_router(self.db, user, email_lookup=self.emails.get,
                                                   clock=lambda: self.now[0]))

    def get(self, path, user=None):
        return asyncio.run(request(self.app, path, user=user))

    def test_sign_in_required(self):
        self.assertEqual(self.get('/poly/access')[0], 401)
        self.assertEqual(self.get('/poly/paper')[0], 401)

    def test_only_listed_verified_email_is_allowed(self):
        self.assertEqual(self.get('/poly/access', 'alice'), (200, {'allowed': True}))
        self.assertEqual(self.get('/poly/access', 'bob'), (200, {'allowed': False}))
        self.assertEqual(self.get('/poly/access', 'carol'), (200, {'allowed': False}))

    def test_data_is_hidden_from_everyone_else(self):
        status, body = self.get('/poly/paper', 'alice')
        self.assertEqual(status, 200)
        self.assertEqual(body['strategies']['crypto_fair_value']['equity'], 25.0)
        self.assertEqual(body['execution'], 'paper_only')
        self.assertEqual(self.get('/poly/paper', 'bob')[0], 404)
        self.assertEqual(self.get('/poly/paper', 'carol')[0], 404)

    def test_full_ledger_is_private_and_in_time_order(self):
        status, body = self.get('/poly/trades', 'alice')
        self.assertEqual((status, [row['kind'] for row in body['trades']]), (200, ['fill', 'settled']))
        self.assertEqual(self.get('/poly/trades', 'bob')[0], 404)
        # Incremental read: only rows at or after `since`, filtered in Firestore (not after a full stream).
        status, body = self.get('/poly/trades?since=2', 'alice')
        self.assertEqual((status, [row['kind'] for row in body['trades']]), (200, ['settled']))
        self.assertEqual(self.db.queries, [('poly_paper_trades', 2.0)])
        self.assertEqual(self.get('/poly/trades?since=-1', 'alice')[0], 422)
        self.assertEqual(self.get('/poly/trades?since=nan', 'alice')[0], 422)
        self.assertEqual(self.get('/poly/trades')[0], 401)

    def test_access_follows_the_database_not_code(self):
        self.assertFalse(self.get('/poly/access', 'bob')[1]['allowed'])
        self.db['feature_access/polymarket_algos'] = {'emails': [OTHER]}
        self.now[0] += 61                       # access list cache expires
        self.assertTrue(self.get('/poly/access', 'bob')[1]['allowed'])
        self.assertFalse(self.get('/poly/access', 'alice')[1]['allowed'])

    def test_missing_access_document_hides_section(self):
        del self.db['feature_access/polymarket_algos']
        self.assertFalse(self.get('/poly/access', 'alice')[1]['allowed'])
        self.assertEqual(self.get('/poly/paper', 'alice')[0], 404)

    def test_large_replies_are_gzipped_only_when_accepted(self):
        import gzip
        self.db['poly_paper_state/long_dated_no'] = {'positions': [{'question': 'q' * 50, 'cost': 2.0}] * 200}
        status, headers, body = asyncio.run(request(self.app, '/poly/paper', 'alice', gzip_ok=True, raw=True))
        self.assertEqual((status, headers.get(b'content-encoding')), (200, b'gzip'))
        plain = self.get('/poly/paper', 'alice')[1]
        self.assertEqual(json.loads(gzip.decompress(body)), plain)
        status, headers, body = asyncio.run(request(self.app, '/poly/paper', 'alice', raw=True))
        self.assertIsNone(headers.get(b'content-encoding'))
        self.assertEqual(json.loads(body), plain)

    def test_since_sends_only_accounts_written_after_it(self):
        from datetime import datetime, timezone
        at = lambda t: datetime.fromtimestamp(t, timezone.utc)
        docs = [SimpleNamespace(id='old', to_dict=lambda: {'equity': 1}, update_time=at(100), read_time=at(500)),
                SimpleNamespace(id='new', to_dict=lambda: {'equity': 2}, update_time=at(400), read_time=at(500))]
        stream = self.db.collection
        self.db.collection = lambda name: SimpleNamespace(stream=lambda: docs) if name == 'poly_paper_state' else stream(name)
        full = self.get('/poly/paper', 'alice')[1]
        self.assertEqual((set(full['strategies']), full['as_of'], 'partial' in full), ({'old', 'new'}, 500.0, False))
        part = self.get('/poly/paper?since=300', 'alice')[1]
        self.assertEqual((set(part['strategies']), part['ids'], part['partial']), ({'new'}, ['old', 'new'], True))
        self.assertEqual(self.get('/poly/paper?since=nan', 'alice')[0], 422)

    def test_section_is_read_only(self):
        routes = {(method, route.path) for route in self.app.routes for method in getattr(route, 'methods', [])
                  if route.path.startswith('/poly')}
        self.assertEqual(routes, {('GET', '/poly/access'), ('GET', '/poly/paper'), ('GET', '/poly/trades')})


if __name__ == '__main__':
    unittest.main()

