"""Fast research harness for ratio_strategy_03: rebuild the minute dataset from the Dhan cache,
derive the IV-skew features, simulate candidate entry rules in a tenth of a second each and
score them against the published Ratio-Fluxer trades.

Run from zen_credit (offline cache from 18 June 2025; downloads nothing):

    ..\\.venv\\Scripts\\python.exe -B -m backtest.ratio_research build      # -> reports/ratio_research/market.pkl
    ..\\.venv\\Scripts\\python.exe -B -m backtest.ratio_research baseline   # pinned rule, ledger + score
    ..\\.venv\\Scripts\\python.exe -B -m backtest.ratio_research grid       # smoothing / gate / persistence grid

The simulator mirrors the engine rules of the named module (opening-ATM short strike, 400-point
hedge, 50% credit target, credit + 45 stop, 14:57 exit on expiry day, settlement at the expiry-day
last close when quotes are missing, Monday 80% allocation) on candle closes. It is a research tool:
confirm any candidate with backtest.dhan_replay before pinning it in the strategy module.
"""
from __future__ import annotations

import itertools
import pickle
import sys
from datetime import date, time
from pathlib import Path

import numpy as np
import pandas as pd

from backtest.dhan_history import DhanHistoryClient, chunks, spot_payload
from backtest.dhan_replay import parse_series
from backtest.provider_calendar import ProviderCalendar, expiries_for
from config import REPO_ROOT
from strategy import ratio_strategy_03_fluxer as s3
from strategy.implied_vol import implied_vol, years_to_expiry
from utils.time import IST

OUT = REPO_ROOT / "reports" / "ratio_research"
PUBLISHED = REPO_ROOT.parent / "ratio-fluxer-past-trades.csv"
CAPITAL = 320000.0
WIDTH = 400
STEP = 50.0
START = pd.Timestamp("2025-10-01", tz=IST)
END = pd.Timestamp("2026-09-30 23:59", tz=IST)
FULL_FIELDS = ["open", "high", "low", "close", "volume", "strike", "spot", "iv", "oi"]


# --------------------------------------------------------------------------- published trades
def load_published() -> pd.DataFrame:
    import csv
    import re
    mon = {m: i for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}

    def last_tuesday(y, m):
        d = (date(y, m, 28) + pd.Timedelta(days=4)).replace(day=1) - pd.Timedelta(days=1)
        while d.weekday() != 1:
            d -= pd.Timedelta(days=1)
        return d.date() if hasattr(d, "date") else d

    def parse(sym):
        m = re.match(r"NIFTY(\d{2})([A-Z]{3})(\d{2})(\d{5})(CE|PE)$", sym)
        if m and m.group(2) in mon:
            d, mo, y, k, t = m.groups()
            return date(2000 + int(y), mon[mo], int(d)), int(k), t
        m = re.match(r"NIFTY(\d{2})([A-Z]{3})(\d{5})(CE|PE)$", sym)
        if m and m.group(2) in mon:
            y, mo, k, t = m.groups()
            return pd.Timestamp(last_tuesday(2000 + int(y), mon[mo])).date(), int(k), t
        m = re.match(r"NIFTY(\d{2})([1-9OND])(\d{2})(\d{5})(CE|PE)$", sym)
        if m:
            y, mo, d, k, t = m.groups()
            mo = {"O": 10, "N": 11, "D": 12}.get(mo, mo)
            return date(2000 + int(y), int(mo), int(d)), int(k), t
        raise ValueError(sym)

    rows = []
    for r in csv.DictReader(open(PUBLISHED, encoding="utf-8-sig")):
        legs = [(r[f"leg{i}_side"], r[f"leg{i}_symbol"], float(r[f"leg{i}_entry_price"]), float(r[f"leg{i}_exit_price"])) for i in (1, 2)]
        sell = next(l for l in legs if l[0] == "SELL")
        buy = next(l for l in legs if l[0] == "BUY")
        exp, ks, t = parse(sell[1])
        _, kb, _ = parse(buy[1])
        rows.append(dict(entry=pd.Timestamp(r["entry_datetime"], tz=IST), exit=pd.Timestamp(r["exit_datetime"], tz=IST),
                         side=t, sell=ks, buy=kb, expiry=exp, credit=round(sell[2] - buy[2], 2), pnl=float(r["pnl_inr"])))
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- market dataset
class Market:
    """Minute grid of index candles and near-expiry option closes (ATM +/-10) with own IV features."""

    def __init__(self, start=date(2025, 6, 18), end=date(2026, 10, 17), progress=print):
        client = DhanHistoryClient(offline=True)
        cal = ProviderCalendar()
        spots, opts = [], []
        for first, last in chunks(start, end):
            try:
                spots.append(parse_series(client.request("intraday", spot_payload(first, last)), first, last, cal))
            except RuntimeError as exc:
                progress(f"missing index chunk {first}: {exc}")
                continue
            for off in range(-10, 11):
                for side, label in (("CALL", "ce"), ("PUT", "pe")):
                    payload = {"securityId": 13, "exchangeSegment": "NSE_FNO", "instrument": "OPTIDX", "interval": "1",
                               "expiryFlag": "WEEK", "expiryCode": 1, "strike": "ATM" if off == 0 else f"ATM{off:+d}",
                               "drvOptionType": side, "requiredData": FULL_FIELDS,
                               "fromDate": first.isoformat(), "toDate": last.isoformat()}
                    try:
                        resp = client.request("rollingoption", payload)
                    except RuntimeError:
                        continue
                    frame = parse_series((resp.get("data") or {}).get(label), first, last, cal)
                    if frame.empty:
                        continue
                    frame = frame.copy()
                    frame["minute"] = frame.index + pd.Timedelta(minutes=1)
                    frame["side"] = label
                    frame["offset"] = off
                    opts.append(frame[["minute", "side", "offset", "strike", "close", "iv"]].reset_index(drop=True))
            progress(f"chunk {first} loaded", flush=True)
        bars = pd.concat(spots).sort_index()
        bars = bars[~bars.index.duplicated(keep="last")]
        near = pd.concat(opts, ignore_index=True)
        for c in ("strike", "close", "iv"):
            near[c] = pd.to_numeric(near[c], errors="coerce")
        self.clock = pd.DatetimeIndex(bars.index + pd.Timedelta(minutes=1))
        self.n = len(self.clock)
        self.pos = pd.Series(np.arange(self.n), index=self.clock)
        self.open = bars.open.to_numpy(float)
        self.close = bars.close.to_numpy(float)
        self.dates = np.array(self.clock.date)
        self.times = np.array(self.clock.time)
        udates = sorted(set(self.dates))
        self.expiry_of = {d: expiries_for(d)[0] for d in udates}
        self.lot_of = {d: (75 if self.expiry_of[d] <= date(2025, 12, 30) else 65) for d in udates}
        self.dte = np.array([(self.expiry_of[d] - d).days for d in self.dates])
        self.weekday = np.array([d.weekday() for d in self.dates])
        strikes = np.sort(near.strike.dropna().unique())
        self.strikes = strikes
        self.sidx = {float(k): i for i, k in enumerate(strikes)}
        grid = np.full((self.n, len(strikes), 2), np.nan)
        m_idx = self.pos.reindex(near.minute).to_numpy()
        ok = np.isfinite(m_idx) & near.strike.notna().to_numpy()
        si = near.strike.map(self.sidx).to_numpy()
        side = (near.side == "pe").to_numpy().astype(int)
        grid[m_idx[ok].astype(int), si[ok].astype(int), side[ok]] = near.close.to_numpy()[ok]
        self.grid = grid
        self.last_idx_of_date = pd.Series(np.arange(self.n), index=self.dates).groupby(level=0).max().to_dict()
        self.in_window = np.array([(time(10, 15) <= t <= time(14, 15)) for t in self.times])
        self.exit_time = np.array([t >= time(14, 57) for t in self.times])
        self.features = self._features()

    def _features(self) -> pd.DataFrame:
        """Own spot-based IV skew (as the strategy module computes it) plus the raw 800-rank."""
        spot = self.close
        expiry = [self.expiry_of[d] for d in self.dates]
        tyrs = years_to_expiry(self.clock, expiry)
        atm = s3.atm_strike(spot)

        def price(strike, side):
            out = np.full(self.n, np.nan)
            for i in range(self.n):
                j = self.sidx.get(float(strike[i]))
                if j is not None:
                    out[i] = self.grid[i, j, side]
            return out

        up = atm + s3.WING_STEPS * STEP
        down = atm - s3.WING_STEPS * STEP
        iv_pe = implied_vol(price(down, 1), spot, down, tyrs, False, rate=s3.RISK_FREE_RATE)
        iv_ce = implied_vol(price(up, 0), spot, up, tyrs, True, rate=s3.RISK_FREE_RATE)
        iv_atm = implied_vol(price(atm, 0), spot, atm, tyrs, True, rate=s3.RISK_FREE_RATE)
        f = pd.DataFrame({"skew": iv_pe - iv_ce, "iv_atm_ce": iv_atm, "atm": atm}, index=self.clock)
        f["skew_smooth"] = session_smooth(f["skew"], self.dates, s3.SMOOTH_WINDOW)
        return f

    def price(self, i, strike, side):
        j = self.sidx.get(float(strike))
        return np.nan if j is None else self.grid[i, j, side]

    def atm(self, x):
        return float(s3.atm_strike(x))


def session_smooth(series: pd.Series, dates, window: int) -> pd.Series:
    return series.groupby(np.asarray(dates)).transform(lambda x: x.rolling(window, min_periods=window).mean())


def rank800(series: pd.Series) -> pd.Series:
    return series.rolling(s3.RANK_WINDOW, min_periods=s3.RANK_MIN_PERIODS).rank(pct=True)


def gate_signal(skew, alpha, call_max=s3.SKEW_CALL_MAX, put_min=s3.SKEW_PUT_MIN, lo=s3.BEARISH_RANK, hi=s3.BULLISH_RANK):
    """-1 = credit call spread, +1 = credit put spread, 0 = nothing."""
    return np.where((alpha < lo) & (skew <= call_max), -1, np.where((alpha > hi) & (skew >= put_min), 1, 0))


def persist(sig, dates, n: int):
    """Keep a signal only after n consecutive identical nonzero signals within one session."""
    out = np.zeros(len(sig), dtype=int)
    run, prev, prev_d = 0, 0, None
    for i, (v, d) in enumerate(zip(sig, dates)):
        run = run + 1 if (v != 0 and v == prev and d == prev_d) else (1 if v != 0 else 0)
        prev, prev_d = v, d
        if v != 0 and run >= n:
            out[i] = v
    return out


# --------------------------------------------------------------------------- simulation
def simulate(mkt: Market, signal, start=START, end=END, target_frac=0.5, stop_points=45.0, max_dte=5, min_dte=1,
             weekend=False) -> pd.DataFrame:
    sig = np.asarray(signal)
    if not weekend:
        sig = np.where(mkt.weekday >= 5, 0, sig)
    start_i = int(mkt.pos[mkt.clock >= start].iloc[0])
    end_i = int(mkt.pos[mkt.clock <= end].iloc[-1])
    trades, pos = [], None
    for i in range(start_i, mkt.n):
        d = mkt.dates[i]
        if pos is not None:
            side = pos["side"]
            sv = mkt.price(i, pos["sell"], side) - mkt.price(i, pos["buy"], side)
            reason = None
            if d > pos["expiry"]:
                spot = mkt.close[mkt.last_idx_of_date[pos["expiry"]]]
                sv = (max(spot - pos["sell"], 0) - max(spot - pos["buy"], 0)) if side == 0 else (max(pos["sell"] - spot, 0) - max(pos["buy"] - spot, 0))
                reason = "expiry"
            elif np.isfinite(sv):
                if sv >= pos["stop"]:
                    reason = "stop"
                elif sv <= pos["target"]:
                    reason = "target"
                elif d == pos["expiry"] and mkt.exit_time[i]:
                    reason = "time"
            if reason:
                trades.append({**pos, "exit": mkt.clock[i], "exit_value": sv, "pnl": (pos["credit"] - sv) * pos["units"], "reason": reason})
                pos = None
            continue
        if i > end_i or sig[i] == 0 or not mkt.in_window[i] or not (min_dte <= mkt.dte[i] <= max_dte):
            continue
        side = 1 if sig[i] > 0 else 0
        atm = mkt.atm(mkt.open[i])
        sell, buy = atm, (atm - WIDTH if side == 1 else atm + WIDTH)
        ps, pb = mkt.price(i, sell, side), mkt.price(i, buy, side)
        if not (np.isfinite(ps) and np.isfinite(pb)) or ps - pb <= 0:
            continue
        credit = round(ps - pb, 2)
        lot = mkt.lot_of[d]
        alloc = CAPITAL * (0.8 if (mkt.weekday[i] == 0 and d >= date(2026, 4, 6)) else 1.0)
        lots = int(alloc // (2.25 * WIDTH * lot))
        pos = {"entry": mkt.clock[i], "side": side, "sell": sell, "buy": buy, "expiry": mkt.expiry_of[d], "credit": credit,
               "units": lots * lot, "lots": lots, "target": round(credit * (1 - target_frac), 2), "stop": round(credit + stop_points, 2)}
    if pos is not None:
        trades.append({**pos, "exit": None, "exit_value": np.nan, "pnl": np.nan, "reason": "open"})
    return pd.DataFrame(trades)


def score(trades: pd.DataFrame, published: pd.DataFrame, label="") -> dict:
    t = trades[trades.reason != "open"] if len(trades) else trades
    matched = same = 0
    for r in published.itertuples():
        s = 0 if r.side == "CE" else 1
        day = t[(t.entry.dt.date == r.entry.date()) & (t.side == s)] if len(t) else t
        if len(day):
            matched += 1
            same += int(day.sell.iloc[0] == r.sell)
    pnl = t.pnl.to_numpy() if len(t) else np.array([])
    cum = np.cumsum(pnl) if len(pnl) else np.array([0.0])
    dd = float((cum - np.maximum.accumulate(cum)).min()) if len(pnl) else 0.0
    return dict(label=label, trades=len(t), wins=int((pnl > 0).sum()), win_pct=round(100 * (pnl > 0).mean(), 1) if len(pnl) else 0.0,
                pnl=round(float(pnl.sum()), 0), max_dd=round(-dd, 0), matched=matched, of=len(published), same_strike=same,
                extra=len(t) - matched, stops=int((t.reason == "stop").sum()) if len(t) else 0)


def published_in(start=START, end=END) -> pd.DataFrame:
    p = load_published()
    return p[(p.entry >= start) & (p.entry <= end)]


def load_market() -> Market:
    path = OUT / "market.pkl"
    if path.exists():
        return pickle.load(open(path, "rb"))
    OUT.mkdir(parents=True, exist_ok=True)
    mkt = Market()
    pickle.dump(mkt, open(path, "wb"), protocol=5)
    return mkt


def pinned_signal(mkt: Market):
    f = mkt.features
    return gate_signal(f["skew_smooth"], rank800(f["skew_smooth"]))


def main(argv=None):
    argv = argv or sys.argv[1:]
    command = argv[0] if argv else "baseline"
    pd.set_option("display.width", 250)
    pd.set_option("display.max_rows", 500)
    if command == "build":
        path = OUT / "market.pkl"
        if path.exists():
            path.unlink()
        mkt = load_market()
        print("minutes", mkt.n, "strikes", len(mkt.strikes), "->", path)
        return
    mkt = load_market()
    pub = published_in()
    if command == "baseline":
        tr = simulate(mkt, pinned_signal(mkt))
        print(score(tr, pub, "pinned rule"))
        print(tr[["entry", "side", "sell", "credit", "exit", "exit_value", "pnl", "reason"]].to_string())
        return
    if command == "grid":
        f = mkt.features
        rows = []
        smooths = {w: (f["skew"] if w == 1 else session_smooth(f["skew"], mkt.dates, w)) for w in (1, 5, 15, 30)}
        ranks = {w: rank800(s) for w, s in smooths.items()}
        for w, cm, pm, n, lo in itertools.product((1, 5, 15, 30), (-2.0, -2.5, -3.0, -3.5), (4.0, 4.5, 5.0), (1, 5, 10, 20), (0.2, 0.1)):
            sig = gate_signal(smooths[w], ranks[w], call_max=cm, put_min=pm, lo=lo, hi=1 - lo)
            if n > 1:
                sig = persist(sig, mkt.dates, n)
            rows.append(dict(w=w, cm=cm, pm=pm, n=n, lo=lo, **score(simulate(mkt, sig), pub)))
        R = pd.DataFrame(rows).drop(columns=["label"])
        R["pub_like"] = R.matched - 0.5 * R.extra - R.stops
        R.to_csv(OUT / "grid.csv", index=False)
        print(R.sort_values(["pub_like", "pnl"], ascending=False).head(30).to_string())
        return
    raise SystemExit(f"unknown command {command}; use build, baseline or grid")


if __name__ == "__main__":
    main()
