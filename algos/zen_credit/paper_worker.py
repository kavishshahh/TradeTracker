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

log = logging.getLogger('paper_worker')


def run_round(runners, catalog, now):
    results = {}
    for name, runner in runners.items():
        # Disabling new entries must not abandon an existing paper position.
        if not catalog.get(name, {}).get('enabled', False) and runner.store.open_position_row() is None:
            continue
        try:
            result = runner.locked_cycle(now)
            results[name] = result
            log.info('%s: %s', name, result.get('status'))
        except Exception as exc:
            # The other strategy still runs; next minute can recover.
            results[name] = {'status': 'error', 'reason': type(exc).__name__}
            log.error('%s: %s', name, type(exc).__name__)
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
    runners = {}
    stopped = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    signal.signal(signal.SIGINT, lambda *_: stopped.set())
    log.info('Paper worker started. Provider=Dhan, interval=one minute, orders=disabled')
    while not stopped.is_set():
        now = now_ist()
        try:
            catalog = {doc.id: doc.to_dict() for doc in db.collection('algo_catalog').stream(timeout=15)}
            # Config/data provenance is pinned to the versioned implementation;
            # per-strategy model capital is read from the catalogue.
            for name, record in catalog.items():
                if name not in STRATEGIES or name == 'description' or not record.get('enabled', True) or name in runners:
                    continue
                cfg = replace(CONFIG, strategy=replace(CONFIG.strategy, capital=float(record['capital'])),
                              data=replace(CONFIG.data, provider='dhan'),
                              email=replace(CONFIG.email, enabled=False),
                              runtime=replace(CONFIG.runtime, strategy_name=name))
                runners[name] = Runner.from_config(cfg, provider=provider)
            provider.begin_round()
            run_round(runners, catalog, now)
        except Exception as exc:
            log.error('Paper worker round failed: %s', type(exc).__name__)
        # Keep running overnight; exchange calendar blocks trading/data requests.
        # Aim just after each minute boundary, allowing candle publication time.
        delay = max(1, 60 - time.time() % 60 + 5)
        stopped.wait(delay)


if __name__ == '__main__':
    main()
