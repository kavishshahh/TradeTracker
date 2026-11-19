"""Thousand-variant search around ratio_strategy_04 (R4) on the three-year minute dataset.

backtest.ratio_improve covered R3's execution levers (about 1,500 variants) and produced R4. This module
tests levers that search never touched, with R4 as the benchmark every variant has to beat:

    round_f  signal variants under R4 execution: wing distance, smoothing span, rank window, gate levels,
             realised-volatility caps, IV ratio instead of IV difference, wing-versus-ATM confirmation
             (the "Ripple" idea), skew rate of change, persistence, one side only
    round_g  execution variants on the pinned signal: expiry-day exit time, a later-day target, a stop
             that tightens once the spread has decayed, stop confirmation, spot-conditioned stops, stops
             as a credit multiple, credit filters, strikes, per-side entry times, re-entry limits
    round_h  factorial of the levers from F and G that beat R4 in every year

    ..\\.venv\\Scripts\\python.exe -B -m backtest.ratio_variants check|round_f|round_g|round_h|all

Selection protocol (same as ratio_improve): a variant counts only if each of the three years is at least as
good as R4 (year 3 within 5%), the realized drawdown is no worse, and its parameter neighbours behave
alike. The dataset ends 30 Sep 2026; later sessions are the hold-out and are replayed with
backtest.dhan_replay, never searched here.
"""
from __future__ import annotations

import itertools
import sys
from datetime import date, time

import numpy as np
import pandas as pd

from backtest import ratio_improve as ri
from backtest import ratio_research as rr
from strategy import ratio_strategy_03_fluxer as s3
from strategy.implied_vol import implied_vol, years_to_expiry

OUT = ri.OUT
STEP = 50.0
R4 = dict(entry_start=time(11, 45), stop_pts=50.0, stop_delay=60, hard_stop_pts=100.0, target_frac=0.4)
BASE = {**ri.BASE, **R4, "exit_time": time(14, 57), "later_target": None, "trail_trigger": None, "trail_pts": 0.0,
        "stop_confirm": 1, "stop_spot_within": None, "stop_mult": None, "min_credit": None, "max_credit": None,
        "max_per_expiry": None, "day_lock": None}


# --------------------------------------------------------------------------- signal variants
def iv_panel(mkt) -> dict:
    """Spot-based Black-Scholes IV of the ATM strike and the 1-4 step wings, both sides (ce[k], pe[k])."""
    if getattr(mkt, "_ivp", None) is not None:
        return mkt._ivp
    path = OUT / "iv_panel.npz"
    if path.exists():
        z = np.load(path)
        mkt._ivp = {k: z[k] for k in z.files}
        return mkt._ivp
    spot = mkt.close
    atm = np.asarray(s3.atm_strike(spot), dtype=float)
    tyrs = years_to_expiry(mkt.clock, [mkt.expiry_of[d] for d in mkt.dates])
    rows = np.arange(mkt.n)

    def px(strike, side):
        j = np.clip(np.searchsorted(mkt.strikes, strike), 0, len(mkt.strikes) - 1)
        out = mkt.grid[rows, j, side].astype(float)
        out[mkt.strikes[j] != strike] = np.nan
        return out

    panel = {}
    for k in range(5):
        up, dn = atm + k * STEP, atm - k * STEP
        panel[f"ce{k}"] = implied_vol(px(up, 0), spot, up, tyrs, True, rate=s3.RISK_FREE_RATE)
        panel[f"pe{k}"] = implied_vol(px(dn, 1), spot, dn, tyrs, False, rate=s3.RISK_FREE_RATE)
    np.savez_compressed(path, **panel)
    mkt._ivp = panel
    return panel


_CACHE: dict = {}


def _smoothed(mkt, form, wing, ema):
    key = ("s", form, wing, ema)
    if key not in _CACHE:
        p = iv_panel(mkt)
        raw = p[f"pe{wing}"] - p[f"ce{wing}"] if form == "diff" else 100.0 * (p[f"pe{wing}"] / p[f"ce{wing}"] - 1.0)
        _CACHE[key] = s3.ema_smooth(pd.Series(raw, index=mkt.clock), mkt.dates, ema)
    return _CACHE[key]


def _rank(mkt, form, wing, ema, win):
    key = ("r", form, wing, ema, win)
    if key not in _CACHE:
        _CACHE[key] = rr.rank_window(_smoothed(mkt, form, wing, ema), win).to_numpy()
    return _CACHE[key]


def _tails(mkt):
    """Tail probabilities of the pinned gates (-3.0 / 4.5 on the 100-point EMA-10 skew), used to place the
    gates of other wings, spans and the ratio form at the same quantiles."""
    if "tails" not in _CACHE:
        s = _smoothed(mkt, "diff", 2, 10).to_numpy()
        s = s[np.isfinite(s)]
        _CACHE["tails"] = (float((s <= s3.SKEW_CALL_MAX).mean()), float((s >= s3.SKEW_PUT_MIN).mean()))
    return _CACHE["tails"]


def _ripple_rank(mkt, side, wing, ema, win=800):
    """Rank of the smoothed wing IV minus the same side's ATM IV (how rich that wing is against the money)."""
    key = ("rip", side, wing, ema, win)
    if key not in _CACHE:
        p = iv_panel(mkt)
        raw = p[f"ce{wing}"] - p["ce0"] if side == "call" else p[f"pe{wing}"] - p["pe0"]
        _CACHE[key] = rr.rank_window(s3.ema_smooth(pd.Series(raw, index=mkt.clock), mkt.dates, ema), win).to_numpy()
    return _CACHE[key]


def gate_levels(mkt, form="diff", wing=2, ema=10, cq=1.0, pq=1.0):
    """Call / put gate levels at the pinned gates' quantiles times cq / pq."""
    s = _smoothed(mkt, form, wing, ema).to_numpy()
    fin = s[np.isfinite(s)]
    qc, qp = _tails(mkt)
    pinned = (form, wing, ema) == ("diff", 2, 10)
    cm = s3.SKEW_CALL_MAX if (pinned and cq == 1.0) else float(np.quantile(fin, min(qc * cq, 0.5)))
    pm = s3.SKEW_PUT_MIN if (pinned and pq == 1.0) else float(np.quantile(fin, 1.0 - min(qp * pq, 0.5)))
    return cm, pm


def make_signal(mkt, form="diff", wing=2, ema=10, rank_win=800, cm=None, pm=None, cq=1.0, pq=1.0, lo=0.2,
                put_rv_max=s3.PUT_RV_MAX, put_rv_win=20, call_rv_max=None, ripple_q=None, ripple_side="both",
                ripple_dir="rich", ripple_ema=10, roc_lag=None, roc_mode="revert", persist_n=1, sides="both",
                call_start=None, put_start=None):
    """-1 = credit call spread, +1 = credit put spread. Defaults reproduce the pinned R3/R4 signal exactly.
    cm/pm: explicit gate levels; when None they sit at the pinned gates' quantiles times cq/pq (for the
    pinned form that is -3.0 / 4.5 at cq = pq = 1)."""
    s = _smoothed(mkt, form, wing, ema).to_numpy()
    a = _rank(mkt, form, wing, ema, rank_win)
    qcm, qpm = gate_levels(mkt, form, wing, ema, cq, pq)
    cm = qcm if cm is None else cm
    pm = qpm if pm is None else pm
    g = rr.regime(mkt)
    with np.errstate(invalid="ignore"):
        call_ok = (s <= cm) & (a < lo)
        put_ok = (s >= pm) & (a > 1 - lo)
        if put_rv_max is not None:
            put_ok &= g[f"rv{put_rv_win}"].to_numpy() <= put_rv_max
        if call_rv_max is not None:
            call_ok &= g["rv20"].to_numpy() <= call_rv_max
        if ripple_q is not None:
            for side in ("call", "put"):
                if ripple_side not in (side, "both"):
                    continue
                r = _ripple_rank(mkt, side, wing, ripple_ema)
                keep = (r > ripple_q) if ripple_dir == "rich" else (r < 1 - ripple_q)
                if side == "call":
                    call_ok &= keep
                else:
                    put_ok &= keep
        if roc_lag is not None:
            ser = _smoothed(mkt, form, wing, ema)
            d = (ser - ser.groupby(np.asarray(mkt.dates)).shift(roc_lag)).to_numpy()
            up = d > 0
            dn = d < 0
            call_ok &= up if roc_mode == "revert" else dn      # call spread: skew is low; revert = turning up
            put_ok &= dn if roc_mode == "revert" else up
    sig = np.where(call_ok, -1, np.where(put_ok, 1, 0))
    if sides == "call":
        sig = np.where(sig == 1, 0, sig)
    elif sides == "put":
        sig = np.where(sig == -1, 0, sig)
    if persist_n > 1:
        sig = rr.persist(sig, mkt.dates, persist_n)
    if call_start is not None or put_start is not None:
        tmin = _tmin(mkt)
        if call_start is not None:
            sig = np.where((sig == -1) & (tmin < call_start.hour * 60 + call_start.minute), 0, sig)
        if put_start is not None:
            sig = np.where((sig == 1) & (tmin < put_start.hour * 60 + put_start.minute), 0, sig)
    return sig


def _tmin(mkt):
    if getattr(mkt, "_tmin", None) is None:
        mkt._tmin = np.array([t.hour * 60 + t.minute for t in mkt.times])
    return mkt._tmin


# --------------------------------------------------------------------------- execution simulator
def simulate_x(mkt, sig, start=ri.START, end=ri.END, **kw) -> pd.DataFrame:
    """ri.simulate_v (premium stop only) with R4 defaults and these extra switches:
    exit_time        scheduled exit time on the exit day (R4: 14:57 on the expiry day)
    later_target     credit fraction target on the days after the entry day (None = entry-day target only)
    trail_trigger    once the spread has lost this fraction of the credit, the stop moves to
                     credit + trail_pts (no grace period; negative trail_pts locks a profit)
    stop_confirm     consecutive minutes the spread must sit at or above the stop
    stop_spot_within premium stop only while the index is within this many points of the short strike
                     on the losing side (calls: spot >= strike - x; negative x = beyond the strike)
    stop_mult        stop at credit * stop_mult instead of credit + stop_pts
    min_credit / max_credit   skip entries outside this credit range (points)
    max_per_expiry   entries allowed per expiry
    day_lock         no new entry on a day after an exit of this kind: 'any', 'target' or 'stop'"""
    c = {**BASE, **kw}
    tmin = _tmin(mkt)
    sig = np.where(mkt.weekday >= 5, 0, np.asarray(sig))
    lo_t = c["entry_start"].hour * 60 + c["entry_start"].minute
    hi_t = c["entry_end"].hour * 60 + c["entry_end"].minute
    exit_t = c["exit_time"].hour * 60 + c["exit_time"].minute
    cand = (sig != 0) & (tmin >= lo_t) & (tmin <= hi_t) & (mkt.dte >= c["dte_min"]) & (mkt.dte <= c["dte_max"])
    start_i = int(np.searchsorted(mkt.clock, start))
    end_i = int(np.searchsorted(mkt.clock, end, side="right")) - 1
    cand_idx = np.flatnonzero(cand)
    cand_idx = cand_idx[(cand_idx >= start_i) & (cand_idx <= end_i)]
    sessions = sorted(set(mkt.dates))
    sess_pos = {d: k for k, d in enumerate(sessions)}
    trades, i, size_mult, blocked_until = [], start_i, 1.0, None
    per_expiry: dict = {}
    width = c["width"]
    while True:
        k = np.searchsorted(cand_idx, i)
        if k >= len(cand_idx):
            break
        i = int(cand_idx[k])
        d = mkt.dates[i]
        if blocked_until is not None and sess_pos[d] < blocked_until:
            i += 1
            continue
        expiry = mkt.expiry_of[d]
        if c["max_per_expiry"] is not None and per_expiry.get(expiry, 0) >= c["max_per_expiry"]:
            i += 1
            continue
        side = 1 if sig[i] > 0 else 0
        atm = rr.short_strike(mkt, i, side, "open")
        sell = atm + (c["strike_off"] * STEP if side == 0 else -c["strike_off"] * STEP)
        buy = sell + width if side == 0 else sell - width
        ps, pb = mkt.price(i, sell, side), mkt.price(i, buy, side)
        if not (np.isfinite(ps) and np.isfinite(pb)) or ps - pb <= 0:
            i += 1
            continue
        credit = round(float(ps - pb), 2)
        lot = mkt.lot_of[d]
        if (c["min_credit"] is not None and credit < c["min_credit"]) or (c["max_credit"] is not None and credit > c["max_credit"]):
            i += 1
            continue
        stop_level = round(credit * c["stop_mult"], 2) if c["stop_mult"] is not None else round(credit + c["stop_pts"], 2)
        alloc = ri.CAPITAL * c["alloc"] * size_mult * (c["monday_frac"] if (mkt.weekday[i] == 0 and d >= date(2026, 4, 6)) else 1.0)
        lots = int(alloc // (2.25 * width * lot))
        if c["max_loss_frac"] is not None:
            lots = min(lots, int(ri.CAPITAL * c["max_loss_frac"] // ((stop_level - credit) * lot)))
        if lots <= 0:
            i += 1
            continue
        exit_day = expiry if c["exit_days_before"] == 0 else sessions[max(sess_pos.get(expiry, len(sessions) - 1) - c["exit_days_before"], sess_pos[d])]
        pos = dict(entry=mkt.clock[i], side=side, sell=sell, buy=buy, expiry=expiry, credit=credit, units=lots * lot, lots=lots,
                   target=round(credit * (1 - c["target_frac"]), 2), stop=stop_level)
        later = None if c["later_target"] is None else credit * (1 - c["later_target"])
        arm_at = None if c["trail_trigger"] is None else credit * (1 - c["trail_trigger"])
        armed, streak, exit_rec = False, 0, None
        for j in range(i + 1, mkt.n):
            dj = mkt.dates[j]
            if dj > expiry:
                spot = mkt.close[mkt.last_idx_of_date[expiry]]
                sv = (max(spot - sell, 0) - max(spot - buy, 0)) if side == 0 else (max(sell - spot, 0) - max(buy - spot, 0))
                exit_rec = (j, sv, "expiry")
                break
            sv = mkt.price(j, sell, side) - mkt.price(j, buy, side)
            if np.isfinite(sv):
                streak = streak + 1 if sv >= stop_level else 0
                if streak >= c["stop_confirm"] and (j - i) >= c["stop_delay"]:
                    x = c["stop_spot_within"]
                    spot = mkt.close[j]
                    if x is None or (side == 0 and spot >= sell - x) or (side == 1 and spot <= sell + x):
                        exit_rec = (j, sv, "stop")
                        break
                if c["hard_stop_pts"] is not None and sv >= credit + c["hard_stop_pts"]:
                    exit_rec = (j, sv, "stop")
                    break
                if armed and sv >= credit + c["trail_pts"]:
                    exit_rec = (j, sv, "trail")
                    break
                if arm_at is not None and sv <= arm_at:
                    armed = True
                if dj == d:
                    if sv <= pos["target"]:
                        exit_rec = (j, sv, "target")
                        break
                elif later is not None and sv <= later:
                    exit_rec = (j, sv, "target")
                    break
                if dj == exit_day and tmin[j] >= exit_t:
                    exit_rec = (j, sv, "time")
                    break
        if exit_rec is None:
            break
        j, sv, reason = exit_rec
        pnl = (credit - sv) * pos["units"]
        trades.append({**pos, "exit": mkt.clock[j], "exit_value": sv, "pnl": pnl, "reason": reason})
        per_expiry[expiry] = per_expiry.get(expiry, 0) + 1
        if reason == "stop":
            size_mult = c["after_stop_frac"]
            if c["cooldown"]:
                blocked_until = sess_pos[mkt.dates[j]] + c["cooldown"] + 1
        elif pnl > 0:
            size_mult = 1.0
        i = j + 1 if mkt.dates[j] == d or reason != "expiry" else j
        lock = c["day_lock"]
        if lock is not None and reason != "expiry" and (lock == "any" or lock == reason):
            i = max(i, mkt.last_idx_of_date[mkt.dates[j]] + 1)
    return pd.DataFrame(trades)


def evaluate(trades: pd.DataFrame) -> dict:
    out = ri.evaluate(trades)
    if trades.empty:
        return {**out, "pf": 0.0, "worst_trade": 0.0}
    loss = -float(trades.pnl[trades.pnl < 0].sum())
    out["pf"] = round(float(trades.pnl[trades.pnl > 0].sum()) / loss, 2) if loss > 0 else 99.0
    out["worst_trade"] = round(float(trades.pnl.min()))
    return out


# --------------------------------------------------------------------------- grids
def _t(h, m):
    return time(h, m)


def round_f():
    """Signal variants under R4 execution. Rows: (name, signal kwargs, simulator kwargs)."""
    v = [("R4", {}, {})]
    for wing, ema, win in itertools.product((1, 2, 3, 4), (5, 10, 20), (400, 800, 1600)):
        if (wing, ema, win) != (2, 10, 800):
            v.append((f"wing={wing * 50} ema={ema} rank={win}", dict(wing=wing, ema=ema, rank_win=win), {}))
    for cm, pm, lo in itertools.product((-2.0, -2.5, -3.0, -3.5, -4.0), (3.5, 4.5, 5.5), (0.1, 0.2, 0.3)):
        if (cm, pm, lo) != (-3.0, 4.5, 0.2):
            v.append((f"call<={cm} put>={pm} rank={lo}", dict(cm=cm, pm=pm, lo=lo), {}))
    for cap in (12, 14, 18, 20, None):
        v.append((f"put_rv20<={cap}", dict(put_rv_max=cap), {}))
    for win, cap in itertools.product((10, 30), (14, 16, 18)):
        v.append((f"put_rv{win}<={cap}", dict(put_rv_max=cap, put_rv_win=win), {}))
    for cap in (12, 14, 16, 18, 20):
        v.append((f"call_rv20<={cap}", dict(call_rv_max=cap), {}))
    for wing, ema in itertools.product((1, 2, 3), (10, 20)):
        v.append((f"ratio form wing={wing * 50} ema={ema}", dict(form="ratio", wing=wing, ema=ema), {}))
    for side, q, direction in itertools.product(("call", "put", "both"), (0.5, 0.6, 0.7, 0.8), ("rich", "cheap")):
        v.append((f"ripple {side} wing {direction} q={q}", dict(ripple_q=q, ripple_side=side, ripple_dir=direction), {}))
    for lag, mode in itertools.product((5, 15, 30), ("revert", "extend")):
        v.append((f"skew {mode} over {lag}m", dict(roc_lag=lag, roc_mode=mode), {}))
    for n in (2, 3, 5, 10, 15):
        v.append((f"persist={n}", dict(persist_n=n), {}))
    for side in ("call", "put"):
        v.append((f"{side} spreads only", dict(sides=side), {}))
    return v


def round_g():
    """Execution variants on the pinned signal."""
    v = [("R4", {}, {})]
    times = (_t(9, 20), _t(9, 45), _t(10, 30), _t(11, 30), _t(12, 30), _t(13, 30), _t(14, 30), _t(14, 57), _t(15, 15))
    for et, lt in itertools.product(times, (None, 0.6, 0.7, 0.8, 0.9, 0.95)):
        if (et, lt) != (_t(14, 57), None):
            v.append((f"expiry_exit={et:%H%M} later_target={lt}", {}, dict(exit_time=et, later_target=lt)))
    for trig, pts in itertools.product((0.25, 0.4, 0.5, 0.6, 0.75), (-10.0, 0.0, 10.0, 25.0)):
        v.append((f"trail after {trig} decay to credit{pts:+.0f}", {}, dict(trail_trigger=trig, trail_pts=pts)))
    for n, sp, dl in itertools.product((2, 3, 5, 10, 15), (40.0, 50.0, 60.0), (0, 30, 60)):
        v.append((f"stop_confirm={n} stop={sp:.0f} delay={dl}", {}, dict(stop_confirm=n, stop_pts=sp, stop_delay=dl)))
    for x, sp, dl in itertools.product((-50.0, -25.0, 0.0, 25.0, 50.0, 100.0), (40.0, 50.0, 60.0), (0, 60)):
        v.append((f"stop_if_spot_within={x:.0f} stop={sp:.0f} delay={dl}", {}, dict(stop_spot_within=x, stop_pts=sp, stop_delay=dl)))
    for m, dl in itertools.product((1.3, 1.4, 1.5, 1.6, 1.8, 2.0), (0, 30, 60)):
        v.append((f"stop=credit*{m} delay={dl}", {}, dict(stop_mult=m, stop_delay=dl)))
    for x in (40.0, 60.0, 80.0, 100.0, 120.0, 140.0):
        v.append((f"min_credit={x:.0f}", {}, dict(min_credit=x)))
    for x in (120.0, 150.0, 200.0, 250.0):
        v.append((f"max_credit={x:.0f}", {}, dict(max_credit=x)))
    for off, w in itertools.product((-2, -1, 1, 2), (300, 400, 500)):
        v.append((f"strike_off={off} width={w}", {}, dict(strike_off=off, width=w)))
    starts = (_t(10, 15), _t(11, 0), _t(11, 45), _t(12, 30))
    for cs, ps in itertools.product(starts, starts):
        if (cs, ps) != (_t(11, 45), _t(11, 45)):
            v.append((f"call_from={cs:%H%M} put_from={ps:%H%M}", dict(call_start=cs, put_start=ps), dict(entry_start=_t(10, 15))))
    for n, lock in itertools.product((1, 2, 3), (None, "any", "target", "stop")):
        v.append((f"max_per_expiry={n} day_lock={lock}", {}, dict(max_per_expiry=n, day_lock=lock)))
    for lock in ("any", "target", "stop"):
        v.append((f"day_lock={lock}", {}, dict(day_lock=lock)))
    for back, et in itertools.product((1, 2), (_t(9, 30), _t(12, 0), _t(14, 57))):
        v.append((f"exit {back} session(s) early at {et:%H%M}", {}, dict(exit_days_before=back, exit_time=et)))
    for (lo, hi), en in itertools.product(((1, 3), (1, 4), (2, 5), (2, 4)), (_t(13, 30), _t(14, 15), _t(14, 45))):
        v.append((f"dte={lo}-{hi} entry_until={en:%H%M}", {}, dict(dte_min=lo, dte_max=hi, entry_end=en)))
    return v


def run(mkt, variants, label) -> pd.DataFrame:
    rows = []
    for k, (name, sig_kw, sim_kw) in enumerate(variants):
        sig = make_signal(mkt, **sig_kw)
        rows.append(dict(variant=name, **evaluate(simulate_x(mkt, sig, **sim_kw))))
        if k % 50 == 0:
            print(f"{label}: {k + 1}/{len(variants)}", flush=True)
    out = pd.DataFrame(rows)
    base = out.iloc[0]
    out["each_year"] = (out.y1 >= base.y1) & (out.y2 >= base.y2) & (out.y3 >= base.y3 - 0.05 * abs(base.y3))
    out["beats_r4"] = out.each_year & (out.dd >= base.dd) & (out.pnl > base.pnl)
    out.to_csv(OUT / f"{label}.csv", index=False)
    return out


def round_h1():
    """Factorial of the levers that beat or tied R4 in rounds F and G (512 rows, the first is R4)."""
    v = []
    stops = (("pts", 50.0), ("mult", 1.5), ("mult", 1.6), ("mult", 1.7))
    for cap, off, ema, (kind, sv), conf, trail, et in itertools.product(
            (s3.PUT_RV_MAX, 20, 25, None), (0, -1), (10, 5), stops, (1, 3), (None, 0.5), (_t(14, 57), _t(15, 15))):
        sim = dict(strike_off=off, stop_confirm=conf, exit_time=et)
        if kind == "mult":
            sim["stop_mult"] = sv
        if trail is not None:
            sim.update(trail_trigger=trail, trail_pts=25.0)
        name = (f"put_rv<={cap} strike_off={off} ema={ema} stop={kind}{sv} confirm={conf} "
                f"trail={trail} exit={et:%H%M}")
        v.append((name, dict(put_rv_max=cap, ema=ema), sim))
    return v


CANDIDATE_SIG = dict(put_rv_max=None)
CANDIDATE_SIM = dict(strike_off=-1)


def round_h2():
    """Neighbourhood of the round-H1 candidate (no put volatility cap, short strike one step in the money):
    R4's own execution choices and the signal constants re-tested on top of it. Rows 0-1: R4, candidate."""
    v = [("R4", {}, {}), ("candidate", dict(CANDIDATE_SIG), dict(CANDIDATE_SIM))]
    starts = (_t(11, 15), _t(11, 30), _t(11, 45), _t(12, 0), _t(12, 15))
    for st, dl, tf in itertools.product(starts, (30, 60, 90), (0.3, 0.4, 0.5)):
        if (st, dl, tf) != (_t(11, 45), 60, 0.4):
            v.append((f"from={st:%H%M} grace={dl} target={tf}", dict(CANDIDATE_SIG),
                      {**CANDIDATE_SIM, "entry_start": st, "stop_delay": dl, "target_frac": tf}))
    for sp, hard in itertools.product((40.0, 45.0, 50.0, 55.0, 60.0), (80.0, 100.0, 120.0, None)):
        if (sp, hard) != (50.0, 100.0):
            v.append((f"stop={sp:.0f} hard={hard}", dict(CANDIDATE_SIG), {**CANDIDATE_SIM, "stop_pts": sp, "hard_stop_pts": hard}))
    for win, cap in itertools.product((10, 20, 30), (17, 18, 19, 20, 22, 25, 30, 40)):
        v.append((f"put_rv{win}<={cap}", dict(put_rv_max=cap, put_rv_win=win), dict(CANDIDATE_SIM)))
    for ema, lo in itertools.product((5, 8, 10, 12, 15), (0.15, 0.2, 0.25)):
        if (ema, lo) != (10, 0.2):
            v.append((f"ema={ema} rank={lo}", {**CANDIDATE_SIG, "ema": ema, "lo": lo}, dict(CANDIDATE_SIM)))
    for et in (_t(14, 30), _t(15, 5), _t(15, 15), _t(15, 25)):
        v.append((f"expiry_exit={et:%H%M}", dict(CANDIDATE_SIG), {**CANDIDATE_SIM, "exit_time": et}))
    for off in (-3, -2, 0, 1):
        v.append((f"strike_off={off}", dict(CANDIDATE_SIG), dict(strike_off=off)))
    return v


ROUNDS = {"round_f": round_f, "round_g": round_g, "round_h1": round_h1, "round_h2": round_h2}


def main(argv=None):
    argv = argv or sys.argv[1:]
    command = argv[0] if argv else "round_f"
    pd.set_option("display.width", 250)
    pd.set_option("display.max_colwidth", 70)
    mkt = ri.load_market()
    if command == "check":
        print("pinned signal reproduced:", np.array_equal(make_signal(mkt), ri.pinned_signal(mkt)))
        print("R4:", evaluate(simulate_x(mkt, make_signal(mkt))))
        print("ri :", ri.evaluate(ri.simulate_v(mkt, ri.pinned_signal(mkt), **R4)))
        return
    for name in (list(ROUNDS) if command == "all" else [command]):
        out = run(mkt, ROUNDS[name](), name)
        print(f"\n{name}: {len(out)} variants, {int(out.beats_r4.sum())} beat R4 in every year without more drawdown")
        print(out.sort_values("calmar", ascending=False).head(40).to_string(index=False))


if __name__ == "__main__":
    main()
