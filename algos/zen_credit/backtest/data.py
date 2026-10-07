"""Load the published reference trades for comparison and metric regression tests."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from config import REPO_ROOT
from utils.time import IST

PROVIDER_CSV = REPO_ROOT / "data/reference/past_trade.csv"


def load_provider_legs(path: Path = PROVIDER_CSV) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["entry_ts"] = pd.to_datetime(df["Entry Date"] + " " + df["Entry Time (IST)"]).dt.tz_localize(IST)
    df["exit_ts"] = pd.to_datetime(df["Exit Date"] + " " + df["Exit Time (IST)"]).dt.tz_localize(IST)
    df["expiry"] = pd.to_datetime(df["Expiry"]).dt.date
    return df


def load_provider_trades(path: Path = PROVIDER_CSV) -> pd.DataFrame:
    """One row per provider trade (legs merged). Multi-exit trades use the
    quantity-weighted average exit price of each leg."""
    legs = load_provider_legs(path)
    out = []
    for tno, g in legs.groupby("Trade No", sort=True):
        def leg(side):
            x = g[g["Buy/Sell"] == side]
            qty = x["Qty"].sum()
            return x.iloc[0], (x["Exit Price"] * x["Qty"]).sum() / qty, int(qty)
        s, s_exit, s_qty = leg("SELL")
        b, b_exit, _ = leg("BUY")
        last = g.sort_values("exit_ts").iloc[-1]
        out.append({
            "trade_no": int(tno), "signal_id": s["Signal ID"], "entry_ts": s["entry_ts"],
            "exit_ts": last["exit_ts"], "expiry": s["expiry"], "option_type": s["Option Type"],
            "direction": "BULLISH" if s["Option Type"] == "PE" else "BEARISH",
            "sell_strike": float(s["Strike"]), "buy_strike": float(b["Strike"]),
            "sell_entry": float(s["Entry Price"]), "buy_entry": float(b["Entry Price"]),
            "sell_exit": float(s_exit), "buy_exit": float(b_exit),
            "lot_size": int(s["Lot Size"]), "units": s_qty, "lots": s_qty // int(s["Lot Size"]),
            "margin": float(s["Margin Required"]), "pnl_reported": float(s["Trade P&L (reported)"]),
            "pnl_pct_reported": float(s["Trade P&L % (reported)"]),
            "pnl_check": s["P&L Check"], "n_exit_events": g["Exit Type"].nunique(),
        })
    t = pd.DataFrame(out).sort_values("entry_ts").reset_index(drop=True)
    t["net_credit"] = (t["sell_entry"] - t["buy_entry"]).round(2)
    t["exit_value"] = (t["sell_exit"] - t["buy_exit"]).round(2)
    return t
