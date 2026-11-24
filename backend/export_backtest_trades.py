"""Upload each catalogue strategy's backtest trade ledger to Firestore algo_backtests/{strategy_id}.

Run from the repo root after a new backtest:
  algos/.venv/Scripts/python.exe backend/export_backtest_trades.py           # dry run: prints what would be written
  algos/.venv/Scripts/python.exe backend/export_backtest_trades.py --apply   # replaces every document
  algos/.venv/Scripts/python.exe backend/export_backtest_trades.py --apply ratio_strategy_03   # only the named ones
One document per strategy (one write each). GET /algos/backtest/{id} reads one document when an algo's
Past trades tab opens; the 30-second paper poll never touches this collection.
Only closed trades are exported; a position still open at the end of the replay is skipped.
"""
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / 'algos/reports'
# The ledgers whose totals the catalogue metrics were taken from (see algos/RESEARCH.md).
LEDGERS = {
    'zen_strategy_01': 'zen_strategy_01_2023-10-04_2026-09-30/trades.csv',
    'zen_strategy_02': 'zen_strategy_02_2023-10-04_2026-09-30/trades.csv',
    'ratio_strategy_03': 'ratio_strategy_03_2022-01-26_2026-11-19/trades.csv',
    'ratio_strategy_04': 'ratio_strategy_04_2022-01-26_2026-11-19/trades.csv',
    'zen_strategy_05': 'zen_strategy_05_2023-10-04_2026-11-19/trades.csv',
    'zen_strategy_06': 'zen_strategy_06_2023-10-04_2026-11-19/trades.csv',
    'ratio_strategy_08': 'ratio_strategy_08_2022-01-26_2026-11-19/trades.csv',
    'zen_strategy_10': 'zen_strategy_10_2022-01-26_2026-11-19_on_schedule/trades.csv',
}


def number(value):
    return None if value in ('', None) else round(float(value), 2)


def legs(row):
    """Entry and exit price of the sold and the bought option, or {} unless the four reproduce the trade's P&L.
    An expiry exit is each leg's intrinsic value at the official close; a hedge with no quote at the exit is
    the value the replay booked for it."""
    sell_entry, buy_entry = number(row.get('sell_leg_entry')), number(row.get('buy_leg_entry'))
    sell_exit, buy_exit = number(row.get('sell_leg_exit')), number(row.get('buy_leg_exit'))
    spot = number(row.get('settlement_spot'))
    if row['exit_reason'] == 'Expiry' and spot is not None:
        sign = 1 if row['option_type'] == 'CE' else -1
        sell_exit = round(max(sign * (spot - float(row['sell_strike'])), 0.0), 2)
        buy_exit = round(max(sign * (spot - float(row['buy_strike'])), 0.0), 2)
    elif buy_exit is None:
        buy_exit = number(row.get('hedge_carried_exit_value'))
    if None in (sell_entry, buy_entry, sell_exit, buy_exit):
        return {}
    units = float(row['units'])
    if abs(((sell_entry - buy_entry) - (sell_exit - buy_exit)) * units - float(row['pnl'])) > 0.02 * units + 1:
        return {}
    return {'sell_entry': sell_entry, 'buy_entry': buy_entry, 'sell_exit': sell_exit, 'buy_exit': buy_exit}


def ledger(strategy_id, relative):
    rows = list(csv.DictReader((REPORTS / relative).open(encoding='utf-8')))
    trades = [{
        'entry': row['entry_ts'], 'exit': row['exit_ts'], 'type': row['option_type'], 'expiry': row['expiry'],
        'sell': int(float(row['sell_strike'])), 'buy': int(float(row['buy_strike'])),
        'units': int(float(row['units'])), 'lots': int(float(row['lots'])),
        'credit': number(row['net_credit']), 'pnl': number(row['pnl']), 'reason': row['exit_reason'] or None,
        **legs(row),
    } for row in rows if row.get('exit_ts')]
    return {'strategy_id': strategy_id, 'source': f'algos/reports/{relative}',
            'capital': number(rows[0]['allocated_capital']) if rows else None,
            'generated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'trade_count': len(trades), 'open_skipped': len(rows) - len(trades),
            'total_pnl': round(sum(trade['pnl'] or 0 for trade in trades), 2), 'trades': trades}


def main():
    apply = '--apply' in sys.argv[1:]
    selected = [arg for arg in sys.argv[1:] if not arg.startswith('--')] or list(LEDGERS)
    unknown = set(selected) - set(LEDGERS)
    if unknown:
        sys.exit('Unknown strategies: ' + ', '.join(sorted(unknown)))
    bodies = [ledger(strategy_id, LEDGERS[strategy_id]) for strategy_id in selected]
    for body in bodies:
        print(body['strategy_id'], body['trade_count'], 'closed trades,', body['open_skipped'], 'open skipped, P&L', body['total_pnl'],
              '| leg prices on', sum('sell_entry' in trade for trade in body['trades']))
    if not apply:
        print('Dry run; pass --apply to write', len(bodies), 'documents to algo_backtests.')
        return
    sys.path.insert(0, str(ROOT / 'algos/zen_credit'))
    from execution.firebase_client import get_firestore_client
    db = get_firestore_client()
    for body in bodies:
        db.collection('algo_backtests').document(body['strategy_id']).set(body)
        print('wrote algo_backtests/' + body['strategy_id'])


if __name__ == '__main__':
    main()
