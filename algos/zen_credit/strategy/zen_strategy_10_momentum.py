# Strategy10: 45-minute price momentum credit spreads, entered from 11:45 (Zen Momentum Afternoon, listed for
# paper trading on 20 Nov 2026).
#
# Found with backtest.zen_variants: about 2,500 variants around zen_strategy_01/02 on the minute dataset of
# 4 Oct 2023 - 19 Nov 2026, ranked on entries before 1 Oct 2026 and checked afterwards on 1 Oct - 19 Nov 2026,
# the seven weeks in which zen_strategy_01/02/05/06 all lost money.
#
# RULES
# Completed NIFTY one-minute candle t: x = (close[t] - open[t-45]) / open[t-45]. alpha = trailing 800-candle
# average percentile rank of x, requiring all 800 values. There is no option-volume or option-volatility term
# (zen_strategy_01/02's second rank): the search found the price rank alone, at a longer horizon and a
# stricter threshold, steadier than either Zen formula, and it does not depend on live volume matching the
# historical candles.
# Flat, 11:45-14:15 IST: alpha > 0.9 -> credit PUT spread; alpha < 0.1 -> credit CALL spread. Strikes, hedge
# (400 points), premium limit (short leg <= 200), sizing and the scheduled next-trading-day exit are
# zen_strategy_01's (imported). Stop: entry credit + 45 points. No profit target. Lots are capped so one
# stop loses at most 2.5% of model capital.
#
# WHAT THE SEARCH SHOWED (harness, gross, INR 320,000 fixed capital)
# Entries before 1 Oct 2026: 374 trades, +765,127, drawdown 20.2%, 59% winners, profit factor 1.71, every
# year positive; +611,917 after 2 points of costs per unit and INR 130 a trade. 1 Oct - 19 Nov 2026: 16
# trades, +38,857. Neighbours (horizon 40-50, threshold 0.88-0.92, start 11:30-12:00, stop 35-60, cap 2-4%)
# stay profitable in every year and in the test period, with drawdowns of 11-36% depending on the cap.
# Engine replay, 4 Oct 2023 - 19 Nov 2026 (reports/zen_strategy_10_2023-10-04_2026-11-19): 389 trades,
# +797,777, CAGR 49.1%, drawdown 20.2%, 59.1% winners, profit factor 1.71, 7 losing months of 38; after 2
# points of costs CAGR 42.0% and drawdown 23.5%, after 4.6 points 35.0% and 27.5%.
# Weak points: an 800-candle rank is clearly better than 400 or 1600; call spreads earned nearly all of the
# in-sample profit while put spreads earned the test-period profit; and the 11:45 start and the loss cap
# were kept after the test period had been seen for other variants, so it is not a clean hold-out.
from dataclasses import replace
from datetime import time

import pandas as pd

from strategy import zen_strategy_01_geometric_credit as first
from strategy.zen_strategy_01_geometric_credit import panel_from_options, panel_from_snapshots  # noqa: F401

STRATEGY_NAME = 'zen_strategy_10'
DESCRIPTION = ('45-minute price-change rank (800 candles) above 0.9 / below 0.1, entries 11:45-14:15, credit + 45 '
               'stop, no target, next-day exit, lots capped at a 2.5% loss per stop.')
PROFIT_TARGET_ENABLED = False
HORIZON_MINUTES = 45
RANK_WINDOW = 800
BULLISH_RANK, BEARISH_RANK = 0.9, 0.1
SIGNAL_START = time(11, 45)
MAX_LOSS_FRACTION = 0.025


def apply_profile(cfg=None):
    return replace(first.apply_profile(cfg), price_change_horizon_minutes=HORIZON_MINUTES,
                   alpha_lookback_minutes=RANK_WINDOW, bullish_threshold=BULLISH_RANK, bearish_threshold=BEARISH_RANK,
                   signal_start=SIGNAL_START, max_loss_fraction=MAX_LOSS_FRACTION)


def calculate_indicators(bars, panel=None):
    """Completed start-indexed bars -> decision-indexed rank. alpha2 repeats alpha: the engine asks both
    ranks to cross the threshold and this strategy has only one. The option panel is not used."""
    bars = first._bars(bars)
    clock = bars.index + pd.Timedelta(minutes=1)
    base = bars.open.shift(HORIZON_MINUTES)
    change = (bars.close - base) / base
    change.index = clock
    alpha = change.rolling(RANK_WINDOW, min_periods=RANK_WINDOW).rank(method='average', pct=True)
    return pd.DataFrame({'alpha': alpha, 'alpha2': alpha, 'price_change': change}, index=clock)


def create_engine(cfg, calendar, **kwargs):
    import sys
    from strategy.registry import create_named_engine
    return create_named_engine(sys.modules[__name__], cfg, calendar, **kwargs)
