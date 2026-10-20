"""Three-year research harness for improving ratio_strategy_03 (drawdown first, then return).

Builds a minute dataset for 4 Oct 2023 - 30 Sep 2026 from the dhan_replay cache (offline; the replay of
ratio_strategy_03_2023-10-04_2026-09-30 must have run), then simulates rule variants on candle closes:

    ..\\.venv\\Scripts\\python.exe -B -m backtest.ratio_improve build      # -> reports/ratio_improve/market3y.pkl
    ..\\.venv\\Scripts\\python.exe -B -m backtest.ratio_improve baseline   # pinned rule vs the replay ledger

Selection protocol: the pinned gate was fitted on Oct 2025 - Sep 2026 (year 3), so years 1-2 are the only
out-of-sample evidence. A variant counts only if it improves every year (or leaves it unchanged), not just
the total, and if its parameter neighbours behave alike. Confirm winners with backtest.dhan_replay.
"""
from __future__ import annotations

import pickle
import sys
from datetime import date, time, timedelta

import numpy as np
import pandas as pd

from backtest import ratio_research as rr
from backtest.dhan_history import DhanHistoryClient, chunks, option_payload, spot_payload
from backtest.dhan_replay import parse_series
from backtest.provider_calendar import ProviderCalendar, expiries_for, lot_size
from config import REPO_ROOT
from strategy import ratio_strategy_03_fluxer as s3
from utils.time import IST

OUT = REPO_ROOT / "reports" / "ratio_improve"
REPLAY = REPO_ROOT / "reports" / "ratio_strategy_03_2023-10-04_2026-09-30"
CAPITAL = 320000.0
STEP = 50.0
START = pd.Timestamp("2023-10-04", tz=IST)
END = pd.Timestamp("2026-09-30 23:59", tz=IST)
YEARS = [("y1", pd.Timestamp("2023-10-01", tz=IST)), ("y2", pd.Timestamp("2024-10-01", tz=IST)),
         ("y3", pd.Timestamp("2025-10-01", tz=IST)), ("end", pd.Timestamp("2026-10-01", tz=IST))]


class Market3(rr.Market):
    """rr.Market built from the replay's cached requests (close only) on its 28-day grid from 2023-09-13,
    with index-only chunks before it for the realised volatility, and dated lot sizes."""

    def __init__(self, start=date(2023, 9, 13), end=date(2026, 10, 2), index_from=date(2023, 8, 16), progress=print):
        client = DhanHistoryClient(offline=True)
        cal = ProviderCalendar()
        spots, opts = [], []
        first = index_from
        while first < start:
            last = first + timedelta(days=28)
            spots.append(parse_series(client.request("intraday", spot_payload(first, last)), first, last, cal))
            first = last
        for first, last in chunks(start, end):
            spots.append(parse_series(client.request("intraday", spot_payload(first, last)), first, last, cal))
            for off in range(-10, 11):
                for side, label in (("CALL", "ce"), ("PUT", "pe")):
                    resp = client.request("rollingoption", option_payload(first, last, 1, off, side))
                    frame = parse_series((resp.get("data") or {}).get(label), first, last, cal)
                    if frame.empty:
                        continue
                    frame = frame.copy()
                    frame["minute"] = frame.index + pd.Timedelta(minutes=1)
                    frame["side"] = label
                    opts.append(frame[["minute", "side", "strike", "close"]].reset_index(drop=True))
            progress(f"chunk {first} loaded", flush=True)
        bars = pd.concat(spots).sort_index()
        bars = bars[~bars.index.duplicated(keep="last")][["open", "high", "low", "close"]].apply(pd.to_numeric)
        near = pd.concat(opts, ignore_index=True)
        for c in ("strike", "close"):
            near[c] = pd.to_numeric(near[c], errors="coerce")
        near = near.dropna().drop_duplicates(["minute", "side", "strike"], keep="last")
        self.clock = pd.DatetimeIndex(bars.index + pd.Timedelta(minutes=1))
        self.n = len(self.clock)
        self.pos = pd.Series(np.arange(self.n), index=self.clock)
        self.open, self.close = bars.open.to_numpy(float), bars.close.to_numpy(float)
        self.high, self.low = bars.high.to_numpy(float), bars.low.to_numpy(float)
        self.dates = np.array(self.clock.date)
        self.times = np.array(self.clock.time)
        udates = sorted(set(self.dates))
        self.expiry_of = {d: expiries_for(d)[0] for d in udates}
        self.lot_of = {d: lot_size(d, self.expiry_of[d]) for d in udates}
        self.dte = np.array([(self.expiry_of[d] - d).days for d in self.dates])
        self.weekday = np.array([d.weekday() for d in self.dates])
        self.strikes = np.sort(near.strike.unique())
        self.sidx = {float(k): i for i, k in enumerate(self.strikes)}
        grid = np.full((self.n, len(self.strikes), 2), np.nan, dtype=np.float32)
        m_idx = self.pos.reindex(near.minute).to_numpy()
        ok = np.isfinite(m_idx)
        si = near.strike.map(self.sidx).to_numpy()
        side = (near.side == "pe").to_numpy().astype(int)
        grid[m_idx[ok].astype(int), si[ok].astype(int), side[ok]] = near.close.to_numpy()[ok]
        self.grid = grid
        self.last_idx_of_date = pd.Series(np.arange(self.n), index=self.dates).groupby(level=0).max().to_dict()
        self.in_window = np.array([(time(10, 15) <= t <= time(14, 15)) for t in self.times])
        self.exit_time = np.array([t >= time(14, 57) for t in self.times])
        self.features = self._features()

    def price(self, i, strike, side):
        j = self.sidx.get(float(strike))
        return np.nan if j is None else float(self.grid[i, j, side])


def load_market() -> Market3:
    path = OUT / "market3y.pkl"
    if path.exists():
        import __main__
        for cls in (Market3, rr.Market):
            if not hasattr(__main__, cls.__name__):
                setattr(__main__, cls.__name__, cls)
        return pickle.load(open(path, "rb"))
    OUT.mkdir(parents=True, exist_ok=True)
    mkt = Market3()
    pickle.dump(mkt, open(path, "wb"), protocol=5)
    return mkt


def pinned_signal(mkt):
    return rr.pinned_signal(mkt)


# --------------------------------------------------------------------------- variant simulator
BASE = dict(entry_start=time(10, 15), entry_end=time(14, 15), dte_min=1, dte_max=5, strike_off=0, width=400,
            stop_mode="premium", stop_pts=45.0, stop_delay=0, spot_buffer=0.0, eod_check=time(15, 20),
            target_frac=0.5, target_day_only=True, exit_days_before=0, alloc=1.0, monday_frac=0.8,
            after_stop_frac=1.0, cooldown=0, max_loss_frac=None, hard_stop_pts=None)


def simulate_v(mkt, sig, start=START, end=END, **kw) -> pd.DataFrame:
    """rr.simulate with switches. stop_mode: 'premium' (spread >= credit + stop_pts, from stop_delay minutes
    after entry), 'spot' (index beyond the short strike by spot_buffer points), 'eod' (premium stop checked
    only at eod_check and later), 'none'. strike_off: short strike that many 50-point steps out of the money.
    exit_days_before: scheduled exit that many sessions before expiry (14:57). alloc: capital fraction;
    after_stop_frac: size multiplier after a stop until the next winner; cooldown: sessions without entries
    after a stop; max_loss_frac: lots capped so a stop loses at most this fraction of capital."""
    c = {**BASE, **kw}
    sig = np.where(mkt.weekday >= 5, 0, np.asarray(sig))
    ok_time = np.array([(c["entry_start"] <= t <= c["entry_end"]) for t in mkt.times]) if (c["entry_start"], c["entry_end"]) != (time(10, 15), time(14, 15)) else mkt.in_window
    cand = (sig != 0) & ok_time & (mkt.dte >= c["dte_min"]) & (mkt.dte <= c["dte_max"])
    start_i = int(np.searchsorted(mkt.clock, start)); end_i = int(np.searchsorted(mkt.clock, end, side="right")) - 1
    cand_idx = np.flatnonzero(cand); cand_idx = cand_idx[(cand_idx >= start_i) & (cand_idx <= end_i)]
    sessions = sorted(set(mkt.dates)); sess_pos = {d: k for k, d in enumerate(sessions)}
    trades, i, size_mult, blocked_until = [], start_i, 1.0, None
    width = c["width"]
    while True:
        k = np.searchsorted(cand_idx, i)
        if k >= len(cand_idx):
            break
        i = int(cand_idx[k]); d = mkt.dates[i]
        if blocked_until is not None and sess_pos[d] < blocked_until:
            i += 1; continue
        side = 1 if sig[i] > 0 else 0
        atm = rr.short_strike(mkt, i, side, "open")
        sell = atm + (c["strike_off"] * STEP if side == 0 else -c["strike_off"] * STEP)
        buy = sell + width if side == 0 else sell - width
        ps, pb = mkt.price(i, sell, side), mkt.price(i, buy, side)
        if not (np.isfinite(ps) and np.isfinite(pb)) or ps - pb <= 0:
            i += 1; continue
        credit = round(ps - pb, 2); lot = mkt.lot_of[d]
        alloc = CAPITAL * c["alloc"] * size_mult * (c["monday_frac"] if (mkt.weekday[i] == 0 and d >= date(2026, 4, 6)) else 1.0)
        lots = int(alloc // (2.25 * width * lot))
        if c["max_loss_frac"] is not None and c["stop_mode"] == "premium":
            lots = min(lots, int(CAPITAL * c["max_loss_frac"] // (c["stop_pts"] * lot)))
        if lots <= 0:
            i += 1; continue
        expiry = mkt.expiry_of[d]
        exit_day = expiry if c["exit_days_before"] == 0 else sessions[max(sess_pos.get(expiry, len(sessions) - 1) - c["exit_days_before"], sess_pos[d])]
        pos = dict(entry=mkt.clock[i], side=side, sell=sell, buy=buy, expiry=expiry, credit=credit, units=lots * lot, lots=lots,
                   target=round(credit * (1 - c["target_frac"]), 2), stop=round(credit + c["stop_pts"], 2))
        exit_rec = None
        for j in range(i + 1, mkt.n):
            dj = mkt.dates[j]
            if dj > expiry:
                spot = mkt.close[mkt.last_idx_of_date[expiry]]
                sv = (max(spot - sell, 0) - max(spot - buy, 0)) if side == 0 else (max(sell - spot, 0) - max(buy - spot, 0))
                exit_rec = (j, sv, "expiry"); break
            sv = mkt.price(j, sell, side) - mkt.price(j, buy, side)
            spot = mkt.close[j]
            mode = c["stop_mode"]
            if mode == "spot" and ((side == 0 and spot >= sell + c["spot_buffer"]) or (side == 1 and spot <= sell - c["spot_buffer"])):
                if np.isfinite(sv):
                    exit_rec = (j, sv, "stop"); break
            if np.isfinite(sv):
                if mode == "premium" and sv >= pos["stop"] and (j - i) >= c["stop_delay"]:
                    exit_rec = (j, sv, "stop"); break
                if c["hard_stop_pts"] is not None and sv >= credit + c["hard_stop_pts"]:
                    exit_rec = (j, sv, "stop"); break
                if mode == "eod" and sv >= pos["stop"] and mkt.times[j] >= c["eod_check"]:
                    exit_rec = (j, sv, "stop"); break
                if sv <= pos["target"] and not (c["target_day_only"] and dj != d):
                    exit_rec = (j, sv, "target"); break
                if dj == exit_day and mkt.exit_time[j]:
                    exit_rec = (j, sv, "time"); break
        if exit_rec is None:
            break
        j, sv, reason = exit_rec
        pnl = (credit - sv) * pos["units"]
        trades.append({**pos, "exit": mkt.clock[j], "exit_value": sv, "pnl": pnl, "reason": reason})
        if reason == "stop":
            size_mult = c["after_stop_frac"]
            if c["cooldown"]:
                blocked_until = sess_pos[mkt.dates[j]] + c["cooldown"] + 1
        elif pnl > 0:
            size_mult = 1.0
        i = j + 1 if mkt.dates[j] == d or reason != "expiry" else j
    return pd.DataFrame(trades)


def evaluate(trades: pd.DataFrame) -> dict:
    """Totals, per entry-year P&L, realized drawdown on fixed capital and Calmar (3-year annualised)."""
    if trades.empty:
        return dict(n=0, pnl=0.0, dd=0.0, calmar=0.0, win=0.0, stops=0, y1=0.0, y2=0.0, y3=0.0, worst=0.0)
    t = trades.sort_values("exit")
    eq = t.pnl.cumsum().to_numpy()
    dd = float(np.min(eq - np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:]) / CAPITAL * 100)
    out = dict(n=len(t), pnl=round(float(t.pnl.sum())), dd=round(dd, 1), win=round(100 * float((t.pnl > 0).mean()), 1),
               stops=int((t.reason == "stop").sum()))
    for (name, lo), (_, hi) in zip(YEARS[:-1], YEARS[1:]):
        out[name] = round(float(t.pnl[(t.entry >= lo) & (t.entry < hi)].sum()))
    out["worst"] = min(out["y1"], out["y2"], out["y3"])
    out["calmar"] = round((out["pnl"] / 3 / CAPITAL * 100) / max(abs(out["dd"]), 1.0), 2)
    return out


def daily_features(mkt) -> pd.DataFrame:
    """Causal per-minute regime columns: rr.regime (rv10/20/30, ret5, iv_atm, intraday, raw skew) plus the
    previous close's distance from its 20-session mean (%), the 10-session return (%) and the open gap (%)."""
    if getattr(mkt, "_daily", None) is not None:
        return mkt._daily
    g = rr.regime(mkt).copy()
    last = pd.Series(mkt.close, index=mkt.dates).groupby(level=0).last()
    first = pd.Series(mkt.open, index=mkt.dates).groupby(level=0).first()
    ma20 = (100 * (last / last.rolling(20).mean() - 1)).shift(1)
    ret10 = (100 * (last / last.shift(10) - 1)).shift(1)
    gap = 100 * (first / last.shift(1) - 1)
    for name, series in (("ma20", ma20), ("ret10", ret10), ("gap", gap)):
        g[name] = series.reindex(mkt.dates).to_numpy()
    mkt._daily = g
    return g


def filtered(mkt, sig, call=None, put=None):
    """Drop call (-1) / put (+1) signals where a regime rule says no: each rule is (column, op, value)."""
    g = daily_features(mkt)
    out = np.asarray(sig).copy()
    for rules, side in ((call, -1), (put, 1)):
        for column, op, value in rules or ():
            x = g[column].to_numpy()
            with np.errstate(invalid="ignore"):
                bad = (x > value) if op == ">" else (x < value)
            out = np.where((out == side) & bad, 0, out)
    return out


def round_a():
    """Single-lever variants around the pinned rule."""
    v = [("base", {}, {})]
    for s in (25, 35, 55, 70, 90, 120, 160):
        v.append((f"stop_pts={s}", {}, dict(stop_pts=s)))
    v.append(("stop=none", {}, dict(stop_mode="none")))
    for dl in (5, 15, 30, 60, 120):
        v.append((f"stop_delay={dl}", {}, dict(stop_delay=dl)))
    for t in (time(14, 30), time(15, 0), time(15, 20)):
        for s in (45, 70, 100):
            v.append((f"eod_stop@{t:%H%M} pts={s}", {}, dict(stop_mode="eod", eod_check=t, stop_pts=s)))
    for b in (0, 25, 50, 100, 150):
        v.append((f"spot_stop buffer={b}", {}, dict(stop_mode="spot", spot_buffer=b)))
    for st in (time(10, 30), time(10, 45), time(11, 0), time(11, 30)):
        v.append((f"entry_from={st:%H%M}", {}, dict(entry_start=st)))
    for en in (time(12, 30), time(13, 0), time(13, 30)):
        v.append((f"entry_until={en:%H%M}", {}, dict(entry_end=en)))
    for lo, hi in ((1, 1), (1, 2), (1, 3), (2, 5), (3, 5), (1, 4)):
        v.append((f"dte={lo}-{hi}", {}, dict(dte_min=lo, dte_max=hi)))
    for off in (1, 2, 3, 4):
        v.append((f"strike_off={off}", {}, dict(strike_off=off)))
    for w in (200, 300, 500, 600):
        v.append((f"width={w}", {}, dict(width=w)))
    for tf in (0.3, 0.4, 0.6, 0.7, 0.8):
        v.append((f"target={tf}", {}, dict(target_frac=tf)))
    for tf in (0.5, 0.7):
        v.append((f"target={tf} every day", {}, dict(target_frac=tf, target_day_only=False)))
    v.append(("exit 1 session early", {}, dict(exit_days_before=1)))
    for x in (0.5, 1.0, 1.5, 2.0, 3.0):
        v.append((f"no call if ret5>{x}", dict(call=[("ret5", ">", x)]), {}))
        v.append((f"no put if ret5<-{x}", dict(put=[("ret5", "<", -x)]), {}))
    for x in (0.0, 1.0, 2.0, 3.0):
        v.append((f"no call if ma20>{x}", dict(call=[("ma20", ">", x)]), {}))
        v.append((f"no put if ma20<-{x}", dict(put=[("ma20", "<", -x)]), {}))
    for x in (2.0, 4.0):
        v.append((f"no call if ret10>{x}", dict(call=[("ret10", ">", x)]), {}))
    for x in (0.3, 0.6, 1.0):
        v.append((f"no call if gap>{x}", dict(call=[("gap", ">", x)]), {}))
        v.append((f"no put if gap<-{x}", dict(put=[("gap", "<", -x)]), {}))
    for x in (50, 100, 150):
        v.append((f"no call if intraday>{x}", dict(call=[("intraday", ">", x)]), {}))
        v.append((f"no put if intraday<-{x}", dict(put=[("intraday", "<", -x)]), {}))
    for x in (12, 14, 16, 18, 20):
        v.append((f"no call if rv20>{x}", dict(call=[("rv20", ">", x)]), {}))
    for x in (10, 12, 14):
        v.append((f"no trade if rv20<{x}", dict(call=[("rv20", "<", x)], put=[("rv20", "<", x)]), {}))
    for x in (10, 12, 14, 16, 20):
        v.append((f"no trade if iv_atm>{x}", dict(call=[("iv_atm", ">", x)], put=[("iv_atm", ">", x)]), {}))
        v.append((f"no trade if iv_atm<{x}", dict(call=[("iv_atm", "<", x)], put=[("iv_atm", "<", x)]), {}))
    for cd in (1, 2, 3, 5):
        v.append((f"cooldown={cd}", {}, dict(cooldown=cd)))
    for f in (0.5, 0.25):
        v.append((f"after_stop_size={f}", {}, dict(after_stop_frac=f)))
    for a in (0.5, 0.75):
        v.append((f"alloc={a}", {}, dict(alloc=a)))
    for m in (0.03, 0.04):
        v.append((f"max_loss={m}", {}, dict(max_loss_frac=m)))
    return v


ROUND_B_STARTS = [time(10, 15), time(10, 45), time(10, 50), time(10, 55), time(11, 0), time(11, 5), time(11, 10),
                  time(11, 15), time(11, 20), time(11, 30), time(11, 45), time(12, 0)]


def round_b():
    """Grid over the round-A survivors: entry start x stop size x stop delay x hedge width x target."""
    import itertools
    v = [("base", {}, {})]
    for st, sp, dl, w, tf in itertools.product(ROUND_B_STARTS, (45, 55, 65), (0, 15, 30), (300, 400), (0.4, 0.5)):
        v.append((f"from={st:%H%M} stop={sp} delay={dl} width={w} target={tf}", {},
                  dict(entry_start=st, stop_pts=sp, stop_delay=dl, width=w, target_frac=tf)))
    return v


def round_c():
    """Later starts and entry cut-offs around the round-B region (400-point hedge)."""
    import itertools
    v = [("base", {}, {})]
    starts = [time(11, 30), time(11, 45), time(12, 0), time(12, 15), time(12, 30), time(12, 45), time(13, 0)]
    for st, en, sp, dl, tf in itertools.product(starts, (time(13, 45), time(14, 15), time(14, 38)), (40, 45, 50, 55), (15, 30, 45), (0.3, 0.4, 0.5)):
        v.append((f"from={st:%H%M} until={en:%H%M} stop={sp} delay={dl} target={tf}", {},
                  dict(entry_start=st, entry_end=en, stop_pts=sp, stop_delay=dl, target_frac=tf)))
    return v


CANDIDATE = dict(entry_start=time(11, 45), stop_pts=45, stop_delay=30, target_frac=0.4)


def round_d():
    """Round-A levers re-tested on top of CANDIDATE (first row = candidate itself)."""
    out = [("candidate", {}, dict(CANDIDATE))]
    for name, filt, sim in round_a()[1:]:
        if any(k in sim for k in ("entry_start",)):
            continue
        out.append((name, filt, {**CANDIDATE, **sim}))
    for sp in (38, 40, 42, 48, 50):
        out.append((f"stop_pts={sp}", {}, {**CANDIDATE, "stop_pts": sp}))
    for st in (time(11, 40), time(11, 50), time(11, 55)):
        out.append((f"entry_from={st:%H%M}", {}, {**CANDIDATE, "entry_start": st}))
    return out


def round_e():
    """Stop size x grace period x disaster stop x size-after-stop, on CANDIDATE."""
    import itertools
    out = [("candidate", {}, dict(CANDIDATE))]
    for sp, dl, hard, after in itertools.product((45, 50, 55), (30, 60, 90, 120), (None, 100, 150), (1.0, 0.5)):
        out.append((f"stop={sp} delay={dl} hard={hard} after_stop={after}", {},
                    {**CANDIDATE, "stop_pts": sp, "stop_delay": dl, "hard_stop_pts": hard, "after_stop_frac": after}))
    return out


def run_variants(mkt, variants, label):
    base_sig = pinned_signal(mkt)
    rows = []
    for name, filt, sim in variants:
        sig = filtered(mkt, base_sig, **filt) if filt else base_sig
        rows.append(dict(variant=name, **evaluate(simulate_v(mkt, sig, **sim))))
    out = pd.DataFrame(rows)
    out.to_csv(OUT / f"{label}.csv", index=False)
    base = out.iloc[0]
    out["better_each_year"] = (out.y1 >= base.y1) & (out.y2 >= base.y2) & (out.y3 >= base.y3 - 0.05 * abs(base.y3))
    return out


def main(argv=None):
    argv = argv or sys.argv[1:]
    command = argv[0] if argv else "baseline"
    pd.set_option("display.width", 250)
    if command == "build":
        path = OUT / "market3y.pkl"
        if path.exists():
            path.unlink()
        mkt = load_market()
        print("minutes", mkt.n, "strikes", len(mkt.strikes), "->", path)
        return
    mkt = load_market()
    if command == "baseline":
        tr = rr.simulate(mkt, pinned_signal(mkt), start=START, end=END, target_entry_day_only=True)
        tr = tr[tr.reason != "open"]
        replay = pd.read_csv(REPLAY / "trades.csv", parse_dates=["entry_ts"])
        print("harness", len(tr), round(tr.pnl.sum()), "| replay", len(replay), round(replay.pnl.sum()))
        both = set(tr.entry) & set(replay.entry_ts)
        print("same entry minutes", len(both))
        miss = sorted(set(replay.entry_ts) - set(tr.entry)); extra = sorted(set(tr.entry) - set(replay.entry_ts))
        print("replay only", [str(x) for x in miss]); print("harness only", [str(x) for x in extra])
        return
    if command == "simcheck":
        tr = simulate_v(mkt, pinned_signal(mkt))
        print(evaluate(tr))
        return
    if command == "round_a":
        out = run_variants(mkt, round_a(), "round_a")
        print(out.sort_values("calmar", ascending=False).to_string(index=False))
        return
    if command == "round_e":
        out = run_variants(mkt, round_e(), "round_e")
        print(out.sort_values("calmar", ascending=False).to_string(index=False))
        return
    if command == "round_d":
        out = run_variants(mkt, round_d(), "round_d")
        print(out.sort_values("calmar", ascending=False).to_string(index=False))
        return
    if command == "round_c":
        out = run_variants(mkt, round_c(), "round_c")
        print(out.sort_values("calmar", ascending=False).head(25).to_string(index=False))
        return
    if command == "round_b":
        out = run_variants(mkt, round_b(), "round_b")
        print(out.sort_values("calmar", ascending=False).head(40).to_string(index=False))
        return
    raise SystemExit(f"unknown command {command}")


if __name__ == "__main__":
    main()
