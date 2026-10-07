"""Minute-close replay using Dhan's rolling series reassembled as fixed contracts.

Run from zen_credit: python -m backtest.dhan_replay --start 2024-01-01 --end 2025-01-01
End is inclusive for entries. Warm-up is outside the ledger; exits can use a seven-day tail.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
import json
import io
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

import numpy as np
import pandas as pd

from backtest.dhan_history import DhanHistoryClient, chunks, download, option_payload, spot_payload
from backtest.engine import Backtester
from backtest.metrics import compute_metrics,compute_period_performance
from backtest.nifty_2024 import Nifty2024Calendar, SOURCES, expiries_for, lot_size
from backtest import nifty_2026
from backtest.nse_settlement import NSESettlementClient
from config import REPO_ROOT, StrategyConfig
from data.providers.base import OptionChainSnapshot, OptionQuote
from strategy.alpha import calculate_alpha, observed_price_change
from strategy.alpha2 import calculate_alpha2
from strategy import registry
from utils.time import IST


def parse_series(raw, start, end, calendar):
    """Filter inclusive API overrun and out-of-session rows; no forward filling."""
    if not raw or not raw.get("timestamp"):
        return pd.DataFrame()
    count = len(raw["timestamp"])
    # Dhan includes empty arrays for fields absent from requiredData.
    if any(len(v) not in (0, count) for k, v in raw.items() if isinstance(v, list)):
        raise ValueError("Historical response arrays have different lengths")
    frame = pd.DataFrame({k: v for k, v in raw.items() if isinstance(v, list) and len(v) == count})
    frame.index = pd.to_datetime(frame.pop("timestamp"), unit="s", utc=True).dt.tz_convert(IST)
    mask = ((frame.index.date >= start) & (frame.index.date < end) &
            (frame.index.time >= time(9, 15)) & (frame.index.time < time(15, 30)))
    frame = frame.loc[mask]
    valid_days = {d for d in set(frame.index.date) if calendar.is_trading_day(d)}
    return frame.loc[np.isin(frame.index.date, list(valid_days))].sort_index()


def write_replay_performance(output,trades,capital,start,end):
    """Period-based returns for ordinary replays, keeping modeled fees explicit."""
    frame=trades.copy()
    if 'exit_ts' in frame:frame['exit_ts']=pd.to_datetime(frame.exit_ts,utc=True)
    gross=compute_period_performance(frame,capital,start,end)
    payload={'gross_realized':gross,'after_modeled_order_fees':None,
        'limitations':'Realized statistics exclude open MTM. Modeled fees are not a full tax, brokerage or funding estimate. Any configured slippage is already in replay fills.'}
    monthly=pd.DataFrame(gross['monthly'])
    if 'pnl_after_modeled_fees' in frame:
        net=compute_period_performance(frame,capital,start,end,pnl_col='pnl_after_modeled_fees')
        net['basis']='realized P&L after modeled order fees; configured slippage already in fills'
        payload['after_modeled_order_fees']=net
        monthly=monthly.merge(pd.DataFrame(net['monthly'])[['month','pnl','return_pct']].rename(
            columns={'pnl':'pnl_after_modeled_fees','return_pct':'return_pct_after_modeled_fees'}),on='month',validate='one_to_one')
    (output/'performance.json').write_text(json.dumps(payload,indent=2,allow_nan=False,default=str))
    monthly.to_csv(output/'performance_monthly.csv',index=False)
    return payload


def load_history(client, start, end, progress=print, calendar=None, expiry_resolver=expiries_for,
                 option_offsets=((1, range(-10, 11)), (2, range(-3, 4)))):
    calendar = calendar or Nifty2024Calendar()
    spots, options = [], []
    for first, last in chunks(start, end):
        progress(f"Loading cached chunk {first}", flush=True)
        raw = client.request("intraday", spot_payload(first, last))
        spots.append(parse_series(raw, first, last, calendar))
        expiry_map = {d: expiry_resolver(d) for d in set(spots[-1].index.date)}
        for code, offsets in option_offsets:
            for offset in offsets:
                for side, label in (("CALL", "ce"), ("PUT", "pe")):
                    payload = client.request("rollingoption", option_payload(first, last, code, offset, side))
                    frame = parse_series(payload["data"].get(label), first, last, calendar)
                    if frame.empty:
                        continue
                    frame["minute"] = frame.index + pd.Timedelta(minutes=1)
                    for day in set(frame.index.date).difference(expiry_map):
                        expiry_map[day] = expiry_resolver(day)
                    frame["expiry"] = [expiry_map[d][code - 1] for d in frame.index.date]
                    frame["side"] = label
                    frame["expiry_code"] = code
                    frame["offset"] = offset
                    options.append(frame[["minute", "expiry", "strike", "side", "close", "volume", "expiry_code", "offset"]])
    bars = pd.concat(spots).sort_index()
    if bars.index.duplicated().any():
        raise ValueError("Duplicate historical index bars")
    bars = bars[["open", "high", "low", "close", "volume"]].apply(pd.to_numeric)
    if not np.isfinite(bars[["open", "high", "low", "close"]]).all().all():
        raise ValueError("Invalid index OHLC; refusing to compress missing prices")
    if not options:
        raise ValueError("No expired-option data returned")
    long = pd.concat(options, ignore_index=True)
    keys = ["minute", "expiry", "strike", "side"]
    duplicates = long.duplicated(keys, keep=False)
    conflicts = pd.DataFrame(columns=long.columns)
    if duplicates.any():
        counts = long.loc[duplicates].groupby(keys)[["close", "volume"]].nunique()
        bad_keys = counts.index[(counts > 1).any(axis=1)]
        if len(bad_keys):
            invalid = pd.MultiIndex.from_frame(long[keys]).isin(bad_keys)
            conflicts = long.loc[invalid].copy()
            long = long.loc[~invalid]
            progress(f"Excluded {len(bad_keys)} conflicting contract/side/minute quotes", flush=True)
    long = long.drop_duplicates(keys)
    wide = long.pivot(index=["minute", "expiry", "strike"], columns="side", values=["close", "volume"])
    wide.columns = [f"{side}_{'ltp' if field == 'close' else 'volume'}" for field, side in wide.columns]
    wide = wide.sort_index()
    return bars, wide, conflicts


def atm_panels(options, bars):
    """Use native candle volume and previous SAME strike close, never rolling-ATM returns."""
    data = options.reset_index()
    spot = bars["close"].copy()
    spot.index += pd.Timedelta(minutes=1)
    data["spot"] = data["minute"].map(spot)
    # Exact half-strike ties resolve down, as in nearest_strike().
    data["atm_strike"] = np.floor((data["spot"] + 25 - 1e-8) / 50) * 50
    selected = data.loc[data["strike"] == data["atm_strike"]].copy()
    previous_keys = pd.MultiIndex.from_arrays(
        [selected["minute"] - pd.Timedelta(minutes=1), selected["expiry"], selected["strike"]],
        names=options.index.names)
    previous = options.reindex(previous_keys)
    same_day = selected["minute"].dt.date.to_numpy() == (selected["minute"] - pd.Timedelta(minutes=1)).dt.date.to_numpy()
    # Decision 09:16 is the first session candle: no return across overnight.
    same_day &= selected["minute"].dt.time.to_numpy() != time(9, 16)
    for side in ("ce", "pe"):
        old = previous[f"{side}_ltp"].to_numpy()
        current = selected[f"{side}_ltp"].to_numpy()
        valid = same_day & np.isfinite(old) & (old > 0) & (current > 0)
        selected[f"{side}_return"] = np.divide(current, old, out=np.full(len(old), np.nan), where=valid) - 1
        # Live volume is valid even when an option is priced at zero. A missing
        # previous contract observation, however, cannot supply a volume delta.
        volume_valid = same_day & np.isfinite(previous[f"{side}_volume"].to_numpy())
        selected.loc[~volume_valid, f"{side}_volume"] = np.nan
    result = {}
    for expiry, group in selected.groupby("expiry"):
        panel = group.set_index("minute")[["spot", "atm_strike", "ce_volume", "pe_volume", "ce_return", "pe_return"]]
        days = []
        for _, day in panel.groupby(panel.index.date):
            days.append(day.reindex(pd.date_range(day.index.min(), day.index.max(), freq="1min")))
        result[expiry] = pd.concat(days).sort_index()
    return result


def supplement_fixed_contracts(client, bars, options, end, calendar, expiry_resolver, lot_resolver):
    """Prefer actual security-ID candles for contracts present in a dated master.

    Persist that master so offline replays keep the same source after expiry.
    Expired contracts absent from the master retain their rolling archive.
    """
    today = datetime.now(IST).date()
    needed = {expiry_resolver(d)[0] for d in set(bars.index.date)}
    master_path = client.cache_dir / f"dhan_nifty_contracts_{end}.csv"
    if not master_path.exists():
        if not any(e >= today for e in needed):
            return options, {"fixed_contracts": 0, "fixed_quote_pairs": 0}
        if client.offline:
            raise RuntimeError("Missing dated instrument master for active-contract replay")
        url = "https://images.dhan.co/api-data/api-scrip-master-detailed.csv"
        response = client.session.get(url, timeout=60)
        if response.status_code != 200:
            raise RuntimeError("Dhan public instrument master unavailable")
        master = pd.read_csv(io.StringIO(response.text), low_memory=False)
        master = master.loc[master.EXCH_ID.eq("NSE") & master.INSTRUMENT.eq("OPTIDX") & master.UNDERLYING_SYMBOL.eq("NIFTY")]
        master.to_csv(master_path, index=False)
    master = pd.read_csv(master_path)
    master["expiry"] = pd.to_datetime(master.SM_EXPIRY_DATE).dt.date
    available = needed.intersection(set(master.expiry))
    jobs = []
    ranges = {}
    for expiry in sorted(available):
        days = [d for d in sorted(set(bars.index.date)) if expiry in expiry_resolver(d)]
        if not days:
            continue
        first = min(days)
        relevant = bars.loc[np.isin(bars.index.date, days), "close"]
        low = np.floor((relevant.min() - 25) / 50) * 50 - 400
        high = np.ceil((relevant.max() + 25) / 50) * 50 + 400
        contracts = master.loc[master.expiry.eq(expiry) & master.STRIKE_PRICE.between(low, high)]
        if contracts.duplicated(["expiry", "STRIKE_PRICE", "OPTION_TYPE"]).any():
            raise ValueError("Instrument master contains duplicate option contracts")
        ranges[expiry] = first
        for _, row in contracts.iterrows():
            if int(row.LOT_SIZE) != lot_resolver(first, expiry):
                raise ValueError("Instrument master and sourced historical lot size disagree")
            payload = {"securityId": str(row.SECURITY_ID), "exchangeSegment": "NSE_FNO", "instrument": "OPTIDX",
                       "interval": "1", "oi": False, "fromDate": f"{first} 00:00:00", "toDate": f"{end} 00:00:00"}
            jobs.append((expiry, float(row.STRIKE_PRICE), row.OPTION_TYPE.lower(), first, payload))
    print(f"Loading {len(jobs)} fixed-contract histories for active expiries {sorted(available)}...", flush=True)
    def fetch(job):
        expiry, strike, side, first, payload = job
        worker = DhanHistoryClient(client.cache_dir, offline=client.offline)
        frame = parse_series(worker.request("intraday", payload), first, end, calendar)
        if frame.empty:
            raise ValueError(f"No fixed-contract candles for {expiry} {strike} {side}")
        frame["minute"] = frame.index + pd.Timedelta(minutes=1)
        frame["expiry"], frame["strike"], frame["side"] = expiry, strike, side
        return frame[["minute", "expiry", "strike", "side", "close", "volume"]]
    frames = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(fetch, job) for job in jobs]
        for i, future in enumerate(as_completed(futures), 1):
            frames.append(future.result())
            if i % 10 == 0 or i == len(jobs):
                print(f"  fixed-contract histories: {i}/{len(jobs)}", flush=True)
    if not frames:
        return options, {"fixed_contracts": 0, "fixed_quote_pairs": 0}
    long = pd.concat(frames, ignore_index=True)
    if long.duplicated(["minute", "expiry", "strike", "side"]).any():
        raise ValueError("Duplicate fixed-contract candles")
    fixed = long.pivot(index=["minute", "expiry", "strike"], columns="side", values=["close", "volume"])
    fixed.columns = [f"{side}_{'ltp' if field == 'close' else 'volume'}" for field, side in fixed.columns]
    keep = ~options.index.get_level_values("expiry").isin(available)
    # Missing security-ID candles stay missing; do not back-fill from the other feed.
    combined = pd.concat([options.loc[keep], fixed]).sort_index()
    return combined, {"fixed_contracts": len(jobs), "fixed_quote_pairs": len(fixed),
                      "fixed_expiries": sorted(available), "instrument_master": str(master_path),
                      "source": "https://dhanhq.co/docs/v2/historical-data/"}


@dataclass(frozen=True, eq=False)
class PreparedOptionQuotes:
    """Chunk-local market data shared by otherwise independent replay engines.

    The quote mapping and its numeric buffers are immutable. The source frame
    identifies the chunk and must remain unchanged while engines consume it.
    """
    source_options: pd.DataFrame
    options: pd.DataFrame
    quote_index: Mapping


@dataclass(frozen=True, eq=False)
class ReplayQuoteMapping(Mapping):
    """Read-only chain view; create quotes only when the engine asks for them.

    Numeric buffers belong to the immutable prepared chunk. Iteration includes
    every valid side and the missing ATM placeholders, just like the eager
    chain. Duplicate records retain the last valid price for each side.
    """
    strikes: np.ndarray
    prices: np.ndarray
    references: frozenset
    slippage: float

    def __getitem__(self, key):
        strike, side = key
        if side not in ('CE', 'PE'):
            raise KeyError(key)
        strike = float(strike)
        column = 0 if side == 'CE' else 1
        left = int(np.searchsorted(self.strikes, strike, side='left'))
        right = int(np.searchsorted(self.strikes, strike, side='right'))
        for row in range(right - 1, left - 1, -1):
            price = float(self.prices[row, column])
            if np.isfinite(price) and price >= 0:
                return OptionQuote(strike, side, price, max(0, price - self.slippage),
                                   price + self.slippage, None)
        if strike in self.references:
            return OptionQuote(strike, side, None, None, None, None)
        raise KeyError(key)

    def __iter__(self):
        seen = set()
        for strike, prices in zip(self.strikes, self.prices):
            for side, price in zip(('CE', 'PE'), prices):
                key = (float(strike), side)
                if np.isfinite(price) and price >= 0 and key not in seen:
                    seen.add(key)
                    yield key
        for strike in self.references:
            for side in ('CE', 'PE'):
                key = (strike, side)
                if key not in seen:
                    yield key

    def __len__(self):
        return sum(1 for _ in self)


def prepare_option_quotes(options):
    """Sort and index one chunk once; never retain data across chunk boundaries."""
    ordered = options.sort_index()
    minutes = ordered.index.get_level_values("minute")
    expiries = ordered.index.get_level_values("expiry")
    # Bytes-backed arrays cannot be made writable by a consumer. Each engine
    # constructs its own mutable OptionChainSnapshot from these numeric slices.
    strikes = np.frombuffer(ordered.index.get_level_values("strike").to_numpy(dtype=float).tobytes(), dtype=float)
    prices = np.frombuffer(ordered[["ce_ltp", "pe_ltp"]].to_numpy(dtype=float).tobytes(), dtype=float).reshape(-1, 2)
    boundaries = np.r_[0, np.flatnonzero((minutes[1:] != minutes[:-1]) | (expiries[1:] != expiries[:-1])) + 1, len(ordered)]
    quotes = {(minutes[first], expiries[first]): (strikes[first:last], prices[first:last])
              for first, last in zip(boundaries[:-1], boundaries[1:]) if first < last}
    return PreparedOptionQuotes(options, ordered, MappingProxyType(quotes))


class DhanReplay(Backtester):
    def __init__(self, cfg, bars, options, slippage_points=0, settlement_loader=None,
                 calendar=None, expiry_resolver=expiries_for, lot_resolver=lot_size,
                 prepared_quotes=None, strategy_name="description"):
        cfg = registry.apply_profile(strategy_name, cfg)
        self.strategy_name = strategy_name
        super().__init__(cfg, calendar or Nifty2024Calendar(), bars, expiry_resolver,
                         lambda d: lot_resolver(d, expiry_resolver(d)[0]))
        self.lot_resolver = lot_resolver
        if prepared_quotes is None:
            prepared_quotes = prepare_option_quotes(options)
        elif not isinstance(prepared_quotes, PreparedOptionQuotes) or prepared_quotes.source_options is not options:
            raise ValueError("Prepared option quotes belong to a different historical chunk")
        self.options = prepared_quotes.options
        self.slippage_points = slippage_points
        self.engine = registry.create_engine(strategy_name, cfg, self.calendar,
            entry_price_source="bidask", max_data_age_seconds=None, require_quotes=True)
        self.reasons = Counter()
        self.coverage_events = []
        self.decisions = []
        self._last_decision = None
        self.settlement_loader = settlement_loader
        self.trade_details = {}
        self.quote_index = prepared_quotes.quote_index

    def _lot_size_at(self, day, expiry):
        return self.lot_resolver(day, expiry)

    def _settlement_at(self, now, expiry):
        # Final closing value is not available before the expiry session ends.
        if self.settlement_loader is not None and now.date() > expiry:
            return self.settlement_loader(expiry)
        return None

    def _indicator_frame(self):
        module = registry.get_strategy(self.strategy_name)
        if module is not None:
            panel = module.panel_from_options(self.bars, self.options, self.expiries_for)
            self.indicators = module.calculate_indicators(self.bars, panel)
            return self.indicators
        print("Calculating causal alpha and expiry-specific alpha2...", flush=True)
        alpha = calculate_alpha(self.bars, self.cfg.alpha_lookback_minutes, self.cfg.price_change_horizon_minutes)
        alpha.index += pd.Timedelta(minutes=1)
        pc = observed_price_change(self.bars, self.cfg.price_change_horizon_minutes)
        pc.index += pd.Timedelta(minutes=1)
        per_expiry = {e: calculate_alpha2(pc, panel, self.cfg.alpha2_lookback_minutes,
                                         self.cfg.volume_short_window, self.cfg.volume_baseline_window,
                                         self.cfg.volatility_window, return_components=True,
                                         factor_lag_bars=self.cfg.alpha2_factor_lag_bars)[1]
                      for e, panel in atm_panels(self.options, self.bars).items()}
        mapping = {d: self.expiries_for(d)[0] for d in set(alpha.index.date)}
        self.indicators = pd.DataFrame({"alpha": alpha})
        nearest = pd.Series([mapping[m.date()] for m in alpha.index], index=alpha.index)
        columns = ["price_change", "volume_ratio", "atm_volatility", "raw", "alpha2"]
        self.indicators[columns] = np.nan
        for expiry, parts in per_expiry.items():
            mask = nearest.eq(expiry)
            self.indicators.loc[mask, columns] = parts.reindex(alpha.index[mask])[columns].to_numpy()
        return self.indicators

    def _chain_at(self, ts, expiry, spot):
        chain = OptionChainSnapshot("NIFTY", expiry, ts, spot)
        strikes, prices = self.quote_index.get((pd.Timestamp(ts), expiry), ([], []))
        # Prevent a missing ATM candle from silently moving the short strike.
        atm = float(np.floor((spot + 25 - 1e-8) / 50) * 50)
        references={atm}
        if self.cfg.strike_reference == "last_bar_open":
            bar_start=pd.Timestamp(ts)-pd.Timedelta(minutes=1)
            entry_atm=float(np.floor((self.bars.loc[bar_start,"open"]+25-1e-8)/50)*50)
            references.add(entry_atm)
        chain.quotes = ReplayQuoteMapping(strikes, prices, frozenset(references), self.slippage_points)
        return chain

    def _observe(self, view, position, result):
        if self._last_decision is None or self._last_decision.month != view.now.month:
            print(f"Replaying {view.now:%Y-%m}: evaluations={len(self.decisions):,}; missing held quotes={len(self.coverage_events):,}", flush=True)
        self.reasons[result.reason] += 1
        row = {"minute": view.now.isoformat(), "action": result.action, "reason": result.reason,
               "alpha": float(view.indicators[0]), "alpha2": float(view.indicators[1]),
               "spread_value": result.exit.exit_value if result.action == "exit" else result.diagnostics.get("spread_value"),
               "entry_ts": position.entry_ts.isoformat() if position else None}
        self.decisions.append(row)
        if result.action == "entry":
            p = result.position
            self.trade_details[p.entry_ts] = {"sell_leg_entry": p.sell_price, "buy_leg_entry": p.buy_price,
                                             "scheduled_exit": p.exit_due}
        elif result.action == "exit" and position is not None:
            details = self.trade_details[position.entry_ts]
            details["spot_at_exit"] = view.chain.spot
            details["exit_observed_ts"] = result.exit.exit_ts
            if result.exit.reason == "Expiry" and view.settlement is not None:
                details["settlement_spot"] = view.settlement.spot
                details["settlement_source"] = view.settlement.source
                details["effective_exit_ts"] = datetime.combine(position.expiry, time(15,30), IST)
            else:
                details["sell_leg_exit"] = self.engine._leg_price(view.chain, position.sell_strike, position.option_type, "BUY")
                details["buy_leg_exit"] = self.engine._leg_price(view.chain, position.buy_strike, position.option_type, "SELL")
        if position is not None:
            first = datetime.combine(view.now.date(), time(9, 16), IST)
            previous = self._last_decision if self._last_decision and self._last_decision.date() == view.now.date() else first - timedelta(minutes=1)
            if (view.now - previous).total_seconds() > 60:
                for minute in pd.date_range(previous + timedelta(minutes=1), view.now - timedelta(minutes=1), freq="1min"):
                    self.coverage_events.append({**row, "minute": minute.isoformat(), "reason": "missing index decision candle",
                                                 "expiry": position.expiry.isoformat(), "sell_strike": position.sell_strike,
                                                 "buy_strike": position.buy_strike, "option_type": position.option_type,
                                                 "exit_due": position.exit_due.isoformat()})
        self._last_decision = view.now
        if position is not None and row["spread_value"] is None:
            self.coverage_events.append({**row, "expiry": position.expiry.isoformat(),
                                         "sell_strike": position.sell_strike, "buy_strike": position.buy_strike,
                                         "option_type": position.option_type, "exit_due": position.exit_due.isoformat()})


def mark_open_trades(trades, replay, asof):
    """Value open original contracts at the final decision; never fabricate an exit."""
    trades["valuation_ts"] = None
    trades["mark_spread_value"] = np.nan
    trades["unrealized_pnl"] = np.nan
    if trades.empty or asof is None:
        return
    bar_start = pd.Timestamp(asof) - pd.Timedelta(minutes=1)
    spot = replay.bars.loc[bar_start, "close"]
    for i, t in trades.loc[trades["exit_ts"].isna()].iterrows():
        chain = replay._chain_at(asof, t["expiry"], spot)
        short = replay.engine._leg_price(chain, t["sell_strike"], t["option_type"], "BUY")
        hedge = replay.engine._leg_price(chain, t["buy_strike"], t["option_type"], "SELL")
        if short is not None and hedge is not None:
            spread = short - hedge
            trades.at[i, "valuation_ts"] = asof
            trades.at[i, "mark_spread_value"] = spread
            trades.at[i, "unrealized_pnl"] = (t["net_credit"] - spread) * t["units"]


def run_cli():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=date.fromisoformat, default=date(2024, 1, 1))
    parser.add_argument("--end", type=date.fromisoformat, default=date(2025, 1, 1), help="inclusive entry date")
    parser.add_argument("--offline", action="store_true", help="use cache without any network requests")
    parser.add_argument("--strategy", choices=registry.strategy_names(), default="description",
                        help="named strategy; strategy_01 is the first selected profit trial")
    parser.add_argument("--provider-history-rules", action="store_true",
                        help="use the observed 2025/2026 calendar and dated 15:00 to 14:53 exit schedule")
    parser.add_argument("--slippage-points", type=float, default=0.0, help="assumed adverse points per leg execution")
    parser.add_argument("--fee-per-leg", type=float, default=0.0, help="assumed rupees per leg order; not an all-tax estimate")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--exit-tail-days", type=int, default=7,
                        help="extra calendar days for exits; use 0 for P&L strictly through --end")
    args = parser.parse_args()
    if args.provider_history_rules:
        from backtest import provider_calendar
        if not date(2025,7,9) <= args.start <= args.end <= date(2026,10,1):
            parser.error("Provider history profile supports July 9 2025 through October 1 2026")
        calendar, expiry_resolver, lot_resolver, sources = (
            provider_calendar.ProviderCalendar(), provider_calendar.expiries_for,
            provider_calendar.lot_size, provider_calendar.SOURCES)
    elif date(2024, 1, 1) <= args.start <= args.end <= date(2025, 1, 1):
        calendar, expiry_resolver, lot_resolver, sources = Nifty2024Calendar(), expiries_for, lot_size, SOURCES
    elif date(2026, 1, 22) <= args.start <= args.end <= date(2026, 12, 10):
        calendar, expiry_resolver, lot_resolver, sources = (
            nifty_2026.Nifty2026Calendar(), nifty_2026.expiries_for, nifty_2026.lot_size, nifty_2026.SOURCES)
    else:
        parser.error("Supported entry ranges: Jan 1 2024–Jan 1 2025, or Jan 22–Dec 10 2026")
    today = datetime.now(IST).date()
    if args.end >= today:
        parser.error("End must be a completed date before today in Asia/Kolkata")
    if args.slippage_points < 0 or args.fee_per_leg < 0 or args.exit_tail_days < 0:
        parser.error("Cost assumptions must be nonnegative")
    start = args.start - timedelta(days=21)
    stop = min(args.end + timedelta(days=args.exit_tail_days + 1), today)
    output = args.output or REPO_ROOT / "reports" / f"dhan_{args.start}_{args.end}"
    output.mkdir(parents=True, exist_ok=True)
    client = DhanHistoryClient(offline=args.offline)
    download(client, start, stop)
    bars, options, conflicts = load_history(client, start, stop, calendar=calendar, expiry_resolver=expiry_resolver)
    options, fixed_audit = supplement_fixed_contracts(client, bars, options, stop, calendar, expiry_resolver, lot_resolver)
    conflicts.to_csv(output / "conflicting_option_records.csv", index=False)
    print(f"Loaded {len(bars):,} index candles and {len(options):,} fixed-contract quote pairs", flush=True)
    cfg = StrategyConfig()  # supplied-description defaults, no live-account overrides
    if args.provider_history_rules:
        cfg = provider_calendar.history_config(cfg)
    cfg = registry.apply_profile(args.strategy, cfg)
    settlements = NSESettlementClient(client.cache_dir, offline=args.offline)
    replay = DhanReplay(cfg, bars, options, args.slippage_points, settlement_loader=settlements.get,
                        calendar=calendar, expiry_resolver=expiry_resolver, lot_resolver=lot_resolver,
                        strategy_name=args.strategy)
    result = replay.run(start=datetime.combine(args.start, time.min, IST),
                        entry_end=datetime.combine(args.end, time.max, IST))
    result.mode = "dhan-minute-close"
    trades = result.to_frame()
    if not trades.empty:
        for col in ("sell_leg_entry", "buy_leg_entry", "scheduled_exit", "sell_leg_exit", "buy_leg_exit",
                    "spot_at_exit", "exit_observed_ts", "settlement_spot", "settlement_source"):
            trades[col] = [replay.trade_details[t].get(col) for t in trades["entry_ts"]]
        trades["exit_ts"] = [replay.trade_details[t].get("effective_exit_ts", e)
                              for t,e in zip(trades["entry_ts"],trades["exit_ts"])]
        gaps = Counter(row["entry_ts"] for row in replay.coverage_events)
        trades["quote_gap_minutes"] = [gaps[t.isoformat()] for t in trades["entry_ts"]]
        trades["has_quote_gaps"] = trades["quote_gap_minutes"] > 0
        trades["exit_after_scheduled_exit"] = trades["exit_ts"] > trades["scheduled_exit"]
        trades["lot_size"] = trades["units"] // trades["lots"]
        trades["modeled_order_fees"] = np.where(trades["exit_ts"].notna() & trades["exit_reason"].ne("Expiry"), 4, 2) * args.fee_per_leg
        trades["pnl_after_modeled_fees"] = trades["pnl"] - trades["modeled_order_fees"]
    mark_open_trades(trades, replay, result.last_decision)
    trades.to_csv(output / "trades.csv", index=False)
    pd.DataFrame(replay.decisions).to_csv(output / "decisions.csv.gz", index=False, compression="gzip")
    pd.DataFrame(replay.coverage_events).to_csv(output / "missing_position_quotes.csv", index=False)
    replay.indicators.to_csv(output / "indicators.csv.gz", compression="gzip")
    closed = trades.loc[trades["exit_ts"].notna()] if not trades.empty else trades
    open_count = int(trades["exit_ts"].isna().sum()) if not trades.empty else 0
    expected_days = [d.date() for d in pd.date_range(args.start, args.end) if replay.calendar.is_trading_day(d.date())]
    observed_days = set(bars.index.date)
    missing_days = [str(d) for d in expected_days if d not in observed_days]
    missing_index_minutes = []
    for day in expected_days:
        expected = pd.date_range(datetime.combine(day, time(9, 15), IST), periods=375, freq="1min")
        missing_index_minutes.extend(expected.difference(bars.index).tolist())
    pd.DataFrame({"bar_start": missing_index_minutes}).to_csv(output / "missing_index_minutes.csv", index=False)
    missing_signal_minutes = sum(time(10, 14) <= m.time() <= time(14, 14) for m in missing_index_minutes)
    period_indicators = replay.indicators.loc[
        (replay.indicators.index.date >= args.start) & (replay.indicators.index.date <= args.end) &
        (replay.indicators.index.time >= time(10, 15)) & (replay.indicators.index.time <= time(14, 15))]
    missing_signal_indicators = int(period_indicators[["alpha", "alpha2"]].isna().any(axis=1).sum())
    unvalued_open = int((trades["exit_ts"].isna() & trades["unrealized_pnl"].isna()).sum()) if not trades.empty else 0
    coverage_ok = not replay.coverage_events and not unvalued_open and not missing_days and not missing_signal_minutes and not missing_signal_indicators
    unrealized = float(trades["unrealized_pnl"].sum()) if open_count and not unvalued_open else (None if unvalued_open else 0.0)
    metrics = compute_metrics(closed, cfg.capital, pnl_col="pnl_after_modeled_fees")
    performance=write_replay_performance(output,trades,cfg.capital,args.start,pd.Timestamp(result.last_decision).date())
    report = {"entry_start": str(args.start), "entry_end_inclusive": str(args.end),
              "download_start": str(start), "download_end_exclusive": str(stop), "config": asdict(cfg),
              "mode": result.mode, "strategy": args.strategy, "provider_history_rules": args.provider_history_rules,
              "coverage_complete_for_open_positions": coverage_ok,
              "missing_position_quote_minutes": len(replay.coverage_events), "open_positions_at_end": open_count,
              "missing_index_session_dates": missing_days, "index_candles": len(bars),
              "missing_index_regular_session_minutes": len(missing_index_minutes),
              "missing_index_signal_window_minutes": missing_signal_minutes,
              "missing_signal_indicator_minutes": missing_signal_indicators,
              "valuation_asof": result.last_decision,
              "unvalued_open_positions": unvalued_open, "unrealized_pnl_before_fees": unrealized,
              "total_pnl_including_open_before_costs": (
                  float(closed["pnl"].sum()) + unrealized if unrealized is not None and not trades.empty else unrealized),
              "initial_position": "flat; warm-up calculates indicators only",
              "requested_exit_tail_days": args.exit_tail_days,
              "option_quote_pairs": len(options), "decision_reasons": dict(replay.reasons),
              "fixed_contract_data": fixed_audit,
              "excluded_conflicting_option_records": len(conflicts),
              "trades_with_quote_gaps": int(trades["has_quote_gaps"].sum()) if not trades.empty else 0,
              "trades_exited_after_scheduled_exit": int(trades["exit_after_scheduled_exit"].sum()) if not trades.empty else 0,
              "closed_trade_metrics_provisional": metrics,"period_performance":performance,
              "slippage_points_per_leg": args.slippage_points,
              "fee_rupees_per_leg_order": args.fee_per_leg,
              "source_urls": sources + ["https://dhanhq.co/docs/v2/expired-options-data/",
                  "https://dhanhq.co/docs/v2/historical-data/",
                  "https://www.nseindia.com/static/products-services/equity-derivatives-settlement-price"],
              "limitations": ["Uses the supplied description with stated assumptions; the provider's exact implementation remains unverified.",
                  "Literal forward price change is delayed five observed bars; alpha2 uses volume/volatility factors from the starting bar of that change.",
                  "Volume ratio uses per-leg mean volume 5/300; volatility uses summed same-contract one-bar return standard deviations over 300 bars, calculated separately by expiry.",
                  "Alpha2 ranks a trailing 300-bar window with at least 270 valid values; volume/volatility baselines require 240 valid values. Missing data is not filled.",
                  "Exit and sizing assumptions: 5% normal-margin stop, net spread target 10, next-trading-day 14:53 exit capped at expiry, INR 320,000 capital, full allocation, estimated margin.",
                  "ATM uses current completed NIFTY close; no inferred short-premium cap or fitted entry conditions are applied.",
                  "Active contracts use security-ID historical candles; expired contracts use the rolling archive. These feeds can differ in minute prices/volumes.",
                  "For rolling data, expiry is inferred from the NSE calendar; active security IDs have dated instrument-master expiries.",
                  "API timestamps treated as candle starts; all values become usable one minute later.",
                  "Index alpha counts observed session candles; missing index minutes are not filled.",
                  "Minute-close execution and stops; bid/ask, intraminute crossing and exact fills unavailable.",
                  "Near-expiry strikes limited to ATM +/-10; absent original legs are never replaced or filled.",
                  "If quotes never return, official expiry-date NSE index close supplies cash settlement; missed scheduled exits remain data gaps.",
                  ("Provider calendar includes the February 1 2026 special session; evening Muhurat sessions excluded."
                   if args.provider_history_rules else "Regular weekday sessions only; special Saturday/Muhurat sessions excluded."),
                  "Margin is a reconstruction assumption, not historical broker margin.",
                  "Fees/taxes excluded unless modeled explicitly; fees parameter is not a full tax calculation.",
                  "Drawdown uses realized closed trades, not intratrade equity."]}
    if args.strategy != "description":
        selected_strategy = registry.get_strategy(args.strategy)
        report["profit_target_enabled"] = getattr(selected_strategy, "PROFIT_TARGET_ENABLED", True)
        report["limitations"] = [
            f"Selected named research candidate {args.strategy}: {selected_strategy.DESCRIPTION}. Not a verified Zen Credit replica.",
            "Completed index close versus open five observed bars earlier; 800-value alpha rank.",
            "Opening ATM near-expiry path; geometric current/10-bar native volume ratios; volatility definition is pinned by the named module; factors lag five bars; alpha2 rank 300 with 270 valid observations.",
            "Missing option candles remain unknown and can postpone exits or suppress entries.",
            "Minute-close execution; bid/ask spreads and intraminute fills unavailable. Costs only include explicit configured assumptions.",
            "Estimated margin and expiry multiplier do not reconstruct actual broker margin or forced liquidation.",
            "Statistics use realized closed trades and fixed capital; open MTM is separate; CAGR is an annualized ending-value calculation.",
            "See the named strategy file for all pinned execution rules and dated historical exit assumptions."]
    (output / "report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    title = "Provisional replay — incomplete position price coverage" if not coverage_ok else "Historical minute-close replay"
    summary = f"# {title}\n\nEntries: {args.start} through {args.end}, inclusive. Capital: INR {cfg.capital:,.0f}.\n\n"
    summary += f"Closed trades: {len(closed)}. Open at end: {open_count}. Missing held-leg quote minutes: {len(replay.coverage_events)}.\n\n"
    summary += f"Trades with quote gaps: {report['trades_with_quote_gaps']}. Trades exited after their scheduled deadline: {report['trades_exited_after_scheduled_exit']}.\n\n"
    summary += f"Closed-trade P&L after modeled fees: INR {metrics.get('total_pnl', 0):,.2f}. "
    summary += f"Win rate: {metrics.get('win_rate_pct', 0)}%. Realized drawdown: {metrics.get('max_drawdown_pct', 0)}%.\n\n"
    summary += f"Unrealized P&L before fees: {('INR ' + format(unrealized, ',.2f')) if unrealized is not None else 'unavailable: missing final quotes'}. Valuation: {result.last_decision}.\n\n"
    total_mark=report['total_pnl_including_open_before_costs']
    summary += f"Combined realized plus unrealized P&L before costs: {('INR ' + format(total_mark, ',.2f')) if total_mark is not None else 'unavailable'}.\n\n"
    summary += f"Missing signal indicators during the requested entry window: {missing_signal_indicators} minutes. Starts flat; warm-up does not carry prior trades into this period.\n\n"
    if not coverage_ok:
        summary += "These closed-trade figures are incomplete and cannot establish the strategy's full-period performance. Missing quotes can delay exits and suppress later entries. See missing_position_quotes.csv and report.json.\n\n"
    summary += "## Trade ledger (Asia/Kolkata; P&L before fees)\n\n"
    if trades.empty:
        summary += "No trades were generated. Check indicator and market-data coverage above.\n\n"
    else:
        summary += "| Entry | Exit | Spread: sell / buy | Expiry | Lots / units | Entry credit | P&L (INR) | Exit reason |\n"
        summary += "|---|---|---|---|---|---|---|---|\n"
        for _, t in trades.iterrows():
            is_open = pd.isna(t["exit_ts"])
            exit_text = "Open at period end" if is_open else t["exit_ts"].strftime("%d %b %H:%M")
            pnl = t["unrealized_pnl"] if is_open else t["pnl"]
            pnl_text = "Unavailable" if pd.isna(pnl) else f"{pnl:+,.2f}" + (" (unrealized)" if is_open else "")
            summary += (f"| {t['entry_ts']:%d %b %H:%M} | {exit_text} | {t['sell_strike']:.0f}{t['option_type']} / "
                        f"{t['buy_strike']:.0f}{t['option_type']} | {t['expiry']} | {t['lots']} / {t['units']} | "
                        f"{t['net_credit']:.2f} | {pnl_text} | {t['exit_reason']} |\n")
        summary += "\n"
        summary += "## Entry indicators\n\n| Entry | alpha | alpha2 | Direction |\n|---|---:|---:|---|\n"
        for _, t in trades.iterrows():
            summary += f"| {t['entry_ts']:%d %b %H:%M} | {t['alpha']:.6f} | {t['alpha2']:.6f} | {t['direction']} |\n"
        summary += "\n"
    summary += "## Assumptions and limits\n\n" + "\n".join("- " + x for x in report["limitations"]) + "\n"
    (output / "summary.md").write_text(summary, encoding="utf-8")
    print(summary, flush=True)
    print(f"Saved outputs: {output}", flush=True)


if __name__ == "__main__":
    run_cli()
