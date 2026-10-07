"""Offline scheduler authentication and failure checks; no external API calls."""
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from algos_scheduler_api import create_scheduler_router
from test_algos_api import request

NOW = datetime(2026, 10, 7, 4, 45, 5, tzinfo=timezone.utc)
HEADERS = {'x-paper-scheduler-token': 'test-secret', 'x-scheduled-at': '2026-10-07T04:45:00Z'}


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.factory_calls = []
        self.result = {'status': 'ok', 'strategies': {'strategy_01': {'status': 'no_action'}, 'strategy_02': {'status': 'entry'}}}
        def factory(db):
            self.factory_calls.append(db)
            return SimpleNamespace(run_once=lambda: self.calls.append(1) or self.result)
        self.app = FastAPI()
        self.app.include_router(create_scheduler_router(object(), factory, clock=lambda: NOW))

    def call(self, headers=None):
        return asyncio.run(request(self.app, '/algos/run-paper-cycle', 'POST', extra_headers=HEADERS if headers is None else headers))

    @patch.dict('os.environ', {'PAPER_SCHEDULER_TOKEN': 'test-secret'})
    def test_auth_and_fresh_timestamp_precede_factory_and_execution(self):
        self.assertEqual(self.call({})[0], 401)
        self.assertEqual(self.call({**HEADERS, 'x-paper-scheduler-token': 'bad'})[0], 401)
        self.assertEqual(self.call({**HEADERS, 'x-scheduled-at': '2026-10-07T04:40:00Z'})[0], 422)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.factory_calls, [])
        self.assertEqual(self.call()[0], 200)
        self.assertEqual(self.call()[1]['execution'], 'paper_only')
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(len(self.factory_calls), 1)

    @patch.dict('os.environ', {'PAPER_SCHEDULER_TOKEN': 'test-secret'})
    def test_busy_and_data_failures_are_visible(self):
        self.result = {'status': 'busy'}
        self.assertEqual(self.call()[0], 409)
        self.result = {'status': 'error', 'strategies': {'strategy_01': {'status': 'data_error', 'detail': 'private message'}}}
        status, body = self.call()
        self.assertEqual(status, 503)
        self.assertNotIn('private message', str(body))

    @patch.dict('os.environ', {'PAPER_SCHEDULER_TOKEN': ''})
    def test_unconfigured_secret_refuses_execution(self):
        self.assertEqual(self.call()[0], 503)
        self.assertEqual(self.calls, [])


if __name__ == '__main__': unittest.main()
