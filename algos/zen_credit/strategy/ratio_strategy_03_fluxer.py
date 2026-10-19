# Strategy03: Ratio-Fluxer style expiry credit spreads (IV-skew reversal).
#
# ORIGIN
# ------
# A structural replica of Stratzy's "Ratio-Fluxer Credit Spread Expiry" Dhan
# algo, fitted to its 19 published trades (23 Oct 2025 to 6 Oct 2026). The
# provider's entry formula is private; what follows is the simplest rule that
# reproduces the published trade structure and the IV-surface state observed at
# every published entry. It is NOT the provider's code and is not claimed to
# match its future trades minute for minute.
#
# WHAT THE PUBLISHED TRADES ESTABLISH
# -----------------------------------
# * Nearest weekly NIFTY expiry only. Entries 10:16-14:38 IST; never on the
#   expiry date; never with more than five days to expiry (no Wednesday entry).
# * Short strike = ATM strike of the last completed one-minute candle (open:
#   12/13 checked trades; close: 11/13). Hedge 400 points further OTM (300 in
#   the 2025 backtest rows, 400 in every 2026 trade). Published fills sit within
#   about two points of the candle closes around the entry minute.
# * Direction: 15 credit CALL spreads, 4 credit PUT spreads. At every entry the
#   100-point OTM put IV minus 100-point OTM call IV ("skew") was at an extreme
#   of its trailing 800-minute rank: call spreads when the skew was unusually
#   low or negative (calls rich), put spreads when the skew was unusually high
#   (puts rich). The sold side is always the relatively expensive side. Three of
#   the four put entries had a raw skew of 4.5-5.0 IV points, the fourth 2.5.
# * Exits: five targets at exactly 50% of the entry credit (0.497-0.512), every
#   one on the entry day; two stops at roughly credit + 40 to 45 points (5% of
#   margin per lot); every position carried overnight ran to the scheduled
#   14:57 IST exit on the expiry day (14:59 in the 2025 rows). On Dhan minute
#   closes the published strikes of 11 of those 12 overnight winners traded
#   below 50% of the credit on a later day for 47-603 minutes (9 Dec 2025 09:16
#   at 0.1 against a 46-point target, 17 Aug 2026 at 4.5 against 67, 8 Sep 2026
#   at 10 against 42) and were still held: the target is live on the entry day
#   only, afterwards only the stop and the scheduled exit apply.
# * Sizing: INR 320,000 maximum capital, 80% on Mondays (every Monday trade
#   from March 2026), 4 lots at 80% and 5 lots at 100% with a 65-unit lot,
#   i.e. floor(capital / margin) with margin per lot between 53,300 and 64,000.
#
# RULES (pinned here; capital and margin stay deployment settings)
# ---------------------------------------------------------------
# Decision minute t uses the completed candle [t-1, t). Panel (near expiry):
#   spot            = candle close; ATM = floor((close + 25 - 1e-8) / 50) * 50
#   iv(side, k)     = own Black-Scholes IV of the candle-close price of strike
#                     ATM + k*50 for that side, underlying = index spot, flat
#                     rate RISK_FREE_RATE, time to 15:30 IST on the expiry date.
#                     Spot (not the futures price) is deliberate: the vendor IV
#                     the published entries line up with is spot based, so the
#                     futures basis is part of the signal. With a parity-implied
#                     forward instead, the entries show no skew extreme at all.
#   skew            = iv(PE, -2) - iv(CE, +2)          (100-point wings)
#   skew_s          = session-local exponential mean of skew, span SMOOTH_WINDOW
#                     (weight 2 / (SMOOTH_WINDOW + 1) on the newest minute),
#                     seeded at the session's first known skew; unknown for the
#                     first SMOOTH_WINDOW-1 minutes of the session and at any
#                     minute whose own skew is unknown (ema_smooth below)
# Indicators:
#   alpha  = trailing 800-observation percentile rank of skew_s (min 720 valid)
#   gate   = skew_s <= SKEW_CALL_MAX (calls rich) or skew_s >= SKEW_PUT_MIN (puts rich)
#   alpha2 = alpha where the gate holds, otherwise 0.5 (neutral); also neutral on
#            Saturday/Sunday special sessions (the provider never traded one)
# Signal (10:15-14:15 IST, flat, nearest expiry 1-5 days away):
#   credit CALL spread when alpha < BEARISH_RANK and alpha2 < BEARISH_RANK
#   credit PUT  spread when alpha > BULLISH_RANK and alpha2 > BULLISH_RANK
# Exits: 50% of the entry credit on the ENTRY DAY ONLY (target_entry_day_only),
#   stop at 5% of normal margin per lot, 14:57 IST on the expiry day.
# Fit (18 published entries in the 1 Oct 2025 - 30 Sep 2026 replay window,
# backtest/ratio_research.py, reports/ratio_research/round2_candidates.csv):
#   round 1: the unsmoothed gate at -2.0/4.5 reproduced 17/18 published entries
#   but added 25 extra trades with 11 stops; a 15-minute simple mean with
#   -3.0/5.0 gave 19 trades, 18 winners, 1 stop, 13/18 published entries on the
#   same day and side, but 15 of its 19 exits were targets against 5 of 18
#   published, and three trades (27 Oct 2025, 17 Aug and 31 Aug 2026, the last
#   the stop) were re-entries after next-morning target exits.
#   round 2: with the target restricted to the entry day, every smoothing/gate
#   variant loses its re-entries and stops (sma15 -3.0/5.0: 15 trades, 3 extra,
#   0 stops, exits 2 target / 5 scheduled / 8 settled). The exponential span-10
#   mean with -3.0/4.5 then matches 14/18 published entries (the 23 Oct and
#   27 Oct 2025, 18 May 2026 entries return) with 5 extra trades, 1 stop,
#   19 trades, 18 winners, INR 545,680 against the published INR 397k; mean
#   absolute P&L gap on matched trades 5,199 (round 1: 8,448). Neighbours
#   (spans 8-12, simple means 8-10, put gate 4.5-5.0) score 13-14 matched,
#   4-6 extra, 0-1 stops; a -2.5 call gate adds 7-12 extras with 2-4 stops and
#   -3.5 drops to 8-11 matched. Pre-window Jul-Sep 2025: 2 trades, 2 winners.
#   Still unmatched: 17 Nov 2025 and 10 Aug 2026 (smoothed skew about -2.0),
#   22 Dec 2025 (2.5) and the provider's losing 9 Mar 2026 call spread (0.6).
#   Asymmetric/hysteresis gates, candle means, 375/1125/1600-minute ranks,
#   basis-sign confirmation and first-cross entry were tested and rejected
#   (round2_candidates.csv): basis sign and hysteresis change nothing, the
#   others trade matches for extras.
"""Named Ratio-Fluxer style IV-skew credit spread implementation."""
from __future__ import annotations

from dataclasses import replace
from datetime import date, time

import numpy as np
import pandas as pd

from config import StrategyConfig
from strategy.implied_vol import implied_vol, years_to_expiry
from utils.time import IST

STRATEGY_NAME = 'ratio_strategy_03'
DESCRIPTION = 'Ratio-Fluxer style expiry credit spread; opening ATM, EMA-10 smoothed 100-point IV skew rank 800, 50% credit target on the entry day only.'
PROFIT_TARGET_ENABLED = True
LIMITATIONS = [
    'ratio_strategy_03 is a structural replica fitted to 19 published Ratio-Fluxer trades; the provider trigger is private, and the smoothed-skew gate was tuned on those trades (14/18 same-day matches, about one extra trade in four).',
    'Skew uses own spot-based Black-Scholes IV (6.5% rate) of candle closes at ATM +/-100, smoothed with a session-local exponential mean (span 10); a missing wing candle leaves the minute unknown and no trade is forced. Saturday/Sunday special sessions never enter.',
    'Minute-close execution: bid/ask, intraminute stop/target touches and exact fills are unavailable; the 50% credit target (entry day only, as the published overnight trades show) and the margin stop are checked once per minute.',
    'Estimated margin (2.25 x width x lot size) sizes positions and sets the stop; it is not historical broker margin or forced liquidation.',
    'Scheduled exit is 14:57 IST on the expiry day; published 2025 rows exited at 14:59 and used 300-point hedges, which this replay does not reproduce.',
    'Missing option candles remain unknown and can postpone exits or suppress entries; costs are excluded unless modeled explicitly.',
    'Statistics use realized closed trades on fixed capital; open MTM is separate; CAGR is an annualized ending-value calculation.',
]
PANEL_COLUMNS = ('spot', 'reference_open', 'expiry', 'atm_strike', 'years_to_expiry',
                 'iv_ce_atm', 'iv_pe_atm', 'iv_ce_up', 'iv_pe_down', 'skew')

RANK_WINDOW = 800
RANK_MIN_PERIODS = 720
WING_STEPS = 2                 # 2 x 50 = 100 points each side
RISK_FREE_RATE = 0.065         # flat continuous rate for the spot-based Black-Scholes IV
SMOOTH_WINDOW = 10             # span of the session-local exponential mean of the skew, in minutes
SKEW_CALL_MAX = -3.0           # IV points (smoothed): calls richer than puts -> credit call spread
SKEW_PUT_MIN = 4.5             # IV points (smoothed): puts much richer than calls -> credit put spread
TARGET_ENTRY_DAY_ONLY = True   # the 50% credit target is live on the entry date only
BULLISH_RANK = 0.8
BEARISH_RANK = 0.2
STRIKE_STEP = 50.0


def apply_profile(cfg: StrategyConfig | None = None) -> StrategyConfig:
    """Freeze the signal and execution rules; keep configured capital/margin."""
    return replace(cfg or StrategyConfig(), alpha_lookback_minutes=RANK_WINDOW, alpha2_lookback_minutes=RANK_WINDOW,
                   bullish_threshold=BULLISH_RANK, bearish_threshold=BEARISH_RANK,
                   signal_start=time(10, 15), signal_end=time(14, 15), spread_distance=400,
                   strike_reference='last_bar_open', max_short_premium=None,
                   stop_loss_margin_fraction=.05, target_spread_value=10., target_credit_fraction=.5,
                   target_entry_day_only=TARGET_ENTRY_DAY_ONLY,
                   time_exit=time(14, 57), time_exit_on_expiry=True, max_days_to_expiry=5,
                   allow_expiry_day_entry=False, historical_time_exit_start=None, historical_time_exit_end=None,
                   monday_capital_fraction=.8, monday_allocation_start=date(2026, 4, 6),
                   market_open=time(9, 15), market_close=time(15, 30), underlying='NIFTY')


def _bars(bars):
    if not isinstance(bars.index, pd.DatetimeIndex) or bars.index.tz is None:
        raise ValueError('Completed bars need a timezone-aware start-minute clock')
    if bars.index.has_duplicates or not bars.index.is_monotonic_increasing:
        raise ValueError('Completed bars must be unique and chronological')
    if not bars.index.equals(bars.index.floor('min')):
        raise ValueError('Completed bar starts must align to minutes')
    result = bars[['open', 'close']].apply(pd.to_numeric, errors='coerce').copy()
    result.index = result.index.tz_convert(IST)
    return result


def atm_strike(spot) -> np.ndarray:
    """Nearest 50-point strike; an exact half-strike tie resolves down."""
    return np.floor((np.asarray(spot, dtype=float) + STRIKE_STEP / 2 - 1e-8) / STRIKE_STEP) * STRIKE_STEP


def ema_smooth(values: pd.Series, sessions, span: int = SMOOTH_WINDOW) -> pd.Series:
    """Session-local exponential mean, weight 2 / (span + 1) on the newest value.

    Each session restarts from its first known value; a value is unknown for the
    first ``span - 1`` minutes of the session and wherever the input is unknown
    (the state is carried across the gap, not updated). Causal by construction.
    """
    x = pd.to_numeric(values, errors='coerce').to_numpy(dtype=float)
    sessions = np.asarray(sessions)
    weight = 2.0 / (span + 1)
    out = np.full(len(x), np.nan)
    state, count, prev = np.nan, 0, None
    for i in range(len(x)):
        if sessions[i] != prev:
            state, count, prev = np.nan, 0, sessions[i]
        count += 1
        if np.isfinite(x[i]):
            state = x[i] if not np.isfinite(state) else state + weight * (x[i] - state)
            if count >= span:
                out[i] = state
    return pd.Series(out, index=values.index)


def calculate_indicators(bars: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    """Completed start-indexed bars + decision-indexed near panel -> alpha/alpha2 frame."""
    bars = _bars(bars); clock = bars.index + pd.Timedelta(minutes=1)
    if not isinstance(panel.index, pd.DatetimeIndex) or panel.index.tz is None:
        raise ValueError('Option panel needs a timezone-aware decision clock')
    if panel.index.has_duplicates or not panel.index.is_monotonic_increasing:
        raise ValueError('Option panel must be unique and chronological')
    selected = panel.copy(); selected.index = selected.index.tz_convert(IST); selected = selected.reindex(clock)
    skew = pd.to_numeric(selected['skew'], errors='coerce')
    atm_iv = pd.to_numeric(selected['iv_ce_atm'], errors='coerce')
    # Session-local smoothing: the mean never spans the overnight gap, and a
    # missing minute leaves that minute's smoothed value unknown.
    skew_s = ema_smooth(skew, clock.date, SMOOTH_WINDOW)
    alpha = skew_s.rolling(RANK_WINDOW, min_periods=RANK_MIN_PERIODS).rank(method='average', pct=True)
    weekend = np.array([d.weekday() >= 5 for d in clock.date])
    gate = ((skew_s <= SKEW_CALL_MAX) | (skew_s >= SKEW_PUT_MIN)) & ~weekend
    alpha2 = pd.Series(np.where(gate & alpha.notna(), alpha, 0.5), index=clock)
    alpha2 = alpha2.where(alpha.notna())        # unknown alpha stays unknown
    return pd.DataFrame({'alpha': alpha, 'alpha2': alpha2, 'skew': skew, 'skew_smooth': skew_s,
                         'atm_iv': atm_iv, 'gate': gate.astype(float)}, index=clock)


def _near_expiries(clock, resolver, quotes):
    if resolver is not None:
        mapping = {day: sorted(resolver(day)) for day in set(clock.date)}
        return [mapping[minute.date()][0] if mapping[minute.date()] else None for minute in clock]
    observed = {minute: sorted({expiry for expiry in frame.index.get_level_values('expiry') if expiry >= minute.date()})
                for minute, frame in quotes.groupby(level='minute', sort=False)}
    return [observed.get(minute, [None])[0] if observed.get(minute) else None for minute in clock]


def _panel(bars, quotes, resolver):
    bars = _bars(bars); clock = bars.index + pd.Timedelta(minutes=1)
    if not isinstance(quotes.index, pd.MultiIndex) or quotes.index.names != ['minute', 'expiry', 'strike']:
        raise ValueError('Quotes need exact minute/expiry/strike MultiIndex')
    if quotes.index.has_duplicates:
        raise ValueError('Duplicate exact option quote keys')
    quotes = quotes.copy()
    minutes = pd.DatetimeIndex(quotes.index.get_level_values('minute'))
    if minutes.tz is None:
        raise ValueError('Option quote minutes must be timezone aware')
    quotes.index = pd.MultiIndex.from_arrays([minutes.tz_convert(IST),
        pd.to_datetime(quotes.index.get_level_values('expiry')).date,
        pd.to_numeric(quotes.index.get_level_values('strike'))], names=quotes.index.names)
    expiry = _near_expiries(clock, resolver, quotes)
    spot = bars.close.to_numpy(dtype=float)
    atm = atm_strike(spot)
    tyrs = years_to_expiry(clock, expiry)
    result = pd.DataFrame({'spot': spot, 'reference_open': bars.open.to_numpy(), 'expiry': expiry,
                           'atm_strike': atm, 'years_to_expiry': tyrs}, index=clock)

    def price(strike, side):
        keys = pd.MultiIndex.from_arrays([clock, expiry, strike], names=quotes.index.names)
        return pd.to_numeric(quotes.reindex(keys)[f'{side}_ltp'], errors='coerce').to_numpy(dtype=float)

    up = atm + WING_STEPS * STRIKE_STEP
    down = atm - WING_STEPS * STRIKE_STEP
    result['iv_ce_atm'] = implied_vol(price(atm, 'ce'), spot, atm, tyrs, True, rate=RISK_FREE_RATE)
    result['iv_pe_atm'] = implied_vol(price(atm, 'pe'), spot, atm, tyrs, False, rate=RISK_FREE_RATE)
    result['iv_ce_up'] = implied_vol(price(up, 'ce'), spot, up, tyrs, True, rate=RISK_FREE_RATE)
    result['iv_pe_down'] = implied_vol(price(down, 'pe'), spot, down, tyrs, False, rate=RISK_FREE_RATE)
    result['skew'] = result['iv_pe_down'] - result['iv_ce_up']
    return result[list(PANEL_COLUMNS)]


def panel_from_options(bars: pd.DataFrame, options: pd.DataFrame, expiries_for) -> pd.DataFrame:
    """Historical candle closes keyed (minute, expiry, strike) with ce_ltp/pe_ltp."""
    return _panel(bars, options, expiries_for)


def panel_from_snapshots(bars: pd.DataFrame, snapshots: pd.DataFrame, expiries_for=None) -> pd.DataFrame:
    """Observed live chain snapshots (LTP) for the nearest expiry of each decision date."""
    if snapshots is None or snapshots.empty:
        empty = pd.DataFrame(index=pd.MultiIndex.from_arrays([pd.DatetimeIndex([], tz=IST), [], []],
                             names=['minute', 'expiry', 'strike']), columns=['ce_ltp', 'pe_ltp'], dtype=float)
        return _panel(bars, empty, expiries_for)
    quotes = snapshots.copy()
    quotes['minute'] = pd.to_datetime(quotes.minute, utc=True).dt.tz_convert(IST)
    quotes = quotes.drop_duplicates(['minute', 'expiry', 'strike'], keep='last')
    return _panel(bars, quotes.set_index(['minute', 'expiry', 'strike'])[['ce_ltp', 'pe_ltp']], expiries_for)


def create_engine(cfg, calendar, **kwargs):
    """Shared execution engine, with named calculation and entry identity."""
    import sys
    from strategy.registry import create_named_engine
    return create_named_engine(sys.modules[__name__], cfg, calendar, **kwargs)
