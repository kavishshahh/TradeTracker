"""Shared paper account evaluator for the API scheduler and local worker."""
from dataclasses import replace
import threading
import logging
import time
from config import CONFIG
from data.providers.dhan import DhanLiveProvider
from main import Runner, configure_paper_logging
from paper_worker import run_round
from strategy.registry import STRATEGIES
from utils.time import now_ist

log = logging.getLogger('paper.coordinator')


class PaperCoordinator:
    def __init__(self, db, provider=None, runner_factory=None):
        configure_paper_logging()
        self.db = db
        self.provider = provider or DhanLiveProvider()
        self.runner_factory = runner_factory or Runner.from_config
        self.runners = {}
        self.lock = threading.Lock()

    def run_once(self, now=None):
        now = now or now_ist()
        started = time.monotonic()
        if not self.lock.acquire(blocking=False):
            log.warning('paper_round_busy minute=%s', now.isoformat())
            return {'status': 'busy', 'execution': 'paper_only'}
        try:
            log.info('paper_round_start minute=%s', now.isoformat())
            log.info('paper_catalog_start minute=%s', now.isoformat())
            catalog = {doc.id: doc.to_dict() for doc in self.db.collection('algo_catalog').stream(timeout=15)}
            log.info('paper_catalog_loaded minute=%s strategies=%s', now.isoformat(),
                     {name: bool(catalog.get(name, {}).get('enabled', False)) for name in STRATEGIES if name != 'description'})
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
            results = run_round(self.runners, catalog, now)
            failed = any(item.get('status') in ('error', 'data_error', 'db_unavailable', 'calendar_unavailable', 'strategy_state_mismatch') for item in results.values())
            log.info('paper_round_complete minute=%s status=%s duration_s=%.2f strategies=%s',
                     now.isoformat(), 'error' if failed else 'ok', time.monotonic() - started,
                     {name: item.get('status') for name, item in results.items()})
            return {'status': 'error' if failed else 'ok', 'execution': 'paper_only', 'strategies': results}
        except Exception as exc:
            log.error('paper_round_failed minute=%s duration_s=%.2f error=%s', now.isoformat(),
                      time.monotonic() - started, type(exc).__name__)
            raise
        finally:
            self.lock.release()
