# Strategy04: ratio_strategy_03 with drawdown-tuned execution (research candidate, 20 Oct 2026).
#
# Same signal, strikes, hedge, expiry rules and sizing as ratio_strategy_03 (imported, not copied).
# Execution changes, chosen on the three-year replay (4 Oct 2023 - 30 Sep 2026) with
# backtest.ratio_improve and required to improve each year separately:
# * entries from 11:45 IST (R3: 10:15); the entry cut-off stays 14:15. Morning skew extremes were the
#   main source of same-day stop-outs; any start from 11:30 to 12:15 behaves alike.
# * stop at credit + 50 points (5.56% of normal margin per lot; R3: + 45), checked from 60 minutes
#   after entry; during those 60 minutes only a disaster stop at credit + 100 applies (never reached
#   in the replay, it bounds the tail).
# * credit target at 40% of the entry credit (R3: 50%), still on the entry day only.
# The pinned gate itself was fitted on Oct 2025 - Sep 2026, so only Oct 2023 - Sep 2025 is out of
# sample for the signal; these execution rules were selected on all three years.
from dataclasses import replace
from datetime import time

from strategy.ratio_strategy_03_fluxer import *  # noqa: F401,F403  (signal, panel and constants)
from strategy.ratio_strategy_03_fluxer import apply_profile as _r3_profile, LIMITATIONS as _R3_LIMITATIONS

STRATEGY_NAME = 'ratio_strategy_04'
DESCRIPTION = ('ratio_strategy_03 signal with afternoon entries (11:45-14:15), a credit + 50 stop active '
               'after 60 minutes (credit + 100 disaster stop always on) and a 40% entry-day credit target.')
ENTRY_START = time(11, 45)
STOP_POINTS = 50.0
HARD_STOP_POINTS = 100.0
STOP_GRACE_MINUTES = 60
TARGET_CREDIT_FRACTION = 0.4
LIMITATIONS = _R3_LIMITATIONS + [
    'Execution rules (entry start, stop, grace period, target) were chosen on the same three years they are '
    'evaluated on; treat the improvement as provisional until forward paper trading confirms it.',
]


def apply_profile(cfg=None):
    base = _r3_profile(cfg)
    normal_points = base.margin_to_width_ratio * base.spread_distance   # normal margin per lot / lot size
    return replace(base, signal_start=ENTRY_START, stop_loss_margin_fraction=STOP_POINTS / normal_points,
                   hard_stop_margin_fraction=HARD_STOP_POINTS / normal_points, stop_grace_minutes=STOP_GRACE_MINUTES,
                   target_credit_fraction=TARGET_CREDIT_FRACTION)


def create_engine(cfg, calendar, **kwargs):
    import sys
    from strategy.registry import create_named_engine
    return create_named_engine(sys.modules[__name__], cfg, calendar, **kwargs)
