"""Sizing and risk levels for a credit spread.

All spread values are per unit (points). For SELL leg price S and BUY leg price B:

    net_credit     = S - B
    units          = lots * lot_size
    gross_credit   = net_credit * units
    max_profit     = net_credit * units
    max_loss       = (width - net_credit) * units
    stop_loss      = net_credit + stop_loss_margin_fraction * normal_margin_per_lot / lot_size
    target         = target_spread_value            (exit when spread value <= target)

``normal_margin_per_lot`` is the broker margin of one lot on a non-expiry day.
The provider's own margins are not reproducible from free data, so it is
estimated as ``margin_to_width_ratio * width * lot_size`` unless
MARGIN_PER_LOT is configured. Lots = floor(allocated capital / margin_per_lot), where the
expiry-day margin (normal * expiry_day_margin_multiplier) applies on expiry day.
The observed schedule allocates 80% on Mondays from 6 April 2026; other entries
use 100%. The amount used at entry is persisted with the position.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

from config import StrategyConfig
from utils.time import round_money, round_price


@dataclass(frozen=True)
class RiskPlan:
    lots: int
    lot_size: int
    units: int
    net_credit: float
    gross_credit: float
    stop_loss: float
    target: float
    max_loss: float
    max_profit: float
    margin_per_lot: float
    normal_margin_per_lot: float
    allocated_capital: float


def allocated_capital(entry_date: date, cfg: StrategyConfig) -> float:
    """Observed allocation schedule; the fraction and start date are configurable."""
    if not math.isfinite(cfg.capital) or cfg.capital <= 0:
        raise ValueError("capital must be finite and positive")
    if not 0 < cfg.monday_capital_fraction <= 1:
        raise ValueError("Monday capital fraction must be in (0, 1]")
    fraction = (cfg.monday_capital_fraction
                if entry_date >= cfg.monday_allocation_start and entry_date.weekday() == 0 else 1.0)
    return round_money(cfg.capital * fraction)


def normal_margin_per_lot(width: float, lot_size: int, cfg: StrategyConfig) -> float:
    if cfg.margin_per_lot_override:
        return float(cfg.margin_per_lot_override)
    return cfg.margin_to_width_ratio * width * lot_size


def margin_per_lot(width: float, lot_size: int, is_expiry_day: bool, cfg: StrategyConfig) -> float:
    m = normal_margin_per_lot(width, lot_size, cfg)
    return m * cfg.expiry_day_margin_multiplier if is_expiry_day else m


def lots_for_capital(capital: float, margin: float) -> int:
    if margin <= 0:
        raise ValueError("margin must be positive")
    return int(math.floor(capital / margin))


def net_credit(sell_price: float, buy_price: float) -> float:
    return round_price(sell_price - buy_price)


def build_risk_plan(sell_price: float, buy_price: float, width: float, lot_size: int,
                    is_expiry_day: bool, cfg: StrategyConfig, entry_date: date) -> RiskPlan:
    if sell_price < 0 or buy_price < 0:
        raise ValueError("negative option price")
    if lot_size <= 0:
        raise ValueError("invalid lot size")
    credit = net_credit(sell_price, buy_price)
    if credit <= 0:
        raise ValueError("spread does not produce a credit")
    normal = normal_margin_per_lot(width, lot_size, cfg)
    margin = margin_per_lot(width, lot_size, is_expiry_day, cfg)
    capital = allocated_capital(entry_date, cfg)
    lots = lots_for_capital(capital, margin)
    units = lots * lot_size
    stop = round_price(credit + cfg.stop_loss_margin_fraction * normal / lot_size)
    return RiskPlan(
        lots=lots, lot_size=lot_size, units=units, net_credit=credit,
        gross_credit=round_money(credit * units), stop_loss=stop,
        target=round_price(cfg.target_spread_value),
        max_loss=round_money((width - credit) * units),
        max_profit=round_money(credit * units),
        margin_per_lot=round_money(margin), normal_margin_per_lot=round_money(normal),
        allocated_capital=capital,
    )


def spread_pnl(entry_credit: float, exit_value: float, units: int) -> float:
    return round_money((entry_credit - exit_value) * units)
