# zen_strategy_11 "Momentum Expiry Puts": buys one at-the-money NIFTY put near the weekly expiry when the index has
# been falling for three hours, the last five minutes have not extended the fall, and option volatility is at the top
# of its recent range.  The first option-BUYING strategy in this package (a "long_option" position, see
# strategy.engine.Position.structure); everything else here sells credit spreads.
#
# ORIGIN (26 Nov 2026)
# Built while reverse engineering a marketplace option-buying algo from its 67 published trades. The trade rules are
# recovered from those trades (ATM option of the nearest expiry, about 15% of capital in premium, stop at -25%,
# target at +75%, out at 15:10, at most two trades a day, expiry day / the day before / the Friday before). The entry
# rule is NOT the provider's: no rule matched its entries (best 23 of 66). This one is variant 3157 of a 5,000-variant
# search (algos/reports/girsanov_research/girsanov_variants.py), chosen because it came closest to the provider's
# published-year statistics while staying profitable on the four earlier years.
#
# RULES (decision on the last completed one-minute candle, fill at the current ask/ltp)
#   days     expiry day or the day before (calendar days to the nearest expiry <= 1), or a Friday with the expiry
#            at most 4 days away
#   window   09:45 - 13:35;  at most 2 trades a day;  one position at a time
#   signal   180-minute index change <= -0.10%  and  5-minute change >= -0.05%  and
#            ATM implied volatility (mean of call and put) ranked >= 0.95 within its last 375 minutes  and
#            ATM put IV <= ATM call IV
#   trade    buy the ATM put (nearest 50-point strike), lots = floor(7.5% of capital / (premium x lot size))
#   exits    option at 80% of the entry price (stop), at 300% (target), else 15:10 the same day
#
# HISTORY
#   Listed 26 Nov 2026 with the provider's trade rules (15% premium, stop -25%, target +75%): on INR 3.2 lakh its
#   five-year drawdown was 37-38%, above the 25% listing rule.  The same day an improvement round
#   (algos/reports/girsanov_research/zen11_improve.py, round 1, variant 184) changed only sizing and exits to the
#   current ones.  Ranked on 26 Jan 2022 - 31 Dec 2024 and checked on 1 Jan 2025 - 19 Nov 2026, after brokerage,
#   taxes and 1% slippage each way: 32.3% a year (drawdown 20.7%) and 23.4% a year (drawdown 17.4%); five years
#   23.5% a year, drawdown 20.7%, no losing calendar year.  21 of 721 sizing/exit variants passed the same rules;
#   nearly all share the 20% stop, the +200% target and a 5-10% premium.
from __future__ import annotations

import hashlib
import math
from dataclasses import replace
from datetime import datetime, time

import numpy as np
import pandas as pd

from config import StrategyConfig
from strategy.engine import EngineResult, Position, StrategyEngine, _f
from strategy.implied_vol import implied_vol, years_to_expiry
from strategy.ratio_strategy_03_fluxer import RISK_FREE_RATE, atm_strike
from strategy.spreads import select_expiry
from utils.time import IST, minute_bucket, round_price, to_ist

STRATEGY_NAME = 'zen_strategy_11'
DESCRIPTION = ('Buys the ATM put near weekly expiry after a 3-hour fall with a stalled last 5 minutes and option '
               'volatility at the top of its 375-minute range; stop -20%, target +200%, out 15:10.')
STRUCTURE = 'long_option'
TREND_MINUTES, TREND_CHANGE = 180, -0.001
PAUSE_MINUTES, PAUSE_FLOOR = 5, -0.0005
IV_RANK_WINDOW, IV_RANK_MIN_PERIODS, IV_RANK_MIN = 375, 300, 0.95
PREMIUM_FRACTION, STOP_FRACTION, TARGET_FRACTION = 0.075, 0.20, 2.0
SIGNAL_START, SIGNAL_END, EXIT_TIME = time(9, 45), time(13, 35), time(15, 10)
MAX_ENTRIES_PER_DAY = 2
MAX_DAYS_TO_EXPIRY, FRIDAY_MAX_DAYS = 1, 4


def apply_profile(cfg=None):
    return replace(cfg or StrategyConfig(), signal_start=SIGNAL_START, signal_end=SIGNAL_END,
                   max_entries_per_day=MAX_ENTRIES_PER_DAY, stop_cooldown_sessions=0, target_entry_day_only=False)


def eligible_day(day, expiry) -> bool:
    days = (expiry - day).days
    return 0 <= days <= MAX_DAYS_TO_EXPIRY or (day.weekday() == 4 and days <= FRIDAY_MAX_DAYS)


def atm_iv_frame(snapshots: pd.DataFrame) -> pd.DataFrame:
    """Per minute: ATM call and put implied volatility (percent) of that minute's nearest expiry, from stored chain rows."""
    if snapshots is None or snapshots.empty:
        return pd.DataFrame(columns=['ce_iv', 'pe_iv'])
    q = snapshots[['minute', 'expiry', 'strike', 'spot', 'ce_ltp', 'pe_ltp']].copy()
    q['minute'] = pd.to_datetime(q.minute, utc=True).dt.tz_convert(IST)
    q['expiry'] = pd.to_datetime(q.expiry.astype(str)).dt.date
    q = q[q.expiry >= q.minute.dt.date]
    q = q[q.expiry == q.groupby('minute').expiry.transform('min')]
    spot = q.groupby('minute').spot.transform('first').astype(float)
    q = q[q.strike.astype(float) == atm_strike(spot.to_numpy())]
    q = q.drop_duplicates('minute').sort_values('minute')
    if q.empty:
        return pd.DataFrame(columns=['ce_iv', 'pe_iv'])
    t = years_to_expiry(pd.DatetimeIndex(q.minute), list(q.expiry))
    s, k = q.spot.astype(float).to_numpy(), q.strike.astype(float).to_numpy()
    ce = implied_vol(q.ce_ltp.astype(float).to_numpy(), s, k, t, True, rate=RISK_FREE_RATE)
    pe = implied_vol(q.pe_ltp.astype(float).to_numpy(), s, k, t, False, rate=RISK_FREE_RATE)
    return pd.DataFrame({'ce_iv': ce, 'pe_iv': pe}, index=pd.DatetimeIndex(q.minute))


def signal_inputs(bars: pd.DataFrame, iv: pd.DataFrame, minute) -> dict:
    """Inputs at decision ``minute`` (bars are start-indexed; the last completed bar started one minute earlier)."""
    out = dict(trend=float('nan'), pause=float('nan'), iv_rank=float('nan'), put_minus_call_iv=float('nan'))
    if bars is not None and len(bars) > TREND_MINUTES:
        close = bars['close'].astype(float)
        last = close.iloc[-1]
        out['trend'] = last / close.iloc[-1 - TREND_MINUTES] - 1
        out['pause'] = last / close.iloc[-1 - PAUSE_MINUTES] - 1
    if iv is not None and len(iv):
        iv = iv[iv.index <= minute]
        mean = ((iv.ce_iv + iv.pe_iv) / 2).dropna().tail(IV_RANK_WINDOW)
        if len(mean) >= IV_RANK_MIN_PERIODS:
            out['iv_rank'] = float(mean.rank(pct=True).iloc[-1])
        last = iv.dropna().tail(1)
        if len(last):
            out['put_minus_call_iv'] = float(last.pe_iv.iloc[0] - last.ce_iv.iloc[0])
    return out


def bearish(inputs: dict) -> bool:
    v = inputs
    return all(math.isfinite(v[k]) for k in v) and v['trend'] <= TREND_CHANGE and v['pause'] >= PAUSE_FLOOR \
        and v['iv_rank'] >= IV_RANK_MIN and v['put_minus_call_iv'] <= 0.0


def calculate_indicators(bars, panel=None):
    raise NotImplementedError('zen_strategy_11 reads its volatility inputs from the live chain history; '
                              'historical replays use algos/reports/girsanov_research/girsanov_sim.py')


class ExpiryPutEngine(StrategyEngine):
    strategy_name = STRATEGY_NAME

    def spread_value(self, chain, pos):
        if pos.structure != STRUCTURE:
            return super().spread_value(chain, pos)
        self._carried_hedge = None
        self._leg_prices = None
        if chain is None or chain.expiry != pos.expiry:
            return None
        b = self._leg_price(chain, pos.buy_strike, pos.option_type, 'SELL')
        if b is None:
            return None
        self._leg_prices = (0.0, b)
        return round_price(-b)

    def _evaluate_entry(self, view, now):
        if not self.calendar.is_trading_day(now.date()):
            return EngineResult('none', 'not a trading day')
        if not (self.cfg.signal_start <= now.time() <= self.cfg.signal_end):
            return EngineResult('none', 'outside signal window')
        exits_today, _ = (self.day_exits or {}).get(now.date(), (0, None))
        if exits_today >= MAX_ENTRIES_PER_DAY:
            return EngineResult('none', f'{exits_today} trades already today (limit {MAX_ENTRIES_PER_DAY})')
        problems = self.data_problems(view)
        if problems:
            return EngineResult('none', 'data: ' + '; '.join(problems))
        expiry = select_expiry(now.date(), view.expiries)
        if not eligible_day(now.date(), expiry):
            return EngineResult('none', f'not an entry day ({(expiry - now.date()).days} days to expiry)')
        minute = minute_bucket(now)
        inputs = signal_inputs(view.spot_bars, atm_iv_frame(view.snapshots), minute)
        diag = {k: _f(v) for k, v in inputs.items()}
        if not bearish(inputs):
            return EngineResult('none', 'no signal', diagnostics=diag)
        spot_ref = float(view.spot_bars['close'].iloc[-1])
        strike = float(atm_strike(spot_ref))
        if view.chain is None or view.chain.expiry != expiry:
            return EngineResult('none', 'no chain for the nearest expiry', diagnostics=diag)
        px = self._leg_price(view.chain, strike, 'PE', 'BUY')
        if px is None or px <= 0:
            return EngineResult('none', 'no put quote', diagnostics=diag)
        capital = float(self.cfg.capital)
        lots = int(capital * PREMIUM_FRACTION // (px * view.lot_size))
        if lots < 1:
            return EngineResult('none', 'premium above the per-trade budget', diagnostics=diag)
        units = lots * view.lot_size
        key = f'{STRATEGY_NAME}|{minute.isoformat()}|{expiry.isoformat()}|{strike:.0f}|PE'
        exit_due = datetime.combine(now.date(), EXIT_TIME, tzinfo=IST)
        pos = Position(
            signal_id=hashlib.sha256(key.encode()).hexdigest()[:20], entry_ts=now, expiry=expiry, option_type='PE',
            sell_strike=strike, buy_strike=strike, lots=lots, lot_size=view.lot_size, units=units,
            sell_price=0.0, buy_price=px, net_credit=round_price(-px),
            stop_loss=round_price(-px * (1 - STOP_FRACTION)), target=round_price(-px * (1 + TARGET_FRACTION)),
            max_loss=round(px * units, 2), max_profit=None, exit_due=exit_due, spot_at_entry=view.chain.spot,
            alpha=_f(inputs['trend']), alpha2=_f(inputs['iv_rank']), allocated_capital=capital, structure=STRUCTURE)
        diag.update(strike=strike, premium=px, lots=lots)
        return EngineResult('entry', 'BEARISH', position=pos, diagnostics=diag)


def create_engine(cfg, calendar, **kwargs):
    return ExpiryPutEngine(apply_profile(cfg), calendar, **kwargs)
