# Strategy 02: variance-scaled credit spreads. Candidate 719c7c6bc176871c.
#
# WORKING AND TRIGGERS
# Completed NIFTY one-minute candle t: x=(close[t]-open[t-5])/open[t-5].
# Alpha is the average percentile rank of x over 800 observed trading candles,
# requiring all 800 values. No forward-looking close is used.
# Select nearest-expiry ATM from completed candle OPEN, nearest 50 points;
# exact half-strike ties go down. Missing the required strike stays unknown.
# Native historical one-minute CE and PE volumes each divide by their own
# 10-candle rolling mean, requiring 8 known candles. Take sqrt(CEratio*PEratio).
# For each selected CE/PE, use adjacent same-contract same-session one-minute
# log returns. Compute sample VARIANCE over 300 candles (ddof=1), requiring
# 240 known observations per side. Volatility denominator is CEvariance+PEvariance.
# Lag both the volume multiplier and variance denominator by 5 observed candles
# on the continuous near-ATM path. Raw beta=x*lagged multiplier/lagged variance.
# Alpha2 is its trailing 300-candle average percentile rank, minimum 270 values.
# Recorded native-volume anomalies are retained for exact historical reproduction;
# live negative cumulative-volume differences remain unknown. Neither candles nor
# missing quotes are filled. Return-based volatility uses each contract's own
# predecessor even when the selected ATM changes. Histories continue across rolls.
#
# When flat, 10:15-14:15 IST inclusive: alpha>0.8 and alpha2>0.8 -> PUT credit
# spread; alpha<0.2 and alpha2<0.2 -> CALL credit spread. Sell opening ATM and
# buy a put 400 below or call 400 above, same near expiry. Short premium <=200,
# positive net credit required. One position, exits first, no same-cycle reentry.
# Capital defaults to INR320000; allocate 80% on Mondays from 2026-04-06,
# otherwise 100%. Normal estimated lot margin=2.25*400*lot_size unless overridden.
# Expiry-day entry margin multiplier=1.54. Lots=floor(allocation/entry margin).
# Stop spread=entry credit+5% normal margin/lot_size. PROFIT TARGET DISABLED.
# Scheduled exit is next trading day, capped at expiry: 15:00 for entries from
# 2025-07-09 through 2026-06-30; otherwise 14:53. Expired-position fallback uses
# official cash settlement only once observed by the shared engine. No reversal
# exit or manufactured broker force-liquidation rule. Missing held-leg quotes
# can postpone exits and suppress subsequent trades. Capital/margin overrides
# change sizing and results; strategy-specific signal and exit settings are pinned.
#
# FULL REFERENCE BACKTEST: 2025-07-09 THROUGH 2026-10-01, 450 calendar dates.
# Gross fixed-capital statistics, expenses excluded. One open trade is separate.
# Closed trades: 194
# Winners: 112
# Losers: 82
# Win rate %: 57.7319587628866
# Gross realized P&L INR: 785704.25
# Fixed-capital total return %: 245.532578125
# CAGR equivalent %: 173.57321367604976
# Trailing 1m return %: -2.32375
# Trailing 3m return %: 9.316328125
# Trailing 6m return %: 78.265078125
# Realized max drawdown %: -33.484140625
# Profit factor: 1.6949166858481917
# Open trade count: 1
# Open gross MTM INR: 16965.0
# Published entry matches: 73/210; extra entries: 122; matching exits: 23.
# Missing held-leg quote minutes: 29371.
# CAGR annualizes ending realized value; position sizing does not compound.
# Gross profit and drawdown improve on Strategy01, but later 3m/6m returns and
# Zen entry matching are worse. These trials are research, not a recovered Zen
# replica or proof of live advantage. Costs, broker margin and RMS are not modeled.
# Later periods were already inspected, not an untouched holdout. Do not interpret
# this gross simulation as an audited net return. All statistics are provisional.
#
# MONTHLY GROSS REALIZED P&L (INR) / FIXED-CAPITAL RETURN / CLOSED TRADES
# 2025-07*:     58035.00 /  18.135938% / 13
# 2025-08 :     65276.25 /  20.398828% / 10
# 2025-09 :    111442.50 /  34.825781% / 13
# 2025-10 :      8587.50 /   2.683594% / 13
# 2025-11 :     24675.00 /   7.710938% / 16
# 2025-12 :    -11880.00 /  -3.712500% / 15
# 2026-01 :     76202.75 /  23.813359% / 14
# 2026-02 :     84347.25 /  26.358516% / 13
# 2026-03 :    118569.75 /  37.053047% / 8
# 2026-04 :     65113.75 /  20.348047% / 8
# 2026-05 :    -51164.75 / -15.988984% / 16
# 2026-06 :    206687.00 /  64.589687% / 11
# 2026-07 :     50332.75 /  15.728984% / 14
# 2026-08 :      2609.75 /   0.815547% / 15
# 2026-09 :    -23130.25 /  -7.228203% / 15
# 2026-10*:         0.00 /   0.000000% / 0
# *Partial first/last months. Source: reports/provider_research/replication_trials/
# volatility_definitions/full_autonomous_719c7c6bc176871c_ledger/.
# Use STRATEGY_NAME=strategy_02 and a separate DATABASE_URL for virtual forward
# execution. Live volume is adjacent cumulative snapshot differences, so feed
# parity with native historical candles is not guaranteed. No broker orders.
# NAMED IMPLEMENTATION VERIFICATION
# Alpha and alpha2 exactly match all 120000 reference values and unknown masks.
# Fresh standalone 2026-09-28--2026-10-01 replay starts flat: 3 closed trades,
# 1 winner,33.33% wins,gross realized loss7091.50 INR. One open trade gross MTM
# +16965.00 INR; combined observed P&L +9873.50 INR,351 held-quote gaps.
# All four trade records match the same week in the completed reference ledger.
# No complete 1m/3m/6m window in this short replay; do not annualize its return.
# Outputs: reports/strategy_02_last_week/{trades.csv,performance.json,summary.md}.


"""Named variance-scaled credit spread candidate."""
from __future__ import annotations
from dataclasses import replace
import sys
import numpy as np
import pandas as pd
from strategy import strategy_01_geometric_credit as first
from strategy.strategy_01_geometric_credit import panel_from_options,panel_from_snapshots
from utils.time import IST

STRATEGY_NAME='strategy_02'
DESCRIPTION='Geometric volume1/10, summed log-return variance300, five-bar lag; target disabled.'
PROFIT_TARGET_ENABLED=False

def apply_profile(cfg=None):
    return replace(first.apply_profile(cfg),volatility_window=300)

def calculate_indicators(bars,panel):
    # Shared price/volume rules and validation; replace the volatility and beta.
    frame=first.calculate_indicators(bars,panel)
    selected=panel.copy();selected.index=selected.index.tz_convert(IST)
    selected=selected.reindex(frame.index)
    variances=[]
    for side in ('ce','pe'):
        values=pd.to_numeric(selected[f'{side}_return'],errors='coerce')
        logs=np.log1p(values.where(np.isfinite(values)&values.gt(-1)))
        variances.append(logs.rolling(300,min_periods=240).var(ddof=1))
    scale=(variances[0]+variances[1]).shift(5)
    raw=frame.price_change*frame.volume_ratio/scale.where(scale.gt(0))
    frame['atm_volatility']=scale;frame['raw']=raw
    frame['alpha2']=raw.rolling(300,min_periods=270).rank(method='average',pct=True)
    return frame

def create_engine(cfg,calendar,**kwargs):
    from strategy.registry import create_named_engine
    return create_named_engine(sys.modules[__name__],cfg,calendar,**kwargs)
