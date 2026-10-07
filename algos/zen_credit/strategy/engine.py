"""Strategy engine: pure decision logic shared by the live service and the backtester.

One call to :meth:`StrategyEngine.evaluate` = one evaluation at decision time
``view.now``. An open position is always evaluated for exit first; a new entry is
considered only when flat (one position at a time in this reconstruction),
and never in the same evaluation that closed a position.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import asdict, dataclass, field
from datetime import date, datetime

import pandas as pd

from data.market_calendar import TradingCalendar
from config import StrategyConfig
from data.providers.base import ExpirySettlement, OptionChainSnapshot
from strategy.alpha import calculate_alpha, observed_price_change
from strategy.alpha2 import build_atm_panel, calculate_alpha2
from risk.exits import ExitDecision, evaluate_exit, time_exit_due
from risk.position_sizing import RiskPlan, allocated_capital, build_risk_plan, spread_pnl
from strategy.signals import Signal, evaluate_signal, in_signal_window
from strategy.spreads import SpreadLegs, build_spread, select_expiry
from utils.time import minute_bucket, round_pct, round_price, to_ist

STRATEGY_NAME = "zen-credit-spread-overnight"


@dataclass
class MarketView:
    now: datetime
    spot_bars: pd.DataFrame                     # complete 1-minute bars
    snapshots: pd.DataFrame                     # stored chain rows (nearest expiry), incl. current minute
    chain: OptionChainSnapshot | None           # current chain, nearest expiry
    expiries: list[date]
    lot_size: int | None
    position_chain: OptionChainSnapshot | None = None   # chain of the open position's expiry
    # Backtest only: (alpha, alpha2) precomputed with the same causal functions.
    # tests/unit/test_leakage.py proves they equal a fresh computation on data
    # truncated at ``now``.
    indicators: tuple[float, float] | None = None
    settlement: ExpirySettlement | None = None


@dataclass
class Position:
    signal_id: str
    entry_ts: datetime
    expiry: date
    option_type: str
    sell_strike: float
    buy_strike: float
    lots: int
    lot_size: int
    units: int
    sell_price: float | None
    buy_price: float | None
    net_credit: float | None
    stop_loss: float | None
    target: float | None
    max_loss: float | None
    max_profit: float | None
    exit_due: datetime
    spot_at_entry: float | None = None
    alpha: float | None = None
    alpha2: float | None = None
    allocated_capital: float | None = None


@dataclass
class ExitEvent:
    reason: str
    exit_ts: datetime
    exit_value: float | None
    pnl: float | None
    pnl_pct: float | None


@dataclass
class EngineResult:
    action: str                                  # "entry" | "exit" | "none"
    reason: str = ""
    position: Position | None = None
    exit: ExitEvent | None = None
    diagnostics: dict = field(default_factory=dict)


def make_signal_id(ts: datetime, legs: SpreadLegs) -> str:
    key = "|".join([STRATEGY_NAME, minute_bucket(ts).isoformat(), legs.expiry.isoformat(),
                    f"{legs.sell_strike:.0f}", f"{legs.buy_strike:.0f}", legs.option_type])
    return hashlib.sha256(key.encode()).hexdigest()[:20]


class StrategyEngine:
    def __init__(self, cfg: StrategyConfig, calendar: TradingCalendar, entry_price_source: str = "ltp",
                 max_data_age_seconds: int | None = 180, require_quotes: bool = True):
        self.cfg, self.calendar = cfg, calendar
        self.entry_price_source = entry_price_source
        self.max_age = max_data_age_seconds
        self.require_quotes = require_quotes
        if cfg.strike_reference not in {"last_bar_open", "spot"}:
            raise ValueError("strike_reference must be last_bar_open or spot")
        if cfg.max_short_premium is not None and (not math.isfinite(cfg.max_short_premium) or cfg.max_short_premium <= 0):
            raise ValueError("max_short_premium must be positive or None")

    # ---------------------------------------------------------------- indicators
    def indicators(self, view: MarketView) -> tuple[float, float, dict]:
        cfg = self.cfg
        if view.indicators is not None:
            return float(view.indicators[0]), float(view.indicators[1]), {}
        bars = view.spot_bars
        alpha_s = calculate_alpha(bars, cfg.alpha_lookback_minutes, cfg.price_change_horizon_minutes, "live")
        alpha = float(alpha_s.iloc[-1]) if len(alpha_s) else float("nan")
        # decision minute m uses the bar that started at m-1 (last complete bar)
        pc = observed_price_change(bars, cfg.price_change_horizon_minutes)
        pc.index = pc.index + pd.Timedelta(minutes=1)
        alpha2 = float("nan")
        comps: dict = {}
        if view.snapshots is not None and not view.snapshots.empty:
            panel = build_atm_panel(view.snapshots)
            a2, parts = calculate_alpha2(pc, panel, cfg.alpha2_lookback_minutes, cfg.volume_short_window,
                                         cfg.volume_baseline_window, cfg.volatility_window,
                                         return_components=True, factor_lag_bars=cfg.alpha2_factor_lag_bars)
            m = minute_bucket(view.now)
            if len(a2) and a2.index[-1] == m:
                alpha2 = float(a2.iloc[-1])
                comps = {k: _f(v) for k, v in parts.iloc[-1].items()}
        return alpha, alpha2, comps

    # ---------------------------------------------------------------- data checks
    def _stale(self, ts: datetime, now: datetime) -> bool:
        if self.max_age is None:
            return False
        return abs((to_ist(now) - to_ist(ts)).total_seconds()) > self.max_age

    def data_problems(self, view: MarketView) -> list[str]:
        p = []
        if view.spot_bars is None or view.spot_bars.empty:
            p.append("no spot bars")
        else:
            last_bar_end = view.spot_bars.index[-1] + pd.Timedelta(minutes=1)
            if self._stale(last_bar_end.to_pydatetime(), view.now):
                p.append("stale spot bars")
        if view.chain is None:
            p.append("no option chain")
        else:
            if self._stale(view.chain.timestamp, view.now):
                p.append("stale option chain")
            if not (view.chain.spot and math.isfinite(view.chain.spot) and view.chain.spot > 0):
                p.append("invalid chain spot")
        if not view.expiries:
            p.append("no expiries")
        if not view.lot_size or view.lot_size <= 0:
            p.append("no lot size")
        return p

    # ---------------------------------------------------------------- prices
    def _leg_price(self, chain: OptionChainSnapshot, strike: float, opt: str, side: str) -> float | None:
        q = chain.quote(strike, opt)
        if q is None:
            return None
        if self.entry_price_source == "bidask":
            px = q.bid if side == "SELL" else q.ask
        else:
            px = q.ltp
        if px is None or not math.isfinite(px) or px < 0:
            return None
        return float(px)

    def spread_value(self, chain: OptionChainSnapshot | None, pos: Position) -> float | None:
        """Cost to close: buy back the short leg, sell the long leg."""
        if chain is None or chain.expiry != pos.expiry:
            return None
        s = self._leg_price(chain, pos.sell_strike, pos.option_type, "BUY")
        b = self._leg_price(chain, pos.buy_strike, pos.option_type, "SELL")
        if s is None or b is None:
            return None
        return round_price(s - b)

    # ---------------------------------------------------------------- evaluation
    def evaluate(self, view: MarketView, position: Position | None) -> EngineResult:
        now = to_ist(view.now)
        if position is not None:
            return self._evaluate_exit(view, position, now)
        return self._evaluate_entry(view, now)

    def _evaluate_exit(self, view: MarketView, pos: Position, now: datetime) -> EngineResult:
        chain = view.position_chain or view.chain
        if chain is not None and self._stale(chain.timestamp, now):
            chain = None
        # After expiry, a later quote/spot cannot represent the contract's settlement.
        value = self.spread_value(chain, pos) if now.date() <= pos.expiry else None
        decision: ExitDecision | None = evaluate_exit(now, value, pos.stop_loss if pos.stop_loss is not None
                                                      else math.inf, pos.target if pos.target is not None
                                                      else -math.inf, pos.exit_due, pos.expiry)
        diag = {"spread_value": value, "stop_loss": pos.stop_loss, "target": pos.target,
                "exit_due": pos.exit_due.isoformat()}
        if decision is None:
            return EngineResult("none", "position held", position=pos, diagnostics=diag)
        if decision.reason == "Expiry":
            settlement = view.settlement
            if (settlement is not None and settlement.expiry == pos.expiry and settlement.source
                    and math.isfinite(settlement.spot) and settlement.spot > 0):
                decision = ExitDecision("Expiry", intrinsic_spread_value(pos, settlement.spot))
                diag["settlement_source"] = settlement.source
            elif self.require_quotes or pos.net_credit is not None:
                return EngineResult("none", "Expiry due but official settlement unavailable",
                                    position=pos, diagnostics=diag)
        if decision.spread_value is None and self.require_quotes:
            return EngineResult("none", f"{decision.reason} due but no valid quotes", position=pos,
                                diagnostics=diag)
        pnl = pct = None
        if decision.spread_value is not None and pos.net_credit is not None:
            pnl = spread_pnl(pos.net_credit, decision.spread_value, pos.units)
            capital = pos.allocated_capital
            if capital is None:
                # Compatibility with positions saved before allocated capital was persisted.
                capital = allocated_capital(to_ist(pos.entry_ts).date(), self.cfg)
            if not math.isfinite(capital) or capital <= 0:
                return EngineResult("none", "invalid allocated capital", position=pos, diagnostics=diag)
            pct = round_pct(100.0 * pnl / capital)
        ev = ExitEvent(decision.reason, now, decision.spread_value, pnl, pct)
        return EngineResult("exit", decision.reason, position=pos, exit=ev, diagnostics=diag)

    def _evaluate_entry(self, view: MarketView, now: datetime) -> EngineResult:
        if not self.calendar.is_trading_day(now.date()):
            return EngineResult("none", "not a trading day")
        if not in_signal_window(now, self.cfg):
            return EngineResult("none", "outside signal window")
        problems = self.data_problems(view) if self.require_quotes else []
        if not self.require_quotes and (view.spot_bars is None or view.spot_bars.empty):
            problems = ["no spot bars"]
        if problems:
            return EngineResult("none", "data: " + "; ".join(problems))
        alpha, alpha2, comps = self.indicators(view)
        diag = {"alpha": _f(alpha), "alpha2": _f(alpha2), **comps}
        signal = evaluate_signal(alpha, alpha2, now, self.cfg)
        diag["signal"] = signal.value
        if signal == Signal.NONE:
            return EngineResult("none", "no signal", diagnostics=diag)
        spot = view.chain.spot if view.chain is not None else float(view.spot_bars["close"].iloc[-1])
        reference_spot = float(view.spot_bars["open"].iloc[-1]) if self.cfg.strike_reference == "last_bar_open" else spot
        if not math.isfinite(reference_spot) or reference_spot <= 0:
            return EngineResult("none", "invalid strike reference", diagnostics=diag)
        diag.update({"strike_reference":self.cfg.strike_reference,"strike_reference_spot":reference_spot})
        expiry = select_expiry(now.date(), view.expiries)
        strikes = view.chain.strikes if view.chain is not None else []
        try:
            legs = build_spread(signal, reference_spot, strikes, expiry, self.cfg.spread_distance)
        except ValueError as exc:
            return EngineResult("none", f"spread: {exc}", diagnostics=diag)
        sell_px = buy_px = None
        plan: RiskPlan | None = None
        if view.chain is not None and view.chain.expiry == expiry:
            sell_px = self._leg_price(view.chain, legs.sell_strike, legs.option_type, "SELL")
            buy_px = self._leg_price(view.chain, legs.buy_strike, legs.option_type, "BUY")
        if sell_px is not None and buy_px is not None and view.lot_size:
            if self.cfg.max_short_premium is not None and sell_px > self.cfg.max_short_premium:
                diag.update({"short_premium":sell_px,"max_short_premium":self.cfg.max_short_premium})
                return EngineResult("none", "short premium above maximum", diagnostics=diag)
            try:
                plan = build_risk_plan(sell_px, buy_px, self.cfg.spread_distance, view.lot_size,
                                       now.date() == expiry, self.cfg, now.date())
            except ValueError as exc:
                return EngineResult("none", f"risk: {exc}", diagnostics=diag)
            if plan.lots < 1:
                return EngineResult("none", "capital below one lot margin", diagnostics=diag)
        elif self.require_quotes:
            return EngineResult("none", "missing leg quotes", diagnostics=diag)
        lot_size = view.lot_size or 0
        pos = Position(
            signal_id=make_signal_id(now, legs), entry_ts=now, expiry=expiry, option_type=legs.option_type,
            sell_strike=legs.sell_strike, buy_strike=legs.buy_strike,
            lots=plan.lots if plan else 0, lot_size=lot_size, units=plan.units if plan else 0,
            sell_price=sell_px, buy_price=buy_px, net_credit=plan.net_credit if plan else None,
            stop_loss=plan.stop_loss if plan else None, target=plan.target if plan else None,
            max_loss=plan.max_loss if plan else None, max_profit=plan.max_profit if plan else None,
            exit_due=time_exit_due(now, expiry, self.calendar, self.cfg), spot_at_entry=spot,
            alpha=_f(alpha), alpha2=_f(alpha2),
            allocated_capital=plan.allocated_capital if plan else allocated_capital(now.date(), self.cfg))
        return EngineResult("entry", signal.value, position=pos, diagnostics=diag)


def intrinsic_spread_value(pos: Position, spot: float) -> float:
    if pos.option_type == "CE":
        v = max(spot - pos.sell_strike, 0.0) - max(spot - pos.buy_strike, 0.0)
    else:
        v = max(pos.sell_strike - spot, 0.0) - max(pos.buy_strike - spot, 0.0)
    return round_price(v)


def _f(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def position_to_dict(p: Position) -> dict:
    d = asdict(p)
    for k, v in d.items():
        if isinstance(v, (datetime, date)):
            d[k] = v.isoformat()
    return d
