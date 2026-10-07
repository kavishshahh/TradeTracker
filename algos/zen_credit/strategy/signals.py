"""Signal rule: both alphas above 0.8 -> bullish, both below 0.2 -> bearish,
evaluated only inside the 10:15-14:15 Asia/Kolkata window (inclusive)."""
from __future__ import annotations

import math
from datetime import datetime
from enum import Enum

from config import StrategyConfig
from utils.time import to_ist


class Signal(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NONE = "NONE"


def in_signal_window(ts: datetime, cfg: StrategyConfig) -> bool:
    t = to_ist(ts).time()
    return cfg.signal_start <= t <= cfg.signal_end


def evaluate_signal(alpha: float, alpha2: float, ts: datetime, cfg: StrategyConfig) -> Signal:
    if not in_signal_window(ts, cfg):
        return Signal.NONE
    if alpha is None or alpha2 is None or math.isnan(alpha) or math.isnan(alpha2):
        return Signal.NONE
    if alpha > cfg.bullish_threshold and alpha2 > cfg.bullish_threshold:
        return Signal.BULLISH
    if alpha < cfg.bearish_threshold and alpha2 < cfg.bearish_threshold:
        return Signal.BEARISH
    return Signal.NONE
