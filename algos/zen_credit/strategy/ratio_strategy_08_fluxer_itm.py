# Strategy08: ratio_strategy_04 with the short strike 50 points in the money (research candidate, 20 Nov 2026).
#
# Same skew signal (including the put volatility cap), hedge width, expiry rules, sizing and execution as
# ratio_strategy_04 (imported, not copied). One change, found with backtest.ratio_variants (1,005 variants
# around R4 on the three-year minute dataset, 4 Oct 2023 - 30 Sep 2026):
# * Short strike one 50-point step in the money (a lower call strike, a higher put strike), hedge still
#   400 points beyond it. The credit is 15-30 points larger while the stop stays at credit + 50, so the
#   average winner grows and the average stop loss does not; some common trades turn from winners into
#   stops and the win rate falls. Two steps in the money raises the drawdown.
# Everything else in R4 stayed the best of its neighbours when re-tested on top of this change
# (entry from 11:45, credit + 50 stop after 60 minutes, credit + 100 disaster stop, 40% entry-day target).
#
# History of the put volatility cap. The strategy was listed on 20 Nov 2026 with a second change from the
# same search: no realised-volatility cap on credit put spreads (R3/R4: none above 16% over 20 sessions).
# On the three searched years that added 8 trades, 6 of them winners. On 22 Nov 2026 the rules were replayed
# on 14 Dec 2021 - 3 Oct 2023, which no search had used (next-candle fills, real costs, INR 3.2 lakh):
#   five years, no cap    110 trades  +13.00 lakh  drawdown 42.7%  worst trade -67,656
#   five years, with cap   76 trades  +11.25 lakh  drawdown 23.0%  worst trade -35,592
# Without the cap it sold put spreads through the falling market of 2022: four stops in six days in May
# 2022, one of them an overnight gap that cost 21% of capital. The cap was restored on 22 Nov 2026, before
# the strategy had a paper trade. Any cap from 12.8% to 19.2% gives the same drawdown; 16% is R3's value.
# The short strike is the best of roughly 2,500 variants tried on the same three years (1,500 for R4,
# 1,005 here): the improvement over R4 is an in-sample selection and has to be confirmed by paper trading.
from dataclasses import replace

from strategy.ratio_strategy_04_fluxer_tuned import *  # noqa: F401,F403  (signal, panel, constants, R4 execution)
from strategy.ratio_strategy_04_fluxer_tuned import apply_profile as _r4_profile, LIMITATIONS as _R4_LIMITATIONS

STRATEGY_NAME = 'ratio_strategy_08'
DESCRIPTION = ('ratio_strategy_04 (11:45-14:15 entries, credit + 50 stop after 60 minutes, credit + 100 disaster '
               'stop, 40% entry-day target, no put spread above 16% realised volatility) with the short strike 50 '
               'points in the money.')
SHORT_STRIKE_OTM_POINTS = -50  # short strike one step in the money (R3/R4: at the money)
LIMITATIONS = _R4_LIMITATIONS + [
    'The short strike moved 50 points in the money after about 2,500 rule variants were tried on the same three '
    'years; expect less than the replayed edge over ratio_strategy_04. It adds directional exposure.',
    'Lots are sized on margin alone: a spread that opens beyond its stop after an overnight gap can lose about a '
    'quarter of capital in one trade. In 14 Dec 2021 - 3 Oct 2023 five of 18 trades were gap stops.',
    'On 14 Dec 2021 - 3 Oct 2023, which no search used, it made INR 98,166 after costs on 18 trades and beat only '
    '80% of random-entry runs; the evidence of an edge outside the searched years is weak.',
]


def apply_profile(cfg=None):
    return replace(_r4_profile(cfg), short_strike_otm_points=SHORT_STRIKE_OTM_POINTS)


def create_engine(cfg, calendar, **kwargs):
    import sys
    from strategy.registry import create_named_engine
    return create_named_engine(sys.modules[__name__], cfg, calendar, **kwargs)
