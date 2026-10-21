"""Three-year research harness for lowering the Zen strategies' drawdown (target: realised drawdown
within 25% of the INR 320,000 model capital).

Signals come from each Zen replay's own indicator file (alpha, alpha2 per decision minute, written by
backtest.dhan_replay), so the entry logic is exactly the pinned module's. Option closes come from the
three-year minute dataset of backtest.ratio_improve (near expiry, ATM +/-10). The simulator mirrors the
engine's Zen rules and adds switches for risk levers:

    ..\\.venv\\Scripts\\python.exe -B -m backtest.zen_improve baseline zen_strategy_01   # vs the replay ledger
    ..\\.venv\\Scripts\\python.exe -B -m backtest.zen_improve round1                     # lever scan, both Zen

Selection protocol: the Zen formulas were chosen on Jul 2025 - Oct 2026, so Oct 2023 - Jun 2025 is the
out-of-sample evidence. A variant counts only if every year stays positive, its parameter neighbours
behave alike, and the full dhan_replay confirms it.
"""
from __future__ import annotations

import sys
from datetime import date, time

import numpy as np
import pandas as pd

from backtest import ratio_improve as ri
from backtest import ratio_research as rr
from config import REPO_ROOT
from utils.time import IST

OUT = REPO_ROOT / "reports" / "zen_improve"
CAPITAL = 320000.0
STEP = 50.0
START = pd.Timestamp("2023-10-04", tz=IST)
END = pd.Timestamp("2026-09-30 23:59", tz=IST)
YEARS = ri.YEARS
HIST_START, HIST_END = date(2025, 7, 9), date(2026, 6, 30)   # dated 15:00 scheduled exit (provider history)

BASE = dict(
    entry_start=time(10, 15), entry_end=time(14, 15), dte_min=0, dte_max=99, max_premium=200.0,
    width=400, strike_off=0,
    target_mode="points", target_pts=10.0, target_frac=0.5, target_day_only=False,
    stop_pts=45.0, stop_delay=0, hard_stop_pts=None, stop_mode="premium",
    exit_mode="next_day", exit_time=time(14, 53),
    alloc=1.0, monday_frac=0.8, expiry_margin_mult=1.54, max_loss_frac=None,
    after_stop_frac=1.0, cooldown=0, max_per_day=None, daily_loss_stop=None,
    rank_lo=0.2, rank_hi=0.8, rv_max=None, eq_window=None, eq_frac=0.5,
)


# zen_strategy_02 has PROFIT_TARGET_ENABLED = False: no profit target, only stop and scheduled exit.
STRATEGY_BASE = {"zen_strategy_01": {}, "zen_strategy_02": {"target_mode": "none"}}


def zen_signal(mkt, strategy_id: str, lo=0.2, hi=0.8):
    """+1 bullish (credit put spread), -1 bearish (credit call spread) from the replay's indicator file."""
    path = REPO_ROOT / "reports" / f"{strategy_id}_2023-10-04_2026-09-30" / "indicators.csv.gz"
    ind = pd.read_csv(path)
    ind.index = pd.to_datetime(ind.pop("timestamp"), utc=True).dt.tz_convert(IST)
    ind = ind[~ind.index.duplicated(keep="last")].reindex(mkt.clock)
    a, a2 = ind["alpha"].to_numpy(), ind["alpha2"].to_numpy()
    with np.errstate(invalid="ignore"):
        return np.where((a > hi) & (a2 > hi), 1, np.where((a < lo) & (a2 < lo), -1, 0))


def _next_session(sessions, sess_pos, d):
    k = sess_pos[d] + 1
    return sessions[k] if k < len(sessions) else d


def simulate(mkt, sig, start=START, end=END, **kw) -> pd.DataFrame:
    c = {**BASE, **kw}
    sig = np.where(mkt.weekday >= 5, 0, np.asarray(sig))
    ok_time = np.array([(c["entry_start"] <= t <= c["entry_end"]) for t in mkt.times])
    cand = (sig != 0) & ok_time & (mkt.dte >= c["dte_min"]) & (mkt.dte <= c["dte_max"])
    start_i = int(np.searchsorted(mkt.clock, start)); end_i = int(np.searchsorted(mkt.clock, end, side="right")) - 1
    cand_idx = np.flatnonzero(cand); cand_idx = cand_idx[(cand_idx >= start_i) & (cand_idx <= end_i)]
    sessions = sorted(set(mkt.dates)); sess_pos = {d: k for k, d in enumerate(sessions)}
    trades, i, size_mult, blocked_until = [], start_i, 1.0, None
    day_count, day_pnl = {}, {}
    rv = ri.daily_features(mkt)["rv20"].to_numpy() if c["rv_max"] is not None else None
    pnls = []
    width = c["width"]
    while True:
        k = np.searchsorted(cand_idx, i)
        if k >= len(cand_idx):
            break
        i = int(cand_idx[k]); d = mkt.dates[i]
        if blocked_until is not None and sess_pos[d] < blocked_until:
            i += 1; continue
        if c["max_per_day"] is not None and day_count.get(d, 0) >= c["max_per_day"]:
            i += 1; continue
        if c["daily_loss_stop"] is not None and day_pnl.get(d, 0.0) <= -c["daily_loss_stop"] * CAPITAL:
            i += 1; continue
        if rv is not None and not (np.isfinite(rv[i]) and rv[i] <= c["rv_max"]):
            i += 1; continue
        side = 1 if sig[i] > 0 else 0
        atm = rr.short_strike(mkt, i, side, "open")
        sell = atm + (c["strike_off"] * STEP if side == 0 else -c["strike_off"] * STEP)
        buy = sell + width if side == 0 else sell - width
        ps, pb = mkt.price(i, sell, side), mkt.price(i, buy, side)
        if not (np.isfinite(ps) and np.isfinite(pb)) or ps - pb <= 0 or ps > c["max_premium"]:
            i += 1; continue
        credit = round(ps - pb, 2); lot = mkt.lot_of[d]; expiry = mkt.expiry_of[d]
        normal_margin = 2.25 * width * lot
        margin = normal_margin * (c["expiry_margin_mult"] if d == expiry else 1.0)
        eq_mult = c["eq_frac"] if (c["eq_window"] and len(pnls) >= c["eq_window"] and sum(pnls[-c["eq_window"]:]) < 0) else 1.0
        alloc = CAPITAL * c["alloc"] * size_mult * eq_mult * (c["monday_frac"] if (mkt.weekday[i] == 0 and d >= date(2026, 4, 6)) else 1.0)
        lots = int(alloc // margin)
        if c["max_loss_frac"] is not None:
            lots = min(lots, int(CAPITAL * c["max_loss_frac"] // (c["stop_pts"] * lot)))
        if lots <= 0:
            i += 1; continue
        if c["exit_mode"] == "expiry" or d >= expiry:
            exit_day = expiry
        else:
            exit_day = min(_next_session(sessions, sess_pos, d), expiry)
        clock_t = time(15, 0) if (c["exit_mode"] == "next_day" and HIST_START <= d <= HIST_END) else c["exit_time"]
        target = (c["target_pts"] if c["target_mode"] == "points" else
                  round(credit * (1 - c["target_frac"]), 2) if c["target_mode"] == "frac" else -np.inf)
        pos = dict(entry=mkt.clock[i], side=side, sell=sell, buy=buy, expiry=expiry, credit=credit, units=lots * lot,
                   lots=lots, target=target, stop=round(credit + c["stop_pts"], 2))
        exit_rec = None
        for j in range(i + 1, mkt.n):
            dj = mkt.dates[j]
            if dj > expiry:
                spot = mkt.close[mkt.last_idx_of_date[expiry]]
                sv = (max(spot - sell, 0) - max(spot - buy, 0)) if side == 0 else (max(sell - spot, 0) - max(buy - spot, 0))
                exit_rec = (j, sv, "expiry"); break
            sv = mkt.price(j, sell, side) - mkt.price(j, buy, side)
            if not np.isfinite(sv):
                continue
            if c["stop_mode"] == "premium" and sv >= pos["stop"] and (j - i) >= c["stop_delay"]:
                exit_rec = (j, sv, "stop"); break
            if c["hard_stop_pts"] is not None and sv >= credit + c["hard_stop_pts"]:
                exit_rec = (j, sv, "stop"); break
            if sv <= target and not (c["target_day_only"] and dj != d):
                exit_rec = (j, sv, "target"); break
            if (dj > exit_day) or (dj == exit_day and mkt.times[j] >= clock_t):
                exit_rec = (j, sv, "time"); break
        if exit_rec is None:
            break
        j, sv, reason = exit_rec
        pnl = (credit - sv) * pos["units"]
        trades.append({**pos, "exit": mkt.clock[j], "exit_value": sv, "pnl": pnl, "reason": reason})
        pnls.append(pnl)
        day_count[d] = day_count.get(d, 0) + 1
        dx = mkt.dates[j]; day_pnl[dx] = day_pnl.get(dx, 0.0) + pnl
        if reason == "stop":
            size_mult = c["after_stop_frac"]
            if c["cooldown"]:
                blocked_until = sess_pos[dx] + c["cooldown"] + 1
        elif pnl > 0:
            size_mult = 1.0
        i = j + 1
    return pd.DataFrame(trades)


def evaluate(trades: pd.DataFrame) -> dict:
    return ri.evaluate(trades)


def baseline(strategy_id: str):
    mkt = ri.load_market()
    t = simulate(mkt, zen_signal(mkt, strategy_id), **STRATEGY_BASE[strategy_id])
    replay = pd.read_csv(REPO_ROOT / "reports" / f"{strategy_id}_2023-10-04_2026-09-30" / "trades.csv")
    replay = replay[replay.exit_ts.notna()]
    print("simulator:", evaluate(t))
    print("replay   : n", len(replay), "pnl", round(replay.pnl.sum()), "win", round(100 * (replay.pnl > 0).mean(), 1),
          "stops", int((replay.exit_reason == "Stop loss").sum()))
    se = set(pd.to_datetime(replay.entry_ts, utc=True).dt.tz_convert(IST))
    te = set(t.entry)
    print("identical entry minutes:", len(se & te), "of replay", len(se), "/ simulator", len(te))


def round1():
    mkt = ri.load_market()
    rows = []
    variants = [("base", {})]
    for s in (25, 35, 60, 80):
        variants.append((f"stop={s}", dict(stop_pts=s)))
    for ml in (0.03, 0.05, 0.08):
        variants.append((f"max_loss={ml}", dict(max_loss_frac=ml)))
    for a in (0.5, 0.7):
        variants.append((f"alloc={a}", dict(alloc=a)))
    variants += [("no expiry-day entry", dict(dte_min=1)), ("dte 1-5", dict(dte_min=1, dte_max=5)),
                 ("target 50% credit", dict(target_mode="frac")),
                 ("target 50% entry day", dict(target_mode="frac", target_day_only=True)),
                 ("hold to expiry", dict(exit_mode="expiry")),
                 ("after stop half size", dict(after_stop_frac=0.5)),
                 ("cooldown 1 session", dict(cooldown=1)), ("cooldown 2 sessions", dict(cooldown=2)),
                 ("max 1 trade/day", dict(max_per_day=1)), ("daily loss stop 3%", dict(daily_loss_stop=0.03)),
                 ("entries 11:00-14:15", dict(entry_start=time(11, 0))),
                 ("rank 0.1/0.9", dict(rank_lo=0.1, rank_hi=0.9)),
                 ("stop delay 30m", dict(stop_delay=30)),
                 ("stop delay 30m + hard 90", dict(stop_delay=30, hard_stop_pts=90))]
    for sid in ("zen_strategy_01", "zen_strategy_02"):
        cache = {}
        for label, kw in variants:
            lo, hi = kw.pop("rank_lo", 0.2), kw.pop("rank_hi", 0.8)
            if (lo, hi) not in cache:
                cache[(lo, hi)] = zen_signal(mkt, sid, lo, hi)
            rows.append(dict(strategy=sid, variant=label, **evaluate(simulate(mkt, cache[(lo, hi)], **{**STRATEGY_BASE[sid], **kw}))))
            print(rows[-1], flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(OUT / "round1.csv", index=False)


def round2():
    """Combinations of the round-1 levers that raised return per unit of drawdown, plus a 20-session
    realised-volatility cap and an equity-curve throttle (half size while the last k trades lost money)."""
    import itertools
    mkt = ri.load_market()
    rows = []
    for sid in ("zen_strategy_01", "zen_strategy_02"):
        sig = zen_signal(mkt, sid)
        grid = itertools.product((25, 35, 45), (1.0, 0.5), (0, 1), (None, 0.03), (None, 16.0, 20.0), (None, 10))
        for stop, after, cool, ml, rvm, eqw in grid:
            kw = dict(stop_pts=stop, after_stop_frac=after, cooldown=cool, max_loss_frac=ml, rv_max=rvm, eq_window=eqw)
            label = f"stop{stop} after{after} cool{cool} ml{ml} rv{rvm} eq{eqw}"
            rows.append(dict(strategy=sid, variant=label, **kw, **evaluate(simulate(mkt, sig, **{**STRATEGY_BASE[sid], **kw}))))
        print(sid, "done", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    R = pd.DataFrame(rows)
    R.to_csv(OUT / "round2.csv", index=False)
    pd.set_option("display.width", 260)
    for sid in ("zen_strategy_01", "zen_strategy_02"):
        sub = R[(R.strategy == sid) & (R[["y1", "y2", "y3"]].min(axis=1) > 0)]
        print("==", sid, "top by return per drawdown (all years positive)")
        print(sub.sort_values("calmar", ascending=False).head(15)[["variant", "n", "pnl", "dd", "win", "stops", "y1", "y2", "y3", "calmar"]].to_string(index=False))


def main(argv=None):
    argv = argv or sys.argv[1:]
    cmd = argv[0] if argv else "baseline"
    if cmd == "baseline":
        for sid in (argv[1:] or ["zen_strategy_01", "zen_strategy_02"]):
            print("==", sid); baseline(sid)
    elif cmd == "round1":
        round1()
    elif cmd == "round2":
        round2()
    else:
        raise SystemExit("use baseline [ids] or round1")


if __name__ == "__main__":
    main()
