"""Crude Expiry Straddle: forward (paper) test with the rules frozen on 28 Nov 2026.

Rules: on the last 2 sessions of the monthly CRUDEOIL option series (expiry day and the session before),
sell the at-the-money call and put at 16:30 and buy both back at 23:00. One lot (100 barrels), no stop.
Two results are shown per day: ``net`` prices minutes outside Dhan's strike window from real quotes in the
least favourable way, ``net_formula`` prices them with Black-76.

No orders are placed anywhere. Each run downloads the sessions that have finished since the last run from
Dhan and prices the trades from those 1-minute bars, with the same code as the backtest, so the ledger
below is out-of-sample: every date in it is after the day the rules were fixed.

    python forward.py            # update data, print and save the ledger
    python forward.py --offline  # no download
    python forward.py --publish  # also write the result to Algo Lab's paper tab (one Firestore document)
Needs a current DHAN_ACCESS_TOKEN in backend/.env for the download.
"""
import argparse
import io
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

from backtest import STORE, load_days

FROZEN = date(2026, 11, 27)          # last session seen when the rules were fixed; only later dates count
ENTRY, EXIT = "16:30", "23:00"
LAST_SESSIONS = 2
HERE = Path(__file__).resolve().parent
LEDGER = STORE / "forward_ledger.csv"
STRATEGY_ID = "crude_strategy_12"
CAPITAL = 600000.0
LOT = 100


def paper_state(results, upcoming):
    """The Algo Lab paper-tab document (the shape execution/firebase_paper.py publishes), from closed forward
    trades. Both options are sold: the call sits in the sell fields and the put in the buy fields."""
    from datetime import datetime, timezone
    trades = []
    for expiry, r in results:
        call, put = r["legs"][0], r["legs"][1]
        stamp = lambda t: f"{t:%Y-%m-%dT%H:%M:%S}+05:30"
        trades.append({"signal_id": f"crude-{r['date']}", "status": "closed", "direction": "NEUTRAL", "entry_ts": stamp(r["entry_time"]),
                       "expiry": str(expiry), "option_type": "CE+PE", "sell_strike": r["strike"], "buy_strike": r["strike"], "lots": 1, "units": LOT,
                       "sell_price": call["entry"], "buy_price": put["entry"], "net_credit": round(call["entry"] + put["entry"], 2),
                       "stop_loss": None, "target": None, "exit_due": stamp(r["exit_time"]), "alpha": None, "alpha2": None,
                       "exit_ts": stamp(r["exit_time"]), "exit_value": round(call["exit"] + put["exit"], 2), "exit_reason": "Time exit",
                       "pnl": round(r["net"], 2), "sell_exit_price": call["exit"], "buy_exit_price": put["exit"], "structure": "short_straddle"})
    trades.sort(key=lambda t: t["exit_ts"], reverse=True)
    count = len(trades)
    now = datetime.now(timezone.utc).astimezone().isoformat()
    return {"strategy": STRATEGY_ID, "execution": "daily_replay", "capital": CAPITAL, "updated_at": now,
            "last_evaluation": trades[0]["exit_ts"] if trades else None,
            "status": "next_trades_" + "_and_".join(f"{d:%d_%b}" for d in upcoming[:2]) if upcoming else "daily_replay",
            "alpha": None, "alpha2": None, "signal_at": None, "open_position": None, "closed_positions": trades[:200], "ledger_limit": 200,
            "closed_trades": count, "realized_pnl": round(sum(t["pnl"] for t in trades), 2),
            "win_rate_pct": sum(t["pnl"] > 0 for t in trades) / count * 100 if count else None,
            "unrealized_pnl": None, "valuation_ts": None, "cost_basis": "net_after_costs_worst_case_pricing", "data_provider": "dhan_replay"}


def expiries(refresh=True):
    """CRUDEOIL option expiry dates from every saved Dhan instrument list (a list only holds live series)."""
    newest = sorted(STORE.glob("mcx_master_*.csv"))[-1]
    if refresh and date.fromisoformat(newest.stem[-10:]) < date.today() - timedelta(days=20):
        r = requests.get("https://images.dhan.co/api-data/api-scrip-master-detailed.csv", timeout=120)
        if r.status_code == 200:
            m = pd.read_csv(io.StringIO(r.text), low_memory=False)
            m.loc[m.EXCH_ID.eq("MCX")].to_csv(STORE / f"mcx_master_{date.today()}.csv", index=False)
    found = set()
    for path in STORE.glob("mcx_master_*.csv"):
        m = pd.read_csv(path, low_memory=False)
        m = m.loc[m.UNDERLYING_SYMBOL.eq("CRUDEOIL") & m.INSTRUMENT.eq("OPTFUT")]
        found.update(pd.to_datetime(m.SM_EXPIRY_DATE).dt.date)
    return sorted(found)


def trade_dates(expiry_dates, count=LAST_SESSIONS):
    """The last ``count`` weekdays up to each expiry. An exchange holiday in that window is not known here;
    a day with no session simply has no data and no trade."""
    out = {}
    for expiry in expiry_dates:
        day, picked = expiry, []
        while len(picked) < count:
            if day.weekday() < 5:
                picked.append(day)
            day -= timedelta(days=1)
        for left, d in enumerate(picked):
            out[d] = (expiry, left)
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--offline", action="store_true")
    p.add_argument("--publish", action="store_true", help="write the forward result to Firestore algo_paper_state")
    a = p.parse_args()
    folder = STORE / "rolling_CRUDEOIL"
    if not a.offline:
        have = sorted(x.name[:10] for x in folder.glob("*.csv.gz"))
        start = date.fromisoformat(have[-1]) + timedelta(days=1)
        if start < date.today():
            subprocess.run([sys.executable, str(HERE / "download_rolling.py"), "--start", str(start)], check=False)
    plan = trade_dates(expiries(refresh=not a.offline))
    from variants import Session, Spec, simulate
    rows, results = [], []
    for d in load_days():
        if d.date > FROZEN and d.date in plan:
            session = Session(d, plan[d.date][0])
            worst = simulate(session, Spec(entry=ENTRY, exit=EXIT))
            formula = simulate(session, Spec(entry=ENTRY, exit=EXIT, pricing="model"))
            if worst and formula:
                results.append((plan[d.date][0], {**worst, "date": d.date}))
                rows.append({"date": d.date, "sessions_left": plan[d.date][1], "future": round(worst["future"], 1), "credit": worst["credit"],
                             "move_pct": worst["move_pct"], "estimated_minutes": worst["modelled"], "net": round(worst["net"]),
                             "net_formula": round(formula["net"])})
    trades = pd.DataFrame(rows)
    pd.set_option("display.width", 250)
    if trades.empty:
        print("No forward trades yet.")
    else:
        trades["cumulative"] = trades.net.cumsum()
        trades["cumulative_formula"] = trades.net_formula.cumsum()
        trades.to_csv(LEDGER, index=False)
        print(trades.to_string(index=False))
        print("days", len(trades), "| net", int(trades.net.sum()), "| net (formula)", int(trades.net_formula.sum()),
              "| winning days", int((trades.net > 0).sum()), "| worst day", int(trades.net.min()))
    upcoming = sorted(d for d in plan if d >= date.today())[:6]
    print("Next trade dates:", ", ".join(str(d) for d in upcoming))
    if a.publish:
        import json
        body = paper_state(results, upcoming)
        json.dumps(body, allow_nan=False)
        sys.path.insert(0, str(HERE.parent / "zen_credit"))
        from execution.firebase_client import get_firestore_client
        get_firestore_client().collection("algo_paper_state").document(STRATEGY_ID).set(body)
        print("wrote algo_paper_state/" + STRATEGY_ID, "| closed trades", body["closed_trades"])
