# Strategy01: causal geometric-volume credit spreads, candidate732629f0bd6093de.
#
# RULES (a named research candidate, NOT a recovered Zen Credit replica)
# -----------------------------------------------------------------
# Completed NIFTY one-minute candle t: x=(close[t]-open[t-5])/open[t-5].
# alpha=trailing800 average percentile rank, requiring800 known x values.
# Each decision t+1 selects nearest-expiry ATM from completed candle OPEN:
# floor((open+25-1e-8)/50)*50. Missing that strike stays unknown; never choose
# another surviving quote. Contract identity includes expiry, strike and side.
# Historical volume is native one-minute CE/PE candle volume. Live volume is
# nonnegative SAME-contract cumulative-volume difference between exact adjacent
# same-session snapshots. No overnight/gap return, cumulative reset substitution,
# zero filling, future close, or published source trade feeds the calculation.
# Frozen historical formula retains recorded native volume values, including12
# negative cached observations in the reference panel; these feed anomalies are
# not repaired. The geometric product may become unknown. Live negative cumulative
# deltas remain unknown rather than being interpreted as traded volume.
# Each side ratio=current native volume / trailing10 mean (minimum8 known).
# Multiplier=sqrt(CEratio*PEratio). Volatility=sum of CE and PE sample STD(ddof1)
# of log1p(same-contract one-minute returns), trailing150, minimum120 known.
# Both multiplier and volatility shift5 on the CONTINUOUS selected near-ATM path,
# including across nearest-expiry rolls. beta=rank300(x*laggedmultiplier/
# laggedvolatility), requiring270 valid values. Ranks use average ties.
#
# Flat and10:15--14:15 IST inclusive: both ranks>.8 -> credit PUT; both<.2 ->
# credit CALL. Sell opening ATM, buy PUT400 lower or CALL400 higher, same near
# expiry. Short premium must be<=200 and spread credit positive. One position;
# one evaluation per minute; exits checked before entries, no same-cycle reentry.
# Sizing: fixed capital(defaultINR320000), full allocation except80% Monday
# from2026-04-06. Estimated normal margin=2.25*400*lot_size unless overridden;
# expiry-day entry margin=normal*1.54. Lots=floor(allocatedcapital/entrymargin).
# No hypothetical broker RMS liquidation is manufactured. Existing-position
# expiry-margin changes are not a reconstructed broker liquidation model.
# Stop=entrycredit+5% normalmargin/lot_size; target=netspread<=10. Priority:
# stop, target, scheduled next-trading-day exit capped at expiry; expired-position
# safety/official settlement follows the shared engine. Scheduled time15:00 for
# entries2025-07-09 through2026-06-30 inclusive; otherwise14:53. No reversal exit.
# Capital and margin overrides remain user supplied; changing them changes results.
#
# VERIFIED REFERENCE BACKTEST,2025-07-09--2026-10-01 (450 inclusive dates)
# --------------------------------------------------------------------
# Source: reports/provider_research/replication_trials/bulk/
# full_autonomous_732629f0bd6093de_ledger/{report.json,performance.json}.
# Gross realized fixed-INR320000 basis;254 closed trades,147 winners107 losers,
# 57.8740% win rate;255 entries. Gross P&L668382,return208.869375%,profitfactor
# 1.49297688. Realized maxdrawdown132813.25 (41.504140625% fixed capital).
# CAGR149.76634545% is annualized ending-value arithmetic, not compounded sizing.
# Reported trailing1m/3m/6m returnsâˆ’7.549140625%/26.3453125%/95.493125%.
# One open trade: known gross MTM6207.50 at2026-10-01, excluded from realized
# statistics.26866 missing held-quote minutes; fills/exits and P&L provisional.
# Fees/taxes/slippage and historical broker margin are unavailable/unmodeled.
# Only81/210 published entries and20 exits match;174 extra entries,129 missing.
# Later dates were already inspected: not an untouched validation holdout.
#
# Month       Gross realized INR   Return%       Closed trades
# 2025-07*       77482.50          24.21328125        18
# 2025-08        81547.50          25.48359375        13
# 2025-09        78896.25          24.65507813        20
# 2025-10        10871.25           3.39726563        14
# 2025-11        31766.25           9.92695313        21
# 2025-12       -32280.00         -10.08750000        17
# 2026-01         -507.00          -0.15843750        27
# 2026-02        -3019.25          -0.94351563        17
# 2026-03       118046.50          36.88953125         9
# 2026-04        37072.75          11.58523438        10
# 2026-05        38870.00          12.14687500        20
# 2026-06       145330.25          45.41570313        18
# 2026-07        78858.00          24.64312500        15
# 2026-08        12353.25           3.86039063        17
# 2026-09         8092.50           2.52890625        17
# 2026-10*      -14998.75          -4.68710938         1
# *Partial first/last months. Monthly returns divide gross realized INR by320000.
# Deployable calculation uses no research files, historical cache or HTTP imports.
#
# IMPLEMENTATION VERIFICATION
# ---------------------------
# Named alpha and alpha2 match all 120,000 stored historical indicator values
# and unknown masks exactly (zero error). Native quote selection and causal
# prefix invariance have separate regression tests.
# Fresh standalone replay, 2026-09-28 through 2026-10-01, starts flat:
# 4 closed trades, 1 winner, win rate 25%, gross realized P&L -22,317.75 INR.
# 1 open trade with gross MTM +6,207.50 INR; combined P&L -16,110.25 INR.
# 351 held-leg quote gaps; results provisional. Full trailing 1/3/6-month
# returns unavailable in this four-day replay; no short-period CAGR claim.
# All five standalone trade records match the corresponding reference ledger
# in entry/exit times, strikes, sizing, signals, fills and realized P&L.
# Results: reports/strategy_01_last_week/{trades.csv,performance.json,summary.md}.

"""Named geometric-volume credit spread implementation."""
from __future__ import annotations

from dataclasses import replace
from datetime import date, time

import numpy as np
import pandas as pd

from config import StrategyConfig
from utils.time import IST

STRATEGY_NAME='strategy_01'
DESCRIPTION='Geometric-volume credit spread; opening ATM,800/300 ranks, logSTD150.'
PANEL_COLUMNS=('spot','reference_open','expiry','atm_strike','ce_ltp','pe_ltp',
               'ce_native_volume','pe_native_volume','ce_volume','pe_volume','ce_return','pe_return')


def apply_profile(cfg: StrategyConfig | None=None) -> StrategyConfig:
    """Freeze named signal/execution rules; retain configured capital/margin."""
    return replace(cfg or StrategyConfig(),alpha_lookback_minutes=800,alpha2_lookback_minutes=300,
        price_change_horizon_minutes=5,bullish_threshold=.8,bearish_threshold=.2,
        signal_start=time(10,15),signal_end=time(14,15),spread_distance=400,
        strike_reference='last_bar_open',max_short_premium=200.,volume_short_window=1,
        volume_baseline_window=10,volatility_window=150,alpha2_factor_lag_bars=5,
        stop_loss_margin_fraction=.05,target_spread_value=10.,time_exit=time(14,53),
        historical_time_exit_start=date(2025,7,9),historical_time_exit_end=date(2026,6,30),
        historical_time_exit=time(15,0),monday_capital_fraction=.8,
        monday_allocation_start=date(2026,4,6),market_open=time(9,15),market_close=time(15,30),underlying='NIFTY')


def _bars(bars):
    if not isinstance(bars.index,pd.DatetimeIndex) or bars.index.tz is None:
        raise ValueError('Completed bars need a timezone-aware start-minute clock')
    if bars.index.has_duplicates or not bars.index.is_monotonic_increasing:
        raise ValueError('Completed bars must be unique and chronological')
    if not bars.index.equals(bars.index.floor('min')):
        raise ValueError('Completed bar starts must align to minutes')
    result=bars[['open','close']].apply(pd.to_numeric,errors='coerce').copy()
    result.index=result.index.tz_convert(IST)
    return result


def calculate_indicators(bars: pd.DataFrame,panel: pd.DataFrame) -> pd.DataFrame:
    """Completed start-indexed bars + decision-indexed near panel -> indicators."""
    bars=_bars(bars);clock=bars.index+pd.Timedelta(minutes=1)
    if not isinstance(panel.index,pd.DatetimeIndex) or panel.index.tz is None:
        raise ValueError('Option panel needs a timezone-aware decision clock')
    if panel.index.has_duplicates or not panel.index.is_monotonic_increasing:
        raise ValueError('Option panel must be unique and chronological')
    selected=panel.copy();selected.index=selected.index.tz_convert(IST);selected=selected.reindex(clock)
    denominator=bars.open.shift(5)
    change=(bars.close-denominator)/denominator
    change.index=clock
    ratios=[];scales=[]
    for side in ('ce','pe'):
        # OPENING_CACHE keeps native candle volume even when prior quote missing.
        column=f'{side}_native_volume' if f'{side}_native_volume' in selected else f'{side}_volume'
        # Exact frozen reference: native feed values enter the rolling means as
        # recorded, including negative archival anomalies. Live builders already
        # reject negative cumulative differences; do not silently alter history.
        volume=pd.to_numeric(selected[column],errors='coerce')
        mean=volume.rolling(10,min_periods=8).mean()
        ratios.append(volume.rolling(1,min_periods=1).mean()/mean.where(mean.gt(0)))
        returns=pd.to_numeric(selected[f'{side}_return'],errors='coerce')
        logs=np.log1p(returns.where(lambda r:np.isfinite(r)&r.gt(-1)))
        scales.append(logs.rolling(150,min_periods=120).std(ddof=1))
    multiplier=np.sqrt(ratios[0]*ratios[1]).shift(5)
    volatility=(scales[0]+scales[1]).shift(5)
    raw=change*multiplier/volatility.where(volatility.gt(0))
    return pd.DataFrame({'alpha':change.rolling(800,min_periods=800).rank(method='average',pct=True),
        'alpha2':raw.rolling(300,min_periods=270).rank(method='average',pct=True),
        'price_change':change,'volume_ratio':multiplier,'atm_volatility':volatility,'raw':raw},index=clock)


def _near_expiries(clock,resolver,quotes):
    if resolver is not None:
        mapping={day:sorted(resolver(day)) for day in set(clock.date)}
        return [mapping[minute.date()][0] if mapping[minute.date()] else None for minute in clock]
    observed={minute:sorted({expiry for expiry in frame.index.get_level_values('expiry') if expiry>=minute.date()})
        for minute,frame in quotes.groupby(level='minute',sort=False)}
    return [observed.get(minute,[None])[0] if observed.get(minute) else None for minute in clock]


def _panel(bars,quotes,resolver,cumulative=False):
    bars=_bars(bars);clock=bars.index+pd.Timedelta(minutes=1)
    if not isinstance(quotes.index,pd.MultiIndex) or quotes.index.names!=['minute','expiry','strike']:
        raise ValueError('Quotes need exact minute/expiry/strike MultiIndex')
    if quotes.index.has_duplicates:raise ValueError('Duplicate exact option quote keys')
    quotes=quotes.copy()
    minutes=pd.DatetimeIndex(quotes.index.get_level_values('minute'))
    if minutes.tz is None:raise ValueError('Option quote minutes must be timezone aware')
    quotes.index=pd.MultiIndex.from_arrays([minutes.tz_convert(IST),
        pd.to_datetime(quotes.index.get_level_values('expiry')).date,
        pd.to_numeric(quotes.index.get_level_values('strike'))],names=quotes.index.names)
    expiry=_near_expiries(clock,resolver,quotes)
    strike=np.floor((bars.open.to_numpy()+25-1e-8)/50)*50
    keys=pd.MultiIndex.from_arrays([clock,expiry,strike],names=quotes.index.names)
    old_keys=pd.MultiIndex.from_arrays([clock-pd.Timedelta(minutes=1),expiry,strike],names=quotes.index.names)
    current=quotes.reindex(keys);previous=quotes.reindex(old_keys)
    result=pd.DataFrame({'spot':bars.close.to_numpy(),'reference_open':bars.open.to_numpy(),
        'expiry':expiry,'atm_strike':strike},index=clock)
    # The historical reference deliberately has no first-session option return.
    adjacent=(clock.hour*60+clock.minute)!=556
    for side in ('ce','pe'):
        price=pd.to_numeric(current[f'{side}_ltp'],errors='coerce').to_numpy(dtype=float)
        old=pd.to_numeric(previous[f'{side}_ltp'],errors='coerce').to_numpy(dtype=float)
        valid=adjacent&np.isfinite(price)&np.isfinite(old)&(price>0)&(old>0)
        result[f'{side}_ltp']=price
        result[f'{side}_return']=np.divide(price,old,out=np.full(len(price),np.nan),where=valid)-1
        volume_field=f'{side}_cum_volume' if cumulative else f'{side}_volume'
        volume=pd.to_numeric(current[volume_field],errors='coerce').to_numpy(dtype=float)
        old_volume=pd.to_numeric(previous[volume_field],errors='coerce').to_numpy(dtype=float)
        if cumulative:
            delta=volume-old_volume
            # Actual adjacent same-day contract snapshots only; day reset unknown.
            same_day=clock.date==(clock-pd.Timedelta(minutes=1)).date
            known=same_day&np.isfinite(volume)&np.isfinite(old_volume)&(delta>=0)
            volume=np.where(known,delta,np.nan)
        result[f'{side}_native_volume']=volume
        result[f'{side}_volume']=np.where(adjacent&np.isfinite(old_volume),volume,np.nan)
    return result[list(PANEL_COLUMNS)]


def panel_from_options(bars: pd.DataFrame,options: pd.DataFrame,expiries_for) -> pd.DataFrame:
    """Native historical candles; exact fixed contract predecessor, near path."""
    return _panel(bars,options,expiries_for,cumulative=False)


def panel_from_snapshots(bars: pd.DataFrame,snapshots: pd.DataFrame,expiries_for=None) -> pd.DataFrame:
    """Observed chain snapshots; derive same-contract minute volume deltas."""
    if snapshots is None or snapshots.empty:
        empty=pd.DataFrame(index=pd.MultiIndex.from_arrays([pd.DatetimeIndex([],tz=IST),[],[]],
            names=['minute','expiry','strike']),columns=['ce_ltp','pe_ltp','ce_cum_volume','pe_cum_volume'],dtype=float)
        return _panel(bars,empty,expiries_for,cumulative=True)
    quotes=snapshots.copy();quotes['minute']=pd.to_datetime(quotes.minute,utc=True).dt.tz_convert(IST)
    return _panel(bars,quotes.set_index(['minute','expiry','strike']),expiries_for,cumulative=True)


def create_engine(cfg,calendar,**kwargs):
    """Shared execution engine, with named calculation and entry identity."""
    import sys
    from strategy.registry import create_named_engine
    return create_named_engine(sys.modules[__name__],cfg,calendar,**kwargs)
