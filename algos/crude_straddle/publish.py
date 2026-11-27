"""Crude Expiry Straddle (crude_strategy_12): the backtest for Algo Lab.

Writes algos/reports/crude_strategy_12_<start>_<end>/trades.csv in the ledger format
backend/export_backtest_trades.py reads, and catalog_row.json (metrics and monthly rows) next to it.
P&L is after charges and slippage, with minutes outside Dhan's strike window priced against the strategy.

    python publish.py
"""
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from forward import ENTRY, EXIT, LAST_SESSIONS
from variants import Spec, sessions, simulate

STRATEGY_ID = "crude_strategy_12"
CAPITAL = 600000.0
LOT = 100
REPORTS = Path(__file__).resolve().parents[1] / "reports"
IST = "+05:30"


def metrics(frame, start, end, cap=CAPITAL):
    """Catalogue metrics from closed trades on fixed capital (same formulas as the other listed algos)."""
    pnl = frame.pnl.to_numpy(float)
    equity = pnl.cumsum()
    drawdown = float(np.min(equity - np.maximum.accumulate(np.concatenate([[0.0], equity]))[1:])) / cap * 100
    years = (pd.Timestamp(end) - pd.Timestamp(start)).days / 365.25
    total = float(pnl.sum())
    after = pd.Timestamp(end) + pd.Timedelta(days=1)
    trailing = lambda months: float(frame.pnl[frame.exit_day >= after - pd.DateOffset(months=months)].sum()) / cap * 100
    return dict(trade_count=int(len(frame)), win_rate_pct=float((pnl > 0).mean() * 100), total_pnl=round(total, 2),
                cagr_pct=float(((cap + total) / cap) ** (1 / years) - 1) * 100, max_drawdown_pct=drawdown,
                return_1m_pct=trailing(1), return_3m_pct=trailing(3), return_6m_pct=trailing(6))


def monthly(frame, start, end, cap=CAPITAL):
    rows = []
    by_month = frame.assign(month=frame.exit_day.dt.strftime("%Y-%m"))
    for month in pd.period_range(start.strftime("%Y-%m"), end.strftime("%Y-%m"), freq="M").astype(str):
        g = by_month[by_month.month == month]
        first, last = pd.Period(month).start_time.date(), pd.Period(month).end_time.date()
        lo, hi = max(first, start), min(last, end)
        won, lost = int((g.pnl > 0).sum()), int((g.pnl < 0).sum())
        total = round(float(g.pnl.sum()), 2)
        rows.append(dict(month=month, pnl=total, pnl_rupees=total, return_pct=total / cap * 100, closed_trades=int(len(g)),
                         trade_count=int(len(g)), winning_trades=won, losing_trades=lost, breakeven_trades=int(len(g)) - won - lost,
                         win_rate_pct=(won / len(g) * 100) if len(g) else 0.0, partial_month=bool(lo != first or hi != last),
                         observed_start=lo.isoformat(), observed_end=hi.isoformat()))
    return rows


def ledger_row(result, expiry):
    call, put = result["legs"][0], result["legs"][1]
    return {"entry_ts": f"{result['entry_time']:%Y-%m-%d %H:%M:%S}{IST}", "exit_ts": f"{result['exit_time']:%Y-%m-%d %H:%M:%S}{IST}",
            "direction": "NEUTRAL", "option_type": "CE+PE", "expiry": str(expiry), "sell_strike": result["strike"], "buy_strike": result["strike"],
            "lots": 1, "units": LOT, "net_credit": round(call["entry"] + put["entry"], 2), "exit_value": round(call["exit"] + put["exit"], 2),
            "exit_reason": "Time exit", "pnl": round(result["net"], 2),
            # Both legs are sold: the "sell" columns hold the call, the "buy" columns the put.
            "sell_leg_entry": call["entry"], "buy_leg_entry": put["entry"], "sell_leg_exit": call["exit"], "buy_leg_exit": put["exit"],
            "structure": "short_straddle", "allocated_capital": CAPITAL, "pnl_before_costs": round(result["gross"], 2)}


def build():
    spec = Spec(entry=ENTRY, exit=EXIT)
    pool = sessions(max_left=LAST_SESSIONS)
    all_days = [s.date for s, _, _ in sessions(max_left=5)]
    rows = [ledger_row(r, expiry) for session, left, expiry in pool if left < LAST_SESSIONS for r in [simulate(session, spec)] if r]
    return pd.DataFrame(rows), min(all_days), max(all_days)


if __name__ == "__main__":
    from backtest import load_days
    ledger, _, _ = build()
    days = load_days()
    start, end = days[0].date, days[-1].date
    out = REPORTS / f"{STRATEGY_ID}_{start}_{end}"
    out.mkdir(parents=True, exist_ok=True)
    ledger.to_csv(out / "trades.csv", index=False)
    frame = pd.DataFrame({"pnl": ledger.pnl, "exit_day": pd.to_datetime(ledger.exit_ts.str[:10])})
    row = {"period_start": str(start), "period_end": str(end), "metrics": metrics(frame, start, end), "monthly": monthly(frame, start, end)}
    (out / "catalog_row.json").write_text(json.dumps(row, indent=1), encoding="utf-8")
    print("ledger ->", out / "trades.csv", "| trades", len(ledger), "| total", round(ledger.pnl.sum(), 2))
    print(json.dumps(row["metrics"], indent=1))
