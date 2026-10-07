"""Firestore paper dashboard read model; production execution state is Firestore.

Only simulated positions are exported. Does not place orders or change signals.
Enable with PAPER_FIREBASE_ENABLED=true and server-side Firebase credentials.
"""
from datetime import date, datetime
import json
import math
import os

FIELDS = ('signal_id', 'status', 'direction', 'entry_ts', 'expiry', 'option_type',
          'sell_strike', 'buy_strike', 'lots', 'units', 'sell_price', 'buy_price',
          'net_credit', 'stop_loss', 'target', 'exit_due', 'alpha', 'alpha2',
          'exit_ts', 'exit_value', 'exit_reason', 'pnl')


def public_trade(row):
    result = {}
    for name in FIELDS:
        value = getattr(row, name)
        if isinstance(value, (date, datetime)):
            value = value.isoformat()
        elif isinstance(value, float) and not math.isfinite(value):
            value = None
        result[name] = value
    return result


def build_snapshot(runner, cycle):
    store = runner.store
    opened = store.open_position_row()
    closed = store.closed_positions(limit=200)
    mtm = None
    mark_time = None
    if hasattr(store, 'paper_totals_and_mark'):
        totals, quote = store.paper_totals_and_mark(opened)
        if quote:
            mtm = (opened.entry_spread_price - (quote['sell'] - quote['buy'])) * opened.units
            mark_time = quote['minute'].isoformat()
    else:
        # Legacy adapter retained for isolated PostgreSQL regression fixtures.
        with store._cursor(dict_rows=True) as cur:
            cur.execute("SELECT COUNT(*) AS closed_trades, COUNT(*) FILTER (WHERE pnl>0) AS winners, "
                        "COUNT(*) FILTER (WHERE pnl IS NULL) AS unknown_pnl, SUM(pnl) AS realized_pnl "
                        "FROM zc_positions WHERE status='closed'")
            totals = dict(cur.fetchone())
            mtm = None
            mark_time = None
            if opened is not None:
                side = 'ce_ltp' if opened.option_type == 'CE' else 'pe_ltp'
                cur.execute(f"SELECT s.minute, s.{side} AS sell, b.{side} AS buy "
                            "FROM zc_option_snapshots s JOIN zc_option_snapshots b "
                            "ON s.minute=b.minute AND s.expiry=b.expiry "
                            "WHERE s.expiry=%s AND s.strike=%s AND b.strike=%s "
                            f"AND s.{side} IS NOT NULL AND b.{side} IS NOT NULL "
                            "AND s.minute<=%s ORDER BY s.minute DESC LIMIT 1",
                            (opened.expiry, opened.sell_strike, opened.buy_strike, datetime.now().astimezone()))
                quote = cur.fetchone()
                if quote:
                    mtm = (opened.entry_spread_price - (quote['sell'] - quote['buy'])) * opened.units
                    mark_time = quote['minute'].isoformat()
    count = totals['closed_trades']
    known = not totals['unknown_pnl']
    last_context = runner.last_context
    return {'strategy': runner.strategy_name, 'execution': 'paper_only',
            'capital': runner.cfg.strategy.capital,
            'updated_at': datetime.now().astimezone().isoformat(),
            'last_evaluation': store.get_state('last_evaluation'),
            'status': cycle.get('status'),
            'alpha': last_context.get('alpha'), 'alpha2': last_context.get('alpha2'),
            'signal_at': last_context.get('minute'),
            'open_position': public_trade(opened) if opened else None,
            'closed_positions': [public_trade(row) for row in closed],
            'ledger_limit': 200, 'closed_trades': count,
            'realized_pnl': float(totals['realized_pnl'] or 0) if known else None,
            'win_rate_pct': totals['winners'] / count * 100 if count and known else None,
            'unrealized_pnl': mtm, 'valuation_ts': mark_time,
            'cost_basis': 'gross_before_costs', 'data_provider': runner.cfg.data.provider}


def publish_paper_snapshot(runner, cycle):
    default = 'true' if hasattr(runner.store, 'publish_dashboard') else 'false'
    if os.getenv('PAPER_FIREBASE_ENABLED', default).lower() != 'true':
        return
    if cycle.get('status') in ('busy', 'db_unavailable', 'strategy_state_mismatch'):
        return
    payload = build_snapshot(runner, cycle)
    json.dumps(payload, allow_nan=False)
    if hasattr(runner.store, 'publish_dashboard'):
        runner.store.publish_dashboard(payload)
    else:
        from execution.firebase_client import get_firestore_client
        get_firestore_client().collection('algo_paper_state').document(runner.strategy_name).set(payload, retry=None, timeout=8)
