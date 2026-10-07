"""Performance metrics on a trade ledger.

Conventions follow the provider's reporting, verified by recomputing the
provider's own figures from its reference trade CSV (data/reference/past_trade.csv):
* returns are simple, on a fixed capital base (no compounding):
  all-time 835053.25 / 320000 = 260.95%;
* daily P&L is booked on the trade's exit date;
* drawdown = (cumulative P&L - running peak of cumulative P&L, floored at 0)
  / capital  (reproduces the provider's -25.39%);
* consecutive wins/losses are counted over days with booked P&L (reproduces 10/4);
* Sharpe / Sortino use daily P&L / capital over ALL business days in the
  period (zero on days without a closed trade), annualised with sqrt(252),
  risk-free 0 (reproduces Sharpe 2.89); Calmar = CAGR / |max drawdown|.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from utils.time import round_half_up


def _streaks(signs: list[bool]) -> tuple[int, int]:
    best_w = best_l = cur_w = cur_l = 0
    for s in signs:
        if s:
            cur_w, cur_l = cur_w + 1, 0
        else:
            cur_l, cur_w = cur_l + 1, 0
        best_w, best_l = max(best_w, cur_w), max(best_l, cur_l)
    return best_w, best_l


def drawdown_table(cum_pnl: pd.Series, capital: float) -> tuple[pd.Series, list[dict]]:
    peak = cum_pnl.cummax().clip(lower=0.0)
    dd = (cum_pnl - peak) / capital
    episodes, start, trough = [], None, None
    for ts, v in dd.items():
        if v < 0 and start is None:
            start, trough = ts, (ts, v)
        elif v < 0:
            if v < trough[1]:
                trough = (ts, v)
        elif start is not None:
            episodes.append({"start": start, "trough": trough[0], "end": ts, "depth": trough[1]})
            start = None
    if start is not None:
        episodes.append({"start": start, "trough": trough[0], "end": None, "depth": trough[1]})
    return dd, episodes


def compute_metrics(trades: pd.DataFrame, capital: float, pnl_col: str = "pnl",
                    exit_col: str = "exit_ts") -> dict:
    if trades.empty:
        return {"trade_count": 0}
    t = trades.sort_values(exit_col)
    pnl = t[pnl_col].astype(float)
    pct = 100.0 * pnl / capital
    wins, losses = pnl[pnl > 0], pnl[pnl <= 0]
    trade_w, trade_l = _streaks(list(pnl > 0))

    ts = pd.to_datetime(t[exit_col])
    if ts.dt.tz is not None:
        ts = ts.dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)
    day = ts.dt.normalize()
    daily = pnl.groupby(day.values).sum().sort_index()
    daily.index = pd.DatetimeIndex(daily.index)
    max_w, max_l = _streaks(list(daily > 0))
    start_row = pd.Series([0.0], index=[daily.index[0] - pd.Timedelta(days=1)])
    cum_full = pd.concat([start_row, daily.cumsum()])
    dd, episodes = drawdown_table(cum_full, capital)
    closed = [e for e in episodes if e["end"] is not None]
    rec_days = [(e["end"] - e["start"]).days for e in closed]
    longest = max(episodes, key=lambda e: ((e["end"] or cum_full.index[-1]) - e["start"]).days) if episodes else None

    all_days = pd.bdate_range(daily.index[0], daily.index[-1])
    r = daily.reindex(all_days, fill_value=0.0) / capital
    years = max((daily.index[-1] - daily.index[0]).days / 365.25, 1 / 365.25)
    total_ret = daily.sum() / capital
    cagr = (1 + total_ret) ** (1 / years) - 1 if total_ret > -1 else float("nan")
    downside = r[r < 0]
    sharpe = r.mean() / r.std(ddof=1) * math.sqrt(252) if r.std(ddof=1) > 0 else float("nan")
    sortino = (r.mean() / math.sqrt((downside ** 2).sum() / len(r)) * math.sqrt(252)
               if len(downside) else float("nan"))
    max_dd = float(dd.min())
    monthly = (daily.groupby(daily.index.to_period("M")).sum() / capital * 100.0)
    yearly = (daily.groupby(daily.index.year).sum() / capital * 100.0)

    def rp(x, n=2):
        return None if x is None or (isinstance(x, float) and math.isnan(x)) else round_half_up(float(x), n)

    return {
        "trade_count": int(len(t)),
        "winning_trades": int(len(wins)), "losing_trades": int(len(losses)),
        "win_rate_pct": rp(100.0 * len(wins) / len(t)),
        "avg_profit": rp(wins.mean() if len(wins) else 0.0), "avg_loss": rp(losses.mean() if len(losses) else 0.0),
        "avg_profit_pct_of_capital": rp(pct[pnl > 0].mean() if len(wins) else 0.0),
        "avg_loss_pct_of_capital": rp(pct[pnl <= 0].mean() if len(losses) else 0.0),
        "total_pnl": rp(pnl.sum()), "total_return_pct": rp(100.0 * total_ret),
        "cagr_pct": rp(100.0 * cagr),
        "max_drawdown_pct": rp(100.0 * max_dd),
        "avg_drawdown_pct": rp(100.0 * np.mean([e["depth"] for e in episodes])) if episodes else 0.0,
        "max_consecutive_wins": max_w, "max_consecutive_losses": max_l,
        "max_consecutive_winning_trades": trade_w, "max_consecutive_losing_trades": trade_l,
        "avg_recovery_days": rp(np.mean(rec_days)) if rec_days else None,
        "max_recovery_days": int(max(rec_days)) if rec_days else None,
        "longest_drawdown": ({"start": str(longest["start"].date()),
                              "end": str(longest["end"].date()) if longest["end"] is not None else None,
                              "days": ((longest["end"] or cum_full.index[-1]) - longest["start"]).days}
                             if longest else None),
        "win_days_pct": rp(100.0 * (daily > 0).mean()),
        "win_months_pct": rp(100.0 * (monthly > 0).mean()),
        "sharpe": rp(sharpe), "sortino": rp(sortino),
        "calmar": rp(cagr / abs(max_dd)) if max_dd < 0 else None,
        "best_day_pct": rp(100.0 * r.max()), "worst_day_pct": rp(100.0 * r.min()),
        "monthly_returns_pct": {str(k): rp(v) for k, v in monthly.items()},
        "yearly_returns_pct": {str(k): rp(v) for k, v in yearly.items()},
        "risk_reward": rp(abs(wins.mean() / losses.mean())) if len(wins) and len(losses) and losses.mean() else None,
    }


def compute_period_performance(trades: pd.DataFrame, capital: float, period_start,
                               period_end, pnl_col: str = "pnl",
                               exit_col: str = "exit_ts") -> dict:
    """Gross realized performance over explicit inclusive IST calendar dates.

    Bounds describe observed replay coverage, not the first/last closed trade.
    Naive times are IST; aware times are converted to IST. Out-of-period closed
    rows and invalid closed values raise rather than silently changing coverage.
    Open rows have missing exits and are excluded. An optional unrealized_pnl /
    valuation_ts pair contributes a separate MTM only when every open row has a
    finite mark on the observation end date; it never changes realized metrics.
    Returns use a fixed capital denominator. CAGR describes the ending realized
    value's annualized growth over inclusive observed days; sizing is not assumed
    to compound. Trailing windows are calendar offsets, lower date exclusive.
    """
    try:
        capital=float(capital)
    except (TypeError,ValueError) as exc:
        raise ValueError('Capital must be finite and positive') from exc
    if not np.isfinite(capital) or capital<=0:
        raise ValueError('Capital must be finite and positive')

    def ist_timestamp(value):
        try:
            ts=pd.Timestamp(value)
            if pd.isna(ts):raise ValueError('Missing timestamp')
            return ts.tz_localize('Asia/Kolkata') if ts.tzinfo is None else ts.tz_convert('Asia/Kolkata')
        except (TypeError,ValueError,OverflowError) as exc:
            raise ValueError(f'Invalid timestamp: {value!r}') from exc

    start=ist_timestamp(period_start).normalize();end=ist_timestamp(period_end).normalize()
    if end<start:raise ValueError('Observation end precedes start')
    days=int((end.date()-start.date()).days+1)
    if not isinstance(trades,pd.DataFrame):raise ValueError('Trades must be a DataFrame')
    if not trades.empty and (pnl_col not in trades or exit_col not in trades):
        raise ValueError('Trade ledger requires P&L and exit columns')
    if trades.empty:
        closed=pd.DataFrame({'exit':pd.Series([],dtype='datetime64[ns, Asia/Kolkata]'),
                             'pnl':pd.Series([],dtype=float)})
        open_count=0
    else:
        open_mask=trades[exit_col].isna();open_count=int(open_mask.sum())
        rows=trades.loc[~open_mask]
        exits=(pd.DatetimeIndex([ist_timestamp(value) for value in rows[exit_col]])
               if len(rows) else pd.DatetimeIndex([],tz='Asia/Kolkata'))
        pnl=pd.to_numeric(rows[pnl_col],errors='coerce').to_numpy(dtype=float)
        if not np.isfinite(pnl).all():raise ValueError('Closed trade P&L must be finite and known')
        dates=exits.normalize()
        if ((dates<start)|(dates>end)).any():
            raise ValueError('Closed trade exits fall outside observed period')
        closed=pd.DataFrame({'exit':exits,'pnl':pnl}).sort_values('exit',kind='stable')
    known_open_marks=[]
    if open_count and {'unrealized_pnl','valuation_ts'}.issubset(trades.columns):
        for row in trades.loc[open_mask].itertuples(index=False):
            try:
                mark=float(row.unrealized_pnl);valuation=ist_timestamp(row.valuation_ts)
            except (TypeError,ValueError):continue
            if np.isfinite(mark) and valuation.normalize()==end:
                known_open_marks.append(mark)
    open_mtm_known=len(known_open_marks)==open_count
    open_mtm=float(sum(known_open_marks)) if open_mtm_known else None
    if closed.empty:
        closed['day']=pd.Series([],dtype='datetime64[ns, Asia/Kolkata]')
    else:closed['day']=closed.exit.dt.normalize()

    def statistics(frame):
        pnl=frame.pnl.to_numpy(dtype=float);count=len(pnl)
        wins=int((pnl>0).sum());losses=int((pnl<0).sum());breakeven=int((pnl==0).sum())
        gross_profit=float(pnl[pnl>0].sum());gross_loss=float(-pnl[pnl<0].sum())
        total=float(pnl.sum())
        if not np.isfinite(total) or not np.isfinite(gross_profit) or not np.isfinite(gross_loss):
            raise ValueError('Closed P&L totals overflow finite arithmetic')
        # Simultaneous exits are aggregated, avoiding arbitrary ledger row order.
        booked=frame.groupby('exit',sort=True).pnl.sum().to_numpy(dtype=float)
        cumulative=np.r_[0.,np.cumsum(booked)]
        drawdown=cumulative-np.maximum.accumulate(cumulative)
        return {'trade_count':int(count),'winning_trades':wins,'losing_trades':losses,
            'breakeven_trades':breakeven,'win_rate_pct':100.*wins/count if count else 0.,
            'total_pnl':total,'total_return_pct':100.*total/capital,
            'gross_profit':gross_profit,'gross_loss':gross_loss,
            'profit_factor':gross_profit/gross_loss if gross_loss>0 else None,
            'profit_factor_status':'defined' if gross_loss>0 else ('no_losses' if gross_profit>0 else 'no_profit_or_loss'),
            'max_drawdown_rupees':float(-drawdown.min()),
            'max_drawdown_pct':float(100.*drawdown.min()/capital)}

    total=statistics(closed);ending=capital+total['total_pnl']
    # log/expm1 avoids loss of precision for small returns. Zero ending equity
    # gives -100%; negative equity has no meaningful real-valued CAGR.
    cagr_status='defined' if ending>=0 else 'negative_ending_value'
    if ending==0:cagr=-100.
    elif ending<0:cagr=None
    else:
        try:
            cagr=100.*math.expm1(math.log(ending/capital)*365.25/days)
            if not np.isfinite(cagr):cagr=None;cagr_status='numerical_overflow'
        except OverflowError:cagr=None;cagr_status='numerical_overflow'
    monthly=[]
    for month in pd.period_range(start.tz_localize(None),end.tz_localize(None),freq='M'):
        first=pd.Timestamp(month.start_time).tz_localize('Asia/Kolkata').normalize()
        last=pd.Timestamp(month.end_time).tz_localize('Asia/Kolkata').normalize()
        observed_start=max(start,first);observed_end=min(end,last)
        frame=closed.loc[(closed.day>=observed_start)&(closed.day<=observed_end)]
        stats=statistics(frame)
        monthly.append({'month':str(month),'pnl':stats['total_pnl'],'pnl_rupees':stats['total_pnl'],'return_pct':stats['total_return_pct'],
            'closed_trades':stats['trade_count'],'trade_count':stats['trade_count'],'winning_trades':stats['winning_trades'],
            'losing_trades':stats['losing_trades'],'breakeven_trades':stats['breakeven_trades'],
            'win_rate_pct':stats['win_rate_pct'],'partial_month':bool(observed_start!=first or observed_end!=last),
            'observed_start':str(observed_start.date()),'observed_end':str(observed_end.date())})
    trailing={}
    for months in (1,3,6):
        lower=end-pd.DateOffset(months=months);required_start=lower+pd.Timedelta(days=1)
        available=start<=required_start
        frame=closed.loc[(closed.day>lower)&(closed.day<=end)]
        trailing[f'{months}m']={'available':bool(available),'lower_date_exclusive':str(lower.date()),
            'end_date_inclusive':str(end.date()),'unavailable_reason':None if available else 'Observed period is shorter than this calendar window',
            **(statistics(frame) if available else {key:None for key in total})}
    return {'basis':'gross realized P&L; expenses not deducted','capital':capital,
        'return_basis':'fixed capital; no compounded sizing assumed',
        'period_start':str(start.date()),'period_end':str(end.date()),'observation_days':days,
        'period_day_count_convention':'inclusive IST calendar dates: end - start + 1',
        **total,'ending_realized_value':ending,'cagr_pct':cagr,
        'cagr_status':cagr_status,
        'open_trade_count':open_count,'open_mtm_pnl':open_mtm,
        'open_mtm_known_trade_count':len(known_open_marks),
        'open_mtm_asof':str(end.date()) if open_count and open_mtm_known else None,
        'open_mtm_status':('known_end_date_marks; excluded from realized statistics' if open_mtm_known else
            'unknown_or_stale_marks; excluded from realized statistics') if open_count else 'no_open_trades',
        'return_1m_pct':trailing['1m']['total_return_pct'],
        'return_3m_pct':trailing['3m']['total_return_pct'],
        'return_6m_pct':trailing['6m']['total_return_pct'],
        'monthly':monthly,'trailing':trailing}
