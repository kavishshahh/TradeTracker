"""Exit rules inferred from the provider trade history.

Priority when several conditions hold at the same evaluation:
  1. Stop loss   : spread value >= stop level
  2. Target      : spread value <= target level
  3. Time exit   : at TIME_EXIT on the next trading day after entry; a trade
                   entered on its expiry day is squared off at TIME_EXIT the
                   same day. Never later than the expiry day.
  4. Expiry      : safety net if the position is still open after expiry.
No signal-reversal exit is implemented. The private exit logic remains unverified.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from data.market_calendar import TradingCalendar
from config import StrategyConfig
from utils.time import combine_ist, to_ist

STOP_LOSS = "Stop loss"
TARGET = "Target"
TIME_EXIT = "Time exit"
EXPIRY = "Expiry"


@dataclass(frozen=True)
class ExitDecision:
    reason: str
    spread_value: float | None


def time_exit_due(entry_ts: datetime, expiry: date, calendar: TradingCalendar,
                  cfg: StrategyConfig) -> datetime:
    entry_day = to_ist(entry_ts).date()
    if entry_day >= expiry:
        exit_day = expiry
    else:
        exit_day = min(calendar.next_trading_day(entry_day), expiry)
    clock = cfg.time_exit
    if (cfg.historical_time_exit_start is not None and cfg.historical_time_exit_end is not None
            and cfg.historical_time_exit_start <= entry_day <= cfg.historical_time_exit_end):
        clock = cfg.historical_time_exit
    return combine_ist(exit_day, clock)


def evaluate_exit(now: datetime, spread_value: float | None, stop_loss: float, target: float,
                  exit_due: datetime, expiry: date) -> ExitDecision | None:
    now = to_ist(now)
    if now.date() > expiry:
        return ExitDecision(EXPIRY, spread_value)
    if spread_value is not None:
        if spread_value >= stop_loss:
            return ExitDecision(STOP_LOSS, spread_value)
        if spread_value <= target:
            return ExitDecision(TARGET, spread_value)
    if now >= exit_due:
        return ExitDecision(TIME_EXIT, spread_value)
    return None
