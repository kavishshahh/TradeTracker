"""Event-driven backtester.

Walks the 1-minute bar stream in time order. At each decision time (= the end
of a completed bar) it builds the same :class:`MarketView` the live service
builds and calls the same :class:`StrategyEngine`. Indicators are precomputed
with the causal functions (verified equal to incremental computation by
tests/unit/test_leakage.py) purely for speed.

Two data modes:
* full     : option snapshots available (e.g. recorded by the live service) -> real
             entry prices, stop loss / target monitoring and P&L.
* spot-only: no historical option data (the free-data situation for the provider
             period). Entries/directions/strikes/expiries and time exits are
             simulated; prices, SL/target exits and P&L are NOT available.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Callable

import numpy as np
import pandas as pd

from data.market_calendar import TradingCalendar
from config import StrategyConfig
from data.providers.base import OptionChainSnapshot, OptionQuote
from strategy.alpha import calculate_alpha, observed_price_change
from strategy.alpha2 import build_atm_panel, calculate_alpha2
from strategy.engine import MarketView, Position, StrategyEngine


def scale_config(cfg: StrategyConfig, bar_minutes: int) -> StrategyConfig:
    """Express minute-based windows in bars (diagnostic runs on 5-minute bars)."""
    if bar_minutes == 1:
        return cfg
    return dataclasses.replace(
        cfg,
        alpha_lookback_minutes=max(1, cfg.alpha_lookback_minutes // bar_minutes),
        alpha2_lookback_minutes=max(1, cfg.alpha2_lookback_minutes // bar_minutes),
        price_change_horizon_minutes=max(1, cfg.price_change_horizon_minutes // bar_minutes),
        volume_short_window=max(1, cfg.volume_short_window // bar_minutes),
        volume_baseline_window=max(1, cfg.volume_baseline_window // bar_minutes),
        volatility_window=max(1, cfg.volatility_window // bar_minutes),
        alpha2_factor_lag_bars=(max(1,cfg.alpha2_factor_lag_bars // bar_minutes)
                               if cfg.alpha2_factor_lag_bars else 0))


@dataclass
class BacktestTrade:
    entry_ts: datetime
    exit_ts: datetime | None
    direction: str
    option_type: str
    expiry: date
    sell_strike: float
    buy_strike: float
    lots: int
    units: int
    net_credit: float | None
    stop_loss: float | None
    target: float | None
    exit_value: float | None
    exit_reason: str | None
    pnl: float | None
    pnl_pct: float | None
    spot_at_entry: float | None
    alpha: float | None
    alpha2: float | None
    allocated_capital: float | None


@dataclass
class BacktestResult:
    trades: list[BacktestTrade] = field(default_factory=list)
    mode: str = "spot-only"
    bar_minutes: int = 1
    evaluations: int = 0
    first_decision: datetime | None = None
    last_decision: datetime | None = None
    final_position: Position | None = None

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame([dataclasses.asdict(t) for t in self.trades])


class Backtester:
    def __init__(self, cfg: StrategyConfig, calendar: TradingCalendar, bars: pd.DataFrame,
                 expiries_for: Callable[[date], list[date]], lot_size_for: Callable[[date], int],
                 snapshots: pd.DataFrame | None = None, strike_interval: float = 50.0,
                 bar_minutes: int = 1, use_alpha2: bool = True, entry_price_source: str = "ltp"):
        self.base_cfg = cfg
        self.cfg = scale_config(cfg, bar_minutes)
        self.calendar, self.bars = calendar, bars.sort_index()
        self.expiries_for, self.lot_size_for = expiries_for, lot_size_for
        self.snapshots = snapshots if snapshots is not None and not snapshots.empty else None
        self.strike_interval = strike_interval
        self.bar_minutes, self.use_alpha2 = bar_minutes, use_alpha2
        self.engine = StrategyEngine(self.cfg, calendar, entry_price_source, max_data_age_seconds=None,
                                     require_quotes=self.snapshots is not None)

    # ---------------------------------------------------------------- indicators
    def _indicator_frame(self) -> pd.DataFrame:
        cfg, bar = self.cfg, pd.Timedelta(minutes=self.bar_minutes)
        alpha = calculate_alpha(self.bars, cfg.alpha_lookback_minutes, cfg.price_change_horizon_minutes, "live")
        alpha.index = alpha.index + bar          # value usable at the end of its bar
        frame = pd.DataFrame({"alpha": alpha})
        if self.snapshots is not None:
            pc = observed_price_change(self.bars, cfg.price_change_horizon_minutes)
            pc.index = pc.index + bar
            per_expiry = {}
            for expiry, snapshots in self.snapshots.groupby("expiry"):
                panel = build_atm_panel(snapshots)
                per_expiry[expiry] = calculate_alpha2(
                    pc, panel, cfg.alpha2_lookback_minutes, cfg.volume_short_window,
                    cfg.volume_baseline_window, cfg.volatility_window,
                    factor_lag_bars=cfg.alpha2_factor_lag_bars)
            values = []
            for minute in frame.index:
                expiries = [e for e in self.expiries_for(minute.date()) if e >= minute.date()]
                series = per_expiry.get(min(expiries)) if expiries else None
                values.append(series.get(minute, np.nan) if series is not None else np.nan)
            frame["alpha2"] = values
        else:
            frame["alpha2"] = np.nan
        return frame

    def _snapshot_index(self) -> dict:
        """(minute, expiry) -> list of row dicts, built once."""
        if getattr(self, "_snap_idx", None) is None:
            self._snap_idx = {}
            cols = [c for c in ("strike", "spot", "ce_ltp", "pe_ltp", "ce_bid", "ce_ask", "pe_bid", "pe_ask",
                                "ce_cum_volume", "pe_cum_volume") if c in self.snapshots.columns]
            for (m, e), g in self.snapshots.groupby(["minute", "expiry"], sort=False):
                self._snap_idx[(pd.Timestamp(m), e)] = g[cols].to_dict("records")
        return self._snap_idx

    def _chain_at(self, ts: datetime, expiry: date, spot: float) -> OptionChainSnapshot:
        snap = OptionChainSnapshot("NIFTY", expiry, ts, spot)
        if self.snapshots is not None:
            rows = self._snapshot_index().get((pd.Timestamp(ts), expiry), [])
            for r in rows:
                for side in ("ce", "pe"):
                    snap.quotes[(float(r["strike"]), side.upper())] = OptionQuote(
                        float(r["strike"]), side.upper(), r.get(f"{side}_ltp"), r.get(f"{side}_bid"),
                        r.get(f"{side}_ask"), r.get(f"{side}_cum_volume"))
            if rows:
                snap.spot = float(rows[0]["spot"])
            return snap
        # spot-only mode: listed strike grid without quotes
        k0 = round(spot / self.strike_interval) * self.strike_interval
        for i in range(-40, 41):
            k = float(k0 + i * self.strike_interval)
            for side in ("CE", "PE"):
                snap.quotes[(k, side)] = OptionQuote(k, side, None, None, None, None)
        return snap

    # ---------------------------------------------------------------- run
    def _lot_size_at(self, day: date, expiry: date) -> int:
        return self.lot_size_for(day)

    def _observe(self, view, position, result):
        """Replay adapters may record decisions/coverage without changing the engine."""

    def _settlement_at(self, now: datetime, expiry: date):
        return None

    def run(self, start: datetime | None = None, end: datetime | None = None,
            entry_end: datetime | None = None, initial_position: Position | None = None,
            include_open_trade: bool = True, reentry_after_exit: bool = False) -> BacktestResult:
        if not isinstance(reentry_after_exit, bool):
            raise ValueError("reentry_after_exit must be boolean")
        ind = self._indicator_frame()
        res = BacktestResult(mode="full" if self.snapshots is not None else "spot-only",
                             bar_minutes=self.bar_minutes)
        position: Position | None = initial_position
        closes = self.bars["close"]
        bar = pd.Timedelta(minutes=self.bar_minutes)
        for i, (bar_start, close) in enumerate(closes.items()):
            now = (bar_start + bar).to_pydatetime()
            if (start and now < start) or (end and now > end):
                continue
            if (not self.calendar.is_trading_day(now.date()) or
                    (not self.calendar.is_market_open(now) and now.time() != self.cfg.market_close)):
                continue
            if position is None and entry_end is not None and now > entry_end:
                continue
            a = ind["alpha"].get(bar_start + bar, np.nan)
            a2 = ind["alpha2"].get(bar_start + bar, np.nan) if self.use_alpha2 else a
            expiries = self.expiries_for(now.date())
            exp_for_chain = position.expiry if position is not None else (
                min([e for e in expiries if e >= now.date()], default=None))
            if exp_for_chain is None:
                continue
            lot = self._lot_size_at(now.date(), exp_for_chain)
            chain = self._chain_at(pd.Timestamp(now), exp_for_chain, float(close))
            view = MarketView(now=now, spot_bars=self.bars.iloc[i:i + 1], snapshots=None,
                              chain=chain, expiries=expiries, lot_size=lot, position_chain=chain,
                              indicators=(a, a2), settlement=self._settlement_at(now, exp_for_chain))
            out = self.engine.evaluate(view, position)
            self._observe(view, position, out)
            res.evaluations += 1
            res.first_decision = res.first_decision or now
            res.last_decision = now
            if out.action == "exit" and position is not None:
                ev = out.exit
                res.trades.append(BacktestTrade(
                    position.entry_ts, ev.exit_ts, "BULLISH" if position.option_type == "PE" else "BEARISH",
                    position.option_type, position.expiry, position.sell_strike, position.buy_strike,
                    position.lots, position.units, position.net_credit, position.stop_loss, position.target,
                    ev.exit_value, ev.reason, ev.pnl, ev.pnl_pct, position.spot_at_entry, position.alpha,
                    position.alpha2, position.allocated_capital))
                position = None
                # Research option: a second flat evaluation after a real exit,
                # using the same completed bar and current quotes. No repeated
                # exit/entry loop and no source timestamps enter this decision.
                if reentry_after_exit and (entry_end is None or now <= entry_end):
                    entry_expiry = min([e for e in expiries if e >= now.date()], default=None)
                    if entry_expiry is not None:
                        entry_lot = self._lot_size_at(now.date(), entry_expiry)
                        entry_chain = self._chain_at(pd.Timestamp(now), entry_expiry, float(close))
                        entry_view = MarketView(now=now, spot_bars=self.bars.iloc[i:i + 1], snapshots=None,
                            chain=entry_chain, expiries=expiries, lot_size=entry_lot,
                            position_chain=entry_chain, indicators=(a, a2),
                            settlement=self._settlement_at(now, entry_expiry))
                        entry_out = self.engine.evaluate(entry_view, None)
                        self._observe(entry_view, None, entry_out)
                        res.evaluations += 1
                        if entry_out.action == "entry":
                            position = entry_out.position
                            if position.lots == 0 and entry_lot:
                                position.lot_size = entry_lot
            elif out.action == "entry":
                position = out.position
                if position.lots == 0 and lot:
                    position.lot_size = lot
        res.final_position = position
        if position is not None and include_open_trade:   # still open at end of data
            res.trades.append(BacktestTrade(
                position.entry_ts, None, "BULLISH" if position.option_type == "PE" else "BEARISH",
                position.option_type, position.expiry, position.sell_strike, position.buy_strike,
                position.lots, position.units, position.net_credit, position.stop_loss, position.target,
                None, "open at end of data", None, None, position.spot_at_entry, position.alpha,
                position.alpha2, position.allocated_capital))
        return res
