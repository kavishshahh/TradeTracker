# Strategy05: zen_strategy_01 (Geometric credit) with drawdown-capped risk rules (research, 21 Oct 2026).
#
# Same signal, strikes, hedge, expiry rules, targets and scheduled exits as zen_strategy_01
# (imported, not copied). Risk rules added to keep the realised drawdown within 25% of capital, chosen
# on the three-year replay (4 Oct 2023 - 30 Sep 2026) with backtest.zen_improve:
# * stop at credit + 35 points (zen_strategy_01: + 45);
# * lots capped so one stop-loss exit loses at most 2.5% of model capital;
# * after a stop, no new entries for the rest of that session and the next session.
# Neighbourhood (stop 30-40, cap 2.5-3.5%, one-session cooldown): every year positive, drawdown
# 17-33%; a two-session cooldown is clearly worse, so the cooldown length is the fragile part.
# The Zen formula was chosen on Jul 2025 - Oct 2026; these risk rules were chosen on all three years.
from dataclasses import replace

from strategy.zen_strategy_01_geometric_credit import *  # noqa: F401,F403  (signal, panel and constants)
from strategy.zen_strategy_01_geometric_credit import apply_profile as _base_profile
from strategy import zen_strategy_01_geometric_credit as _base

STRATEGY_NAME = 'zen_strategy_05'
DESCRIPTION = ('zen_strategy_01 signal with a credit + 35 stop, lots capped at a 2.5% loss per stop and a '
               'one-session pause after every stop.')
PROFIT_TARGET_ENABLED = getattr(_base, 'PROFIT_TARGET_ENABLED', True)
STOP_POINTS = 35.0
MAX_LOSS_FRACTION = 0.025
STOP_COOLDOWN_SESSIONS = 1


def apply_profile(cfg=None):
    base = _base_profile(cfg)
    normal_points = base.margin_to_width_ratio * base.spread_distance   # normal margin per lot / lot size
    return replace(base, stop_loss_margin_fraction=STOP_POINTS / normal_points,
                   max_loss_fraction=MAX_LOSS_FRACTION, stop_cooldown_sessions=STOP_COOLDOWN_SESSIONS)


def create_engine(cfg, calendar, **kwargs):
    import sys
    from strategy.registry import create_named_engine
    return create_named_engine(sys.modules[__name__], cfg, calendar, **kwargs)
