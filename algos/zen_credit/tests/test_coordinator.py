from datetime import datetime
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from execution.coordinator import PaperCoordinator
from strategy.registry import STRATEGIES
from utils.time import IST


class CoordinatorTests(unittest.TestCase):
    def test_dashboard_publication_is_logged_only_after_write(self):
        from execution.firebase_paper import publish_paper_snapshot
        runner = SimpleNamespace(strategy_name='zen_strategy_02', store=SimpleNamespace(publish_dashboard=lambda _: None))
        payload = {'last_evaluation': '2026-10-09T09:25:00+05:30', 'updated_at': '2026-10-09T09:25:02+05:30', 'status': 'no_action'}
        with patch.dict('os.environ', {'PAPER_FIREBASE_ENABLED': 'true'}), patch('execution.firebase_paper.build_snapshot', return_value=payload):
            with self.assertLogs('paper.dashboard', level='INFO') as captured:
                publish_paper_snapshot(runner, {'status': 'no_action'})
            self.assertIn('paper_dashboard_published strategy=zen_strategy_02', '\n'.join(captured.output))
            def failed(_):
                raise RuntimeError('write failed')
            runner.store.publish_dashboard = failed
            with self.assertLogs('paper.dashboard', level='INFO') as captured:
                with self.assertRaises(RuntimeError):
                    publish_paper_snapshot(runner, {'status': 'no_action'})
            self.assertNotIn('paper_dashboard_published', '\n'.join(captured.output))

    def test_disabled_strategy_and_failure_have_correlated_logs(self):
        from paper_worker import run_round
        now = datetime(2026, 10, 9, 9, 25, tzinfo=IST)
        def failed(_):
            raise RuntimeError('private credential must not be logged')
        runners = {
            'zen_strategy_01': SimpleNamespace(store=SimpleNamespace(open_position_row=lambda: None), locked_cycle=failed),
            'zen_strategy_02': SimpleNamespace(store=SimpleNamespace(open_position_row=lambda: None), locked_cycle=failed),
        }
        with self.assertLogs('paper.worker', level='INFO') as captured:
            result = run_round(runners, {'zen_strategy_02': {'enabled': True}}, now)
        output = '\n'.join(captured.output)
        self.assertIn('paper_strategy_skipped strategy=zen_strategy_01', output)
        self.assertIn('reason=disabled_and_flat', output)
        self.assertIn('paper_strategy_failed strategy=zen_strategy_02', output)
        self.assertIn(now.isoformat(), output)
        self.assertIn('duration_s=', output)
        self.assertNotIn('private credential', output)
        self.assertEqual(result['zen_strategy_02']['status'], 'error')

    def test_restarted_disabled_position_exits_and_provider_is_shared(self):
        now = datetime(2026, 10, 7, 10, 30, tzinfo=IST)
        provider = SimpleNamespace(begin_round=lambda: None)
        docs = [SimpleNamespace(id='zen_strategy_01', to_dict=lambda: {'enabled': False, 'capital': 320000}),
                SimpleNamespace(id='zen_strategy_02', to_dict=lambda: {'enabled': True, 'capital': 120000})]
        db = SimpleNamespace(collection=lambda _: SimpleNamespace(stream=lambda **_: docs))
        seen = []
        def factory(cfg, provider):
            seen.append((cfg.runtime.strategy_name, cfg.strategy.capital, cfg.data.provider, provider))
            return SimpleNamespace(store=SimpleNamespace(open_position_row=lambda: object()),
                                   locked_cycle=lambda now: {'status': 'exit'})
        coordinator = PaperCoordinator(db, provider, factory)
        result = coordinator.run_once(now)
        self.assertEqual(result['strategies']['zen_strategy_01']['status'], 'exit')
        # one runner per registered strategy, in registry order; catalogue rows are optional
        self.assertEqual([item[0] for item in seen], [name for name in STRATEGIES if name != 'description'])
        self.assertTrue(all(item[2] == 'dhan' and item[3] is provider for item in seen))
        self.assertEqual(seen[1][1], 120000)
        coordinator.lock.acquire()
        try:
            self.assertEqual(coordinator.run_once(now)['status'], 'busy')
        finally:
            coordinator.lock.release()
        coordinator.run_once(now)
        # one runner per registered strategy, in registry order; catalogue rows are optional
        self.assertEqual([item[0] for item in seen], [name for name in STRATEGIES if name != 'description'])


if __name__ == '__main__': unittest.main()
