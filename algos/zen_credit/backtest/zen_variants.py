"""About 1,000 variants around the two Zen credit strategies (zen_strategy_01 Geometric, zen_strategy_02
Variance), searched with an untouched test period.

The minute dataset runs 4 Oct 2023 - 19 Nov 2026 (backtest.ratio_improve.Market3 to 20 Nov 2026). Every
variant is ranked on entries before 1 Oct 2026 only; 1 Oct - 19 Nov 2026 is reported next to it and never
used to choose. zen_strategy_05/06 were tuned on the first three years and then lost 19-30% of capital in
those seven weeks, so a variant has to hold up there before it is worth a full replay.

Signals are rebuilt from each family's replay indicator file (price change, lagged volume multiplier and
option volatility per decision minute, written by backtest.dhan_replay), so rank windows, the price-change
horizon, thresholds and the alpha/alpha2 combination can vary; the volume and volatility windows cannot.
Execution uses backtest.zen_improve.simulate. Costs: 2 points per unit per round trip (half when the trade
settles at expiry) plus INR 130 a trade, the research-tab convention.

    ..\\.venv\\Scripts\\python.exe -B -m backtest.zen_variants build     # dataset to 19 Nov 2026
    ..\\.venv\\Scripts\\python.exe -B -m backtest.zen_variants check     # signals and baselines vs the replays
    ..\\.venv\\Scripts\\python.exe -B -m backtest.zen_variants all       # rounds a, b, c -> reports/zen_improve
"""
from __future__ import annotations

import itertools
import pickle
import sys
import time as clock_time
from datetime import date, time

import numpy as np
import pandas as pd

from backtest import ratio_improve as ri
from backtest import zen_improve as zi
from config import REPO_ROOT
from utils.time import IST

OUT = REPO_ROOT / "reports" / "zen_improve"
MARKET = OUT / "market_2026-11-19.pkl"
CAPITAL = 320000.0
END = pd.Timestamp("2026-11-19 23:59", tz=IST)
HOLD = pd.Timestamp("2026-10-01", tz=IST)            # entries from here on are the untouched test period
YEARS = [pd.Timestamp(s, tz=IST) for s in ("2023-10-01", "2024-10-01", "2025-10-01", "2026-10-01")]
COST_POINTS, COST_FEE = 2.0, 130.0
# family -> (replay folder holding its indicators through 19 Nov 2026, simulator base)
FAMILIES = {"geometric": ("zen_strategy_05_2023-10-04_2026-11-19", {}),
            "variance": ("zen_strategy_06_2023-10-04_2026-11-19", {"target_mode": "none"})}
SIGNAL_BASE = dict(lo=0.2, hi=0.8, mode="both", w1=800, w2=300, horizon=5, persist=1, sides="both", reverse=False)

_MKT = None
_IND: dict = {}
_SIG: dict = {}


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    mkt = ri.Market3(end=date(2026, 11, 20), progress=lambda *a, **k: None)
    ri.daily_features(mkt)
    pickle.dump(mkt, open(MARKET, "wb"), protocol=5)
    print("minutes", mkt.n, "last", mkt.clock[-1], "->", MARKET)


def load_market():
    global _MKT
    if _MKT is None:
        _MKT = pickle.load(open(MARKET, "rb"))
    return _MKT


def indicators(mkt, family: str) -> pd.DataFrame:
    if family not in _IND:
        ind = pd.read_csv(REPO_ROOT / "reports" / FAMILIES[family][0] / "indicators.csv.gz")
        ind.index = pd.to_datetime(ind.pop("timestamp"), utc=True).dt.tz_convert(IST)
        _IND[family] = ind[~ind.index.duplicated(keep="last")].reindex(mkt.clock)
    return _IND[family]


def _change(mkt, horizon: int) -> np.ndarray:
    base = pd.Series(mkt.open).shift(horizon)
    return ((pd.Series(mkt.close) - base) / base).to_numpy()


def _rank(values, window: int, min_periods: int) -> np.ndarray:
    return pd.Series(values).rolling(window, min_periods=min_periods).rank(method="average", pct=True).to_numpy()


def make_signal(mkt, family: str, lo=0.2, hi=0.8, mode="both", w1=800, w2=300, horizon=5, persist=1, sides="both",
                reverse=False) -> np.ndarray:
    """+1 credit put spread, -1 credit call spread. The defaults are the pinned module's signal (read from
    the replay file); other rank windows or horizons are recomputed on the dataset's own candles."""
    ind = indicators(mkt, family)
    stored = horizon == 5
    a = ind["alpha"].to_numpy() if stored and w1 == 800 else _rank(_change(mkt, horizon), w1, w1)
    if stored and w2 == 300:
        a2 = ind["alpha2"].to_numpy()
    else:
        scale = ind["atm_volatility"].where(ind["atm_volatility"] > 0).to_numpy()
        a2 = _rank(_change(mkt, horizon) * ind["volume_ratio"].to_numpy() / scale, w2, int(round(0.9 * w2)))
    with np.errstate(invalid="ignore"):
        up = {"both": (a > hi) & (a2 > hi), "alpha": a > hi, "alpha2": a2 > hi}[mode]
        down = {"both": (a < lo) & (a2 < lo), "alpha": a < lo, "alpha2": a2 < lo}[mode]
    sig = np.where(up, 1, np.where(down, -1, 0))
    if persist > 1:                                   # the same side for `persist` consecutive minutes
        s = pd.Series(sig)
        held = (s.rolling(persist).min() == s.rolling(persist).max()).to_numpy()
        sig = np.where(held, sig, 0)
    if reverse:
        sig = -sig
    if sides == "calls":
        sig = np.where(sig > 0, 0, sig)
    elif sides == "puts":
        sig = np.where(sig < 0, 0, sig)
    return sig


def _drawdown(pnl: pd.Series) -> float:
    if pnl.empty:
        return 0.0
    eq = pnl.cumsum().to_numpy()
    return float(np.min(eq - np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:]) / CAPITAL * 100)


def evaluate(trades: pd.DataFrame) -> dict:
    """In-sample statistics (entries before 1 Oct 2026), gross and after costs, and the test period apart."""
    keys = ("n", "pnl", "net", "dd", "dd_net", "win", "pf", "edge", "y1", "y2", "y3", "ny1", "ny2", "ny3", "worst_net",
            "score", "hold_n", "hold_pnl", "hold_net", "dd_all")
    if trades.empty:
        return dict.fromkeys(keys, 0.0)
    t = trades.sort_values("exit").copy()
    t["net"] = t.pnl - COST_POINTS * np.where(t.reason == "expiry", 0.5, 1.0) * t.units - COST_FEE
    ins, hold = t[t.entry < HOLD], t[t.entry >= HOLD]
    out = dict(n=len(ins), pnl=round(float(ins.pnl.sum())), net=round(float(ins.net.sum())),
               dd=round(_drawdown(ins.pnl), 1), dd_net=round(_drawdown(ins.net), 1))
    wins, losses = ins.pnl[ins.pnl > 0], ins.pnl[ins.pnl <= 0]
    out["win"] = round(100 * len(wins) / max(len(ins), 1), 1)
    out["pf"] = round(float(wins.sum() / -losses.sum()), 2) if len(losses) and losses.sum() < 0 else 0.0
    out["edge"] = round(float(ins.pnl.sum() / ins.units.sum()), 1) if len(ins) else 0.0
    for k, (a, b) in enumerate(zip(YEARS, YEARS[1:]), 1):
        year = ins[(ins.entry >= a) & (ins.entry < b)]
        out[f"y{k}"], out[f"ny{k}"] = round(float(year.pnl.sum())), round(float(year.net.sum()))
    out["worst_net"] = min(out["ny1"], out["ny2"], out["ny3"])
    out["score"] = round((out["net"] / 3 / CAPITAL * 100) / max(abs(out["dd_net"]), 5.0), 2)
    out.update(hold_n=len(hold), hold_pnl=round(float(hold.pnl.sum())), hold_net=round(float(hold.net.sum())),
               dd_all=round(_drawdown(t.pnl), 1))
    return out


def run_one(family: str, sig_kw: dict, sim_kw: dict) -> pd.DataFrame:
    mkt = load_market()
    key = (family, tuple(sorted(sig_kw.items())))
    if key not in _SIG:
        _SIG[key] = make_signal(mkt, family, **sig_kw)
    return zi.simulate(mkt, _SIG[key], end=END, **{**FAMILIES[family][1], **sim_kw})


def _job(job):
    label, family, sig_kw, sim_kw = job
    row = dict(label=label, family=family)
    row.update({f"s_{k}": v for k, v in sig_kw.items()})
    row.update({f"x_{k}": (v.strftime("%H:%M") if isinstance(v, time) else v) for k, v in sim_kw.items()})
    row.update(evaluate(run_one(family, sig_kw, sim_kw)))
    return row


def run(jobs, name: str, workers: int = 4) -> pd.DataFrame:
    from multiprocessing import Pool
    started, rows = clock_time.time(), []
    with Pool(workers, initializer=load_market) as pool:
        for k, row in enumerate(pool.imap_unordered(_job, jobs, chunksize=2), 1):
            rows.append(row)
            if k % 50 == 0 or k == len(jobs):
                print(f"{name}: {k}/{len(jobs)} after {clock_time.time() - started:.0f}s", flush=True)
    frame = pd.DataFrame(rows).sort_values(["family", "label"]).reset_index(drop=True)
    frame.to_csv(OUT / f"variants_{name}.csv", index=False)
    return frame


# ---------------------------------------------------------------------------------------------- rounds
def round_a():
    """Signal scan at each family's own execution: thresholds x combination x horizon, rank windows,
    persistence, one side only, and the reversed (fade) signal."""
    jobs = []
    for family in FAMILIES:
        seen = set()

        def add(label, **kw):
            key = tuple(sorted(kw.items()))
            if key not in seen:
                seen.add(key)
                jobs.append((label, family, kw, {}))

        add("base")
        for (lo, hi), mode, horizon in itertools.product(
                ((0.2, 0.8), (0.15, 0.85), (0.1, 0.9), (0.25, 0.75), (0.3, 0.7)), ("both", "alpha", "alpha2"), (5, 15, 30)):
            add(f"thr{hi} {mode} h{horizon}", lo=lo, hi=hi, mode=mode, horizon=horizon)
        for w1, w2 in itertools.product((400, 800, 1600), (150, 300, 600)):
            add(f"w{w1}/{w2}", w1=w1, w2=w2)
        for persist in (3, 5, 10):
            add(f"persist{persist}", persist=persist)
        for sides in ("calls", "puts"):
            add(f"{sides} only", sides=sides)
        for mode in ("both", "alpha", "alpha2"):
            add(f"reverse {mode}", reverse=True, mode=mode)
    return jobs


def round_b():
    """Execution levers one at a time at each family's pinned signal."""
    one = [("stop25", dict(stop_pts=25)), ("stop35", dict(stop_pts=35)), ("stop60", dict(stop_pts=60)),
           ("stop80", dict(stop_pts=80)),
           ("delay30 hard90", dict(stop_delay=30, hard_stop_pts=90)), ("delay60 hard100", dict(stop_delay=60, hard_stop_pts=100)),
           ("stop50 delay60 hard100", dict(stop_pts=50, stop_delay=60, hard_stop_pts=100)),
           ("target 10 pts", dict(target_mode="points", target_pts=10)), ("target 20 pts", dict(target_mode="points", target_pts=20)),
           ("no target", dict(target_mode="none")),
           ("target 30%", dict(target_mode="frac", target_frac=0.3)), ("target 40%", dict(target_mode="frac", target_frac=0.4)),
           ("target 50%", dict(target_mode="frac", target_frac=0.5)),
           ("target 40% entry day", dict(target_mode="frac", target_frac=0.4, target_day_only=True)),
           ("target 50% entry day", dict(target_mode="frac", target_frac=0.5, target_day_only=True)),
           ("same day", dict(exit_mode="same_day")), ("hold to expiry", dict(exit_mode="expiry")),
           ("from 10:45", dict(entry_start=time(10, 45))), ("from 11:15", dict(entry_start=time(11, 15))),
           ("from 11:45", dict(entry_start=time(11, 45))), ("from 12:30", dict(entry_start=time(12, 30))),
           ("until 13:15", dict(entry_end=time(13, 15))), ("until 12:15", dict(entry_end=time(12, 15))),
           ("dte 1-5", dict(dte_min=1, dte_max=5)), ("dte 0 only", dict(dte_max=0)), ("dte 2+", dict(dte_min=2)),
           ("dte 0-1", dict(dte_max=1)),
           ("short 50 ITM", dict(strike_off=-1)), ("short 50 OTM", dict(strike_off=1)), ("short 100 OTM", dict(strike_off=2)),
           ("width 200", dict(width=200)), ("width 300", dict(width=300)),
           ("premium <= 150", dict(max_premium=150.0)), ("premium <= 250", dict(max_premium=250.0)),
           ("one a day", dict(max_per_day=1)), ("two a day", dict(max_per_day=2)),
           ("re-enter after stop only", dict(max_per_day=2, reentry_after_stop_only=True)),
           ("pause 1 session after stop", dict(cooldown=1)), ("loss cap 2.5%", dict(max_loss_frac=0.025)),
           ("loss cap 4%", dict(max_loss_frac=0.04)), ("rv <= 16", dict(rv_max=16.0)), ("rv <= 20", dict(rv_max=20.0)),
           ("lock 20%", dict(lock_trigger=0.2, lock_keep=0.0)), ("lock 30% keep 10%", dict(lock_trigger=0.3, lock_keep=0.1)),
           ("daily loss stop 3%", dict(daily_loss_stop=0.03))]
    return [(label, family, {}, kw) for family in FAMILIES for label, kw in one]


def round_c(a: pd.DataFrame):
    """The four best in-sample signals of each family (every year positive after costs) and its pinned
    signal, each with an execution grid: stop x target x exit x start x short strike x loss cap."""
    sig_cols = [c for c in a.columns if c.startswith("s_")]
    jobs = []
    for family in FAMILIES:
        rows = a[(a.family == family) & (a.worst_net > 0)].sort_values("score", ascending=False).head(4)
        signals = [{}] + [{c[2:]: (v.item() if hasattr(v, "item") else v) for c, v in r[sig_cols].items() if pd.notna(v)}
                          for _, r in rows.iterrows()]
        unique = []
        for s in signals:
            s = {k: (int(v) if k in ("w1", "w2", "horizon", "persist") else bool(v) if k == "reverse" else v) for k, v in s.items()}
            if s not in unique:
                unique.append(s)
        grid = itertools.product(
            (35, 45, 60), (("pts10", dict(target_mode="points", target_pts=10)), ("none", dict(target_mode="none")),
                           ("40%day", dict(target_mode="frac", target_frac=0.4, target_day_only=True))),
            ("next_day", "same_day", "expiry"), (time(10, 15), time(11, 45)), (0, -1), (None, 0.025))
        for stop, (tname, target), exit_mode, start, off, cap in grid:
            sim = dict(stop_pts=stop, exit_mode=exit_mode, entry_start=start, strike_off=off, max_loss_frac=cap, **target)
            for k, s in enumerate(unique):
                name = "base" if not s else " ".join(f"{a_}={b_}" for a_, b_ in s.items())
                jobs.append((f"[{name}] stop{stop} {tname} {exit_mode} {start:%H:%M} off{off} cap{cap}", family, s, sim))
    return jobs


def round_d():
    """Neighbourhood of the two signals that survived the test period (the Geometric signal held for five
    minutes, and the plain 30-minute momentum rank), both with entries from 11:45 and the 2.5% loss cap."""
    jobs = []
    held = dict(stop_pts=45, target_mode="points", target_pts=10, max_loss_frac=0.025)
    starts = (time(10, 15), time(11, 0), time(11, 15), time(11, 30), time(11, 45), time(12, 0), time(12, 15), time(12, 30))
    for persist, start in itertools.product((1, 2, 3, 4, 5, 6, 8, 10), starts):
        jobs.append((f"held{persist} from {start:%H:%M}", "geometric", dict(persist=persist), dict(held, entry_start=start)))
    for cap, stop in itertools.product((None, 0.02, 0.025, 0.03, 0.04), (35, 40, 45, 50, 60)):
        jobs.append((f"held5 11:45 cap{cap} stop{stop}", "geometric", dict(persist=5),
                     dict(held, entry_start=time(11, 45), max_loss_frac=cap, stop_pts=stop)))
    for name, target in (("5 pts", dict(target_pts=5)), ("15 pts", dict(target_pts=15)), ("20 pts", dict(target_pts=20)),
                         ("none", dict(target_mode="none")), ("50%", dict(target_mode="frac", target_frac=0.5))):
        jobs.append((f"held5 11:45 target {name}", "geometric", dict(persist=5), dict(held, entry_start=time(11, 45), **target)))
    for end in (time(13, 15), time(13, 45)):
        jobs.append((f"held5 11:45 until {end:%H:%M}", "geometric", dict(persist=5), dict(held, entry_start=time(11, 45), entry_end=end)))
    for persist, start in itertools.product((3, 5, 8), (time(11, 15), time(11, 45), time(12, 15))):
        jobs.append((f"variance held{persist} from {start:%H:%M}", "variance", dict(persist=persist),
                     dict(stop_pts=45, target_mode="none", max_loss_frac=0.025, entry_start=start)))
    momentum = dict(stop_pts=45, target_mode="none", max_loss_frac=0.025)
    for horizon, (lo, hi), start in itertools.product((15, 20, 30, 45, 60), ((0.1, 0.9), (0.15, 0.85), (0.05, 0.95)),
                                                      (time(11, 15), time(11, 45), time(12, 15))):
        jobs.append((f"momentum h{horizon} {hi} from {start:%H:%M}", "geometric",
                     dict(mode="alpha", horizon=horizon, lo=lo, hi=hi), dict(momentum, entry_start=start)))
    return jobs


def check():
    mkt = load_market()
    print("dataset", mkt.clock[0], "->", mkt.clock[-1], "minutes", mkt.n)
    for family in FAMILIES:
        ind = indicators(mkt, family)
        for name, mine in (("alpha", _rank(_change(mkt, 5), 800, 800)),
                           ("alpha2", _rank(_change(mkt, 5) * ind["volume_ratio"].to_numpy()
                                            / ind["atm_volatility"].where(ind["atm_volatility"] > 0).to_numpy(), 300, 270))):
            stored = ind[name].to_numpy()
            both = np.isfinite(stored) & np.isfinite(mine)
            print(f"{family} {name}: stored {int(np.isfinite(stored).sum())} recomputed {int(np.isfinite(mine).sum())} "
                  f"common {int(both.sum())} max abs diff {np.abs(stored[both] - mine[both]).max():.6f} "
                  f"differing > 0.01: {int((np.abs(stored[both] - mine[both]) > 0.01).sum())}")
        started = clock_time.time()
        t = run_one(family, {}, {})
        print(family, "base", evaluate(t), f"{clock_time.time() - started:.1f}s")
        replay = pd.read_csv(REPO_ROOT / "reports" / FAMILIES[family][0].replace("05", "01").replace("06", "02")
                             .replace("2026-11-19", "2026-09-30") / "trades.csv")
        replay = replay[replay.exit_ts.notna()]
        entries = set(pd.to_datetime(replay.entry_ts, utc=True).dt.tz_convert(IST))
        mine = set(t.entry[t.entry < HOLD])
        print(f"   replay to 30 Sep: n {len(replay)} pnl {replay.pnl.sum():,.0f} | same entry minutes {len(entries & mine)} "
              f"of {len(entries)} replay / {len(mine)} harness")


def main(argv=None):
    argv = argv or sys.argv[1:]
    command = argv[0] if argv else "check"
    pd.set_option("display.width", 250)
    if command == "build":
        return build()
    if command == "check":
        return check()
    if command in ("round_a", "all"):
        a = run(round_a(), "round_a")
    if command in ("round_b", "all"):
        run(round_b(), "round_b")
    if command in ("round_c", "all"):
        a = pd.read_csv(OUT / "variants_round_a.csv")
        run(round_c(a), "round_c")
    if command == "round_d":
        run(round_d(), "round_d")
    if command not in ("round_a", "round_b", "round_c", "round_d", "all"):
        raise SystemExit("use build, check, round_a, round_b, round_c, round_d or all")


if __name__ == "__main__":
    main()
