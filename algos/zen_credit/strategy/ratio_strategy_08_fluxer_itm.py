# Strategy08: ratio_strategy_04 without the put volatility cap, short strike 50 points in the money
# (research candidate, 20 Nov 2026).
#
# Same skew signal, hedge width, expiry rules, sizing and execution as ratio_strategy_04 (imported, not
# copied). Two changes, found with backtest.ratio_variants (1,005 variants around R4 on the three-year
# minute dataset, 4 Oct 2023 - 30 Sep 2026) and required to beat R4 in each year without more drawdown:
# * No realised-volatility cap on credit put spreads. R3 pinned "no put above 16% 20-session realised
#   volatility" because it removed three R3 trades the provider did not take in March-April 2026. Under
#   R4's afternoon entry and delayed stop those put signals are profitable: 8 more trades over three
#   years, 6 winners, 2 stops. Caps of 20, 25 and 30 sit between R4 and no cap, so the effect is graded.
# * Short strike one 50-point step in the money (a lower call strike, a higher put strike), hedge still
#   400 points beyond it. The credit is 15-30 points larger while the stop stays at credit + 50, so the
#   average winner grows and the average stop loss does not; 2 of 57 common trades turn from winners
#   into stops and the win rate falls from 83% to 78%. Two steps in the money raises the drawdown to 16%.
# Everything else in R4 stayed the best of its neighbours when re-tested on top of these two changes
# (entry from 11:45, credit + 50 stop after 60 minutes, credit + 100 disaster stop, 40% entry-day target).
# This is the best of roughly 2,500 variants tried on the same three years (1,500 for R4, 1,005 here):
# the improvement over R4 is an in-sample selection and has to be confirmed by forward paper trading.
from dataclasses import replace

from strategy import ratio_strategy_03_fluxer as _r3
from strategy.ratio_strategy_04_fluxer_tuned import *  # noqa: F401,F403  (signal, panel, constants, R4 execution)
from strategy.ratio_strategy_04_fluxer_tuned import apply_profile as _r4_profile, LIMITATIONS as _R4_LIMITATIONS

STRATEGY_NAME = 'ratio_strategy_08'
DESCRIPTION = ('ratio_strategy_04 execution (11:45-14:15 entries, credit + 50 stop after 60 minutes, credit + 100 '
               'disaster stop, 40% entry-day target) with no realised-volatility cap on put spreads and the short '
               'strike 50 points in the money.')
PUT_RV_MAX = None              # no realised-volatility cap on credit put spreads (R3/R4: 16%)
SHORT_STRIKE_OTM_POINTS = -50  # short strike one step in the money (R3/R4: at the money)
LIMITATIONS = [line for line in _R4_LIMITATIONS if not line.startswith('Put spreads need 21 completed sessions')] + [
    'The put volatility cap was removed and the short strike moved 50 points in the money after about 2,500 '
    'rule variants were tried on the same three years; expect less than the replayed edge over ratio_strategy_04.',
    'Without the volatility cap, put spreads are sold after sharp sell-offs too (8 of 27 replayed put trades); '
    'the in-the-money short strike adds directional exposure and loses the trade more often (78% winners).',
]


def apply_profile(cfg=None):
    return replace(_r4_profile(cfg), short_strike_otm_points=SHORT_STRIKE_OTM_POINTS)


def calculate_indicators(bars, panel):
    """R3's indicators with the put realised-volatility cap switched off (``rv`` stays as a diagnostic)."""
    return _r3.calculate_indicators(bars, panel, put_rv_max=PUT_RV_MAX)


def create_engine(cfg, calendar, **kwargs):
    import sys
    from strategy.registry import create_named_engine
    return create_named_engine(sys.modules[__name__], cfg, calendar, **kwargs)
