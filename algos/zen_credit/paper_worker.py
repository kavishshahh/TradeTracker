"""One persistent paper-only backend worker for both registered strategies.

Run from TradeTracker: python algos/zen_credit/paper_worker.py
Reads backend/.env locally; hosting injects the same backend environment.
No external cron and no broker order endpoint. Decisions/MTM are minute-based.
"""
import argparse
from dataclasses import replace
import logging
import signal
import threading
import time

from config import CONFIG
from data.providers.dhan import DhanLiveProvider
from execution.firebase_client import get_firestore_client
from main import Runner, setup_logging
from strategy.registry import STRATEGIES
from utils.time import now_ist

log = logging.getLogger('paper.worker')


def run_round(runners, catalog, now):
    results = {}
    for name, runner in runners.items():
        started = time.monotonic()
        log.info('paper_strategy_start strategy=%s minute=%s', name, now.isoformat())
        # Disabling new entries must not abandon an existing paper position.
        try:
            if not catalog.get(name, {}).get('enabled', False) and runner.store.open_position_row() is None:
                log.info('paper_strategy_skipped strategy=%s minute=%s reason=disabled_and_flat duration_s=%.2f',
                         name, now.isoformat(), time.monotonic() - started)
                continue
            result = runner.locked_cycle(now)
            results[name] = result
            log.info('paper_strategy_complete strategy=%s minute=%s status=%s duration_s=%.2f reason=%s',
                     name, now.isoformat(), result.get('status'), time.monotonic() - started,
                     result.get('reason') or result.get('detail') or '-')
        except Exception as exc:
            # The other strategy still runs; next minute can recover.
            results[name] = {'status': 'error', 'reason': type(exc).__name__}
            log.error('paper_strategy_failed strategy=%s minute=%s duration_s=%.2f error=%s',
                      name, now.isoformat(), time.monotonic() - started, type(exc).__name__)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-data', action='store_true', help='Read-only Dhan connectivity check; no paper cycles or DB writes')
    args = parser.parse_args()
    setup_logging(CONFIG)
    provider = DhanLiveProvider()
    if args.check_data:
        expiries = provider.get_expiries()
        now = now_ist()
        bars = provider.get_spot_bars(now)
        print('Dhan active NIFTY expiries:', len(expiries), 'lot size:', provider.get_lot_size(expiries[0]))
        print('Completed index candles:', len(bars), 'last:', str(bars.index[-1]))
        if now.weekday() < 5 and CONFIG.strategy.market_open <= now.time() < CONFIG.strategy.market_close:
            chain = provider.get_option_chain(expiries[0])
            print('Live option rows:', len(chain.quotes), 'exchange timestamp:', chain.timestamp.isoformat())
        else:
            print('Outside regular market session; live quote freshness must be checked during trading hours.')
        return
    db = get_firestore_client()
    from execution.coordinator import PaperCoordinator
    coordinator = PaperCoordinator(db, provider=provider)
    stopped = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    signal.signal(signal.SIGINT, lambda *_: stopped.set())
    log.info('Paper worker started. Provider=Dhan, interval=one minute, orders=disabled')
    while not stopped.is_set():
        now = now_ist()
        try:
            coordinator.run_once(now)
        except Exception as exc:
            log.error('Paper worker round failed: %s', type(exc).__name__)
        # Keep running overnight; exchange calendar blocks trading/data requests.
        # Aim just after each minute boundary, allowing candle publication time.
        delay = max(1, 60 - time.time() % 60 + 5)
        stopped.wait(delay)


if __name__ == '__main__':
    main()
