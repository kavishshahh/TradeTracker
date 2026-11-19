# Strategy09: the Damper-style intraday credit spread, tuned for a drawdown under 20% (research, 20 Nov 2026).
#
# Started from zen_strategy_07 (the replica of Stratzy's Damper: zen_strategy_01's signal, flat the same day,
# stop at credit + 40, one re-entry after a stop). Over Oct 2023 - Sep 2026 that replica earns about 36% a year
# with an 84% drawdown and a losing second year. Four changes, chosen on those three years with
# backtest.zen_improve (about 800 variants) and confirmed with backtest.dhan_replay --carry-missing-hedge:
# * zen_strategy_02's signal (the variance-scaled beta) instead of zen_strategy_01's: with Damper's exits it
#   earned about 40% more with a third less drawdown;
# * a profit target at 50% of the entry credit instead of "spread <= 10";
# * a profit lock: once 20% of the credit is earned, the stop moves to the entry credit, so a trade that was
#   ahead can no longer become a full stop-loss. It closes as "Profit lock" (about flat) and, like a target or
#   time exit, allows no re-entry that day. This is what lifts average win / average loss from about 0.65
#   to about 1.4 (the win rate falls from 65% to 47%, because break-even exits count as small losses);
# * lots capped so one stop-loss exit loses at most 2.5% of model capital (3 lots of 65 instead of 5).
# Three-year replay (844 trades): about 40% a year on INR 320,000, drawdown 17.7%, average win / average loss
# 1.39, profit factor 1.24, each year 39-42%, 10 losing months of 36. Those figures value a hedge leg that had
# no cached price at the exit minute (10% of exits) by Black-Scholes from its own last print; booking it at
# zero instead gives 15% a year with a 20.2% drawdown, at its last print 49% and 17.6%. Live quotes have no
# such gap. Neighbours: a lock at 30% gives 40% a year with a 20.6% drawdown; a 30% target without the lock
# 43% a year, 19.3% drawdown, average win / loss 0.65. The one-session pause of zen_strategy_05/06 hurts here.
# Everything else (strike, 400-point hedge, premium <= 200, entry window, 14:54 exit, re-entry rule) is
# zen_strategy_07's. The signal was chosen on Jul 2025 - Oct 2026; these exit and risk rules on all three years,
# so there is no untouched hold-out: paper trading is the real test.
from dataclasses import replace
from datetime import time

from strategy.zen_strategy_02_variance_credit import *  # noqa: F401,F403  (signal, panel and constants)
from strategy.zen_strategy_02_variance_credit import apply_profile as _base_profile

STRATEGY_NAME = 'zen_strategy_09'
DESCRIPTION = ('zen_strategy_02 signal traded intraday: flat by 14:54, stop at credit + 40 that moves to break-even after a '
               '20% gain, target at 50% of the credit, one re-entry after a stop, lots capped at a 2.5% loss per stop.')
PROFIT_TARGET_ENABLED = True       # zen_strategy_02 itself trades without a target
STOP_POINTS = 40.0
TARGET_CREDIT_FRACTION = 0.5
PROFIT_LOCK_TRIGGER = 0.2          # once 20% of the credit is earned ...
PROFIT_LOCK_KEEP = 0.0             # ... the stop moves to the entry credit (break-even)
MAX_LOSS_FRACTION = 0.025
TIME_EXIT = time(14, 54)
MAX_ENTRIES_PER_DAY = 2


def apply_profile(cfg=None):
    base = _base_profile(cfg)
    normal_points = base.margin_to_width_ratio * base.spread_distance   # normal margin per lot / lot size
    return replace(base, stop_loss_margin_fraction=STOP_POINTS / normal_points,
                   target_credit_fraction=TARGET_CREDIT_FRACTION, max_loss_fraction=MAX_LOSS_FRACTION,
                   profit_lock_trigger_fraction=PROFIT_LOCK_TRIGGER, profit_lock_keep_fraction=PROFIT_LOCK_KEEP,
                   time_exit=TIME_EXIT, time_exit_same_day=True, max_entries_per_day=MAX_ENTRIES_PER_DAY,
                   reentry_after_stop_only=True)


def create_engine(cfg, calendar, **kwargs):
    import sys
    from strategy.registry import create_named_engine
    return create_named_engine(sys.modules[__name__], cfg, calendar, **kwargs)
