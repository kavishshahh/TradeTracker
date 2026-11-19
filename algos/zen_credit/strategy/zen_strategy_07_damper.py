# Strategy07: replica of Stratzy's "Damper Credit Spread" (Dhan Algos), fitted 20 Nov 2026.
#
# Damper's 316 published trades (17 Sep 2025 - 19 Nov 2026, damper-past-trades.csv at the repo root) are
# zen_strategy_01's signal traded intraday. Same signal, ATM strike from the last completed candle's open,
# 400-point hedge, short premium <= 200, 10:15-14:15 entry window and sizing as zen_strategy_01 (imported,
# not copied); the differences are all in the exits and re-entries:
# * flat the same day: scheduled exit 14:54 on the entry day (15:00 in the provider-history window,
#   9 Jul 2025 - 30 Jun 2026, exactly like zen_strategy_01's next-day exit);
# * stop at credit + 40 points (published stops close at credit + 40-46; zen_strategy_01 uses + 45);
# * target when the spread is worth 10 or less (the same rule; in practice it only fires on expiry days);
# * after a stop it may enter once more that day (45 of Damper's 46 second trades followed a stop, usually
#   2 minutes later and on the other side); after a target or time exit, nothing more that day;
# * 80% of capital on Mondays from 22 Dec 2025 (Damper's first 80% Monday; Nov 2026 Mondays were 100%).
# Fit on 17 Sep 2025 - 30 Sep 2026 with backtest.zen_improve (exit_mode="same_day"): 245 of 275 published
# trades on the same day and side, 178 at the same strike within 3 minutes, and on those 178 the simulator
# made INR 438,850 against Damper's 431,417. Stops of 38/42/45 points all fit worse than 40. Remaining
# differences are signal-level: 55 simulated trades Damper did not take, 30 Damper trades not simulated.
# Damper's realised drawdown on the published trades is about 27% of INR 320,000 (above the 25% listing rule).
from dataclasses import replace
from datetime import date, time

from strategy.zen_strategy_01_geometric_credit import *  # noqa: F401,F403  (signal, panel and constants)
from strategy.zen_strategy_01_geometric_credit import apply_profile as _base_profile
from strategy import zen_strategy_01_geometric_credit as _base

STRATEGY_NAME = 'zen_strategy_07'
DESCRIPTION = ('zen_strategy_01 signal traded intraday like Stratzy\'s Damper: flat by 14:54, stop at credit + 40, '
               'one re-entry after a stop.')
PROFIT_TARGET_ENABLED = getattr(_base, 'PROFIT_TARGET_ENABLED', True)
STOP_POINTS = 40.0
TIME_EXIT = time(14, 54)
MAX_ENTRIES_PER_DAY = 2
MONDAY_ALLOCATION_START = date(2025, 12, 22)


def apply_profile(cfg=None):
    base = _base_profile(cfg)
    normal_points = base.margin_to_width_ratio * base.spread_distance   # normal margin per lot / lot size
    return replace(base, stop_loss_margin_fraction=STOP_POINTS / normal_points, time_exit=TIME_EXIT,
                   time_exit_same_day=True, max_entries_per_day=MAX_ENTRIES_PER_DAY, reentry_after_stop_only=True,
                   monday_allocation_start=MONDAY_ALLOCATION_START)


def create_engine(cfg, calendar, **kwargs):
    import sys
    from strategy.registry import create_named_engine
    return create_named_engine(sys.modules[__name__], cfg, calendar, **kwargs)
