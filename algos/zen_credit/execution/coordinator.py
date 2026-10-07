"""Shared paper account evaluator for the API scheduler and local worker."""
from dataclasses import replace
import threading
from config import CONFIG
from data.providers.dhan import DhanLiveProvider
from main import Runner
from paper_worker import run_round
from strategy.registry import STRATEGIES
from utils.time import now_ist


class PaperCoordinator:
    def __init__(self, db, provider=None, runner_factory=None):
        self.db = db
        self.provider = provider or DhanLiveProvider()
        self.runner_factory = runner_factory or Runner.from_config
        self.runners = {}
        self.lock = threading.Lock()

    def run_once(self, now=None):
        if not self.lock.acquire(blocking=False):
            return {'status': 'busy', 'execution': 'paper_only'}
        try:
            catalog = {doc.id: doc.to_dict() for doc in self.db.collection('algo_catalog').stream(timeout=15)}
            for name in STRATEGIES:
                if name == 'description' or name in self.runners:
                    continue
                record = catalog.get(name, {})
                cfg = replace(CONFIG, strategy=replace(CONFIG.strategy, capital=float(record.get('capital', CONFIG.strategy.capital))),
                              data=replace(CONFIG.data, provider='dhan'), email=replace(CONFIG.email, enabled=False),
                              runtime=replace(CONFIG.runtime, strategy_name=name))
                # Disabled/missing catalogue rows cannot enter. An existing held
                # position is still managed, including after a process restart.
                self.runners[name] = self.runner_factory(cfg, provider=self.provider)
            self.provider.begin_round()
            results = run_round(self.runners, catalog, now or now_ist())
            failed = any(item.get('status') in ('error', 'data_error', 'db_unavailable', 'calendar_unavailable', 'strategy_state_mismatch') for item in results.values())
            return {'status': 'error' if failed else 'ok', 'execution': 'paper_only', 'strategies': results}
        finally:
            self.lock.release()
