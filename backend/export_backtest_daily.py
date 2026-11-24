"""Add each listed strategy's day-by-day backtest P&L to its catalogue row, for the equity chart on the algo page.

`daily` is one entry per IST date on which a trade closed: {"day": "2026-11-19", "pnl": 7215.0}. It comes from the
same ledgers as the Past trades tab (LEDGERS in export_backtest_trades.py) and holds no strikes, sides or entry times.

Run from the repo root after a new backtest, once the catalogue row's metrics and monthly rows are updated:
  algos/.venv/Scripts/python.exe backend/export_backtest_daily.py           # rewrites backend/seed_data/algos_catalog.json
  algos/.venv/Scripts/python.exe backend/export_backtest_daily.py --apply   # also merges `daily` into algo_catalog/{id}
One write per listed strategy and no reads. A row is skipped, and reported, unless its ledger agrees with the
row's own totals: the full P&L, every monthly row and the 1, 3 and 6 month returns.
"""
import csv
import json
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from export_backtest_trades import LEDGERS, REPORTS, ROOT

SEED = ROOT / 'backend/seed_data/algos_catalog.json'
IST = ZoneInfo('Asia/Kolkata')


def months_back(day: date, count: int) -> date:
    """The same day of the month `count` months earlier (the replay's trailing-return convention)."""
    index = day.year * 12 + day.month - 1 - count
    year, month = divmod(index, 12)
    for last in (day.day, 30, 29, 28):
        try:
            return date(year, month + 1, last)
        except ValueError:
            continue
    raise ValueError(day)


def daily(relative):
    totals = {}
    for row in csv.DictReader((REPORTS / relative).open(encoding='utf-8')):
        if row.get('exit_ts'):
            day = datetime.fromisoformat(row['exit_ts']).astimezone(IST).date().isoformat()
            totals[day] = totals.get(day, 0.0) + float(row['pnl'])
    return [{'day': day, 'pnl': round(pnl, 2)} for day, pnl in sorted(totals.items())]


def mismatch(row, series):
    """Why this series cannot be the one the row's figures were taken from, or None."""
    metrics, capital = row['metrics'], row['capital']
    if abs(sum(item['pnl'] for item in series) - metrics['total_pnl']) > 1:
        return 'total P&L differs from the catalogue'
    by_month = {}
    for item in series:
        by_month[item['day'][:7]] = by_month.get(item['day'][:7], 0.0) + item['pnl']
    for month in row['monthly']:
        if abs(by_month.get(month['month'], 0.0) - month['pnl']) > 1:
            return f"month {month['month']} differs from the catalogue"
    end = date.fromisoformat(row['period_end'])
    for count in (1, 3, 6):
        lower = months_back(end, count).isoformat()
        trailing = sum(item['pnl'] for item in series if item['day'] > lower) / capital * 100
        if abs(trailing - metrics[f'return_{count}m_pct']) > 0.01:
            return f'{count}-month return differs from the catalogue ({trailing:.2f}% against {metrics[f"return_{count}m_pct"]:.2f}%)'
    return None


def main():
    apply = '--apply' in sys.argv[1:]
    rows = json.loads(SEED.read_text(encoding='utf-8'))
    done = []
    for row in rows:
        if not row.get('enabled') or row['id'] not in LEDGERS:
            row.pop('daily', None)
            continue
        series = daily(LEDGERS[row['id']])
        problem = mismatch(row, series)
        if problem:
            row.pop('daily', None)
            print(row['id'], row['name'], 'SKIPPED:', problem)
            continue
        row['daily'] = series
        done.append(row)
        print(row['id'], row['name'], len(series), 'days,', series[0]['day'], 'to', series[-1]['day'])
    SEED.write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding='utf-8', newline='\n')
    if not apply:
        print('Seed file updated; pass --apply to merge `daily` into', len(done), 'algo_catalog documents.')
        return
    sys.path.insert(0, str(ROOT / 'algos/zen_credit'))
    from execution.firebase_client import get_firestore_client
    db = get_firestore_client()
    for row in done:
        db.collection('algo_catalog').document(row['id']).set({'daily': row['daily']}, merge=True)
        print('wrote algo_catalog/' + row['id'] + '.daily')


if __name__ == '__main__':
    main()
