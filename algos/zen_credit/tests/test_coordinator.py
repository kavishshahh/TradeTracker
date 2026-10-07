from datetime import datetime
from types import SimpleNamespace
import unittest
from execution.coordinator import PaperCoordinator
from utils.time import IST


class CoordinatorTests(unittest.TestCase):
    def test_restarted_disabled_position_exits_and_provider_is_shared(self):
        now = datetime(2026, 10, 7, 10, 30, tzinfo=IST)
        provider = SimpleNamespace(begin_round=lambda: None)
        docs = [SimpleNamespace(id='strategy_01', to_dict=lambda: {'enabled': False, 'capital': 320000}),
                SimpleNamespace(id='strategy_02', to_dict=lambda: {'enabled': True, 'capital': 120000})]
        db = SimpleNamespace(collection=lambda _: SimpleNamespace(stream=lambda **_: docs))
        seen = []
        def factory(cfg, provider):
            seen.append((cfg.runtime.strategy_name, cfg.strategy.capital, cfg.data.provider, provider))
            return SimpleNamespace(store=SimpleNamespace(open_position_row=lambda: object()),
                                   locked_cycle=lambda now: {'status': 'exit'})
        coordinator = PaperCoordinator(db, provider, factory)
        result = coordinator.run_once(now)
        self.assertEqual(result['strategies']['strategy_01']['status'], 'exit')
        self.assertEqual(len(seen), 2)
        self.assertTrue(all(item[2] == 'dhan' and item[3] is provider for item in seen))
        self.assertEqual(seen[1][1], 120000)
        coordinator.lock.acquire()
        try:
            self.assertEqual(coordinator.run_once(now)['status'], 'busy')
        finally:
            coordinator.lock.release()
        coordinator.run_once(now)
        self.assertEqual(len(seen), 2)


if __name__ == '__main__': unittest.main()
