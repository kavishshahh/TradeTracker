"""Causal exit hypotheses on original spreads; incomplete paths never score as matches."""
from datetime import date
import json
import numpy as np
import pandas as pd
from backtest.provider_research import BAR_CACHE,OUTPUT,provider_trades
from backtest.provider_calendar import ProviderCalendar
from utils.time import IST

OUT=OUTPUT/'replication_trials'


def margin_requirement(normal_margin, units, spot, mode, multiplier=1.5):
    """Scenario estimate, not historical SPAN or a broker margin response."""
    if mode=='multiplier':return normal_margin*multiplier
    if mode=='additional_elm':return normal_margin+.02*np.asarray(spot)*units
    raise ValueError(f'Unknown margin scenario: {mode}')


def margin_shortfall(required, capital, marked_profit=None):
    """Unknown marked P&L leaves account equity unknown; never fill it with zero."""
    funds=capital if marked_profit is None else capital+np.asarray(marked_profit)
    return np.asarray(required)-funds


def requires_expiry_uplift(entry_day,expiry,exit_day):
    # Expiry entries already report expiry-day entry margin.
    return entry_day<expiry<=exit_day


def review_september_exit_bounds():
    """Missing-hedge compatibility bounds, never replacement executable prices."""
    from datetime import timedelta
    from backtest.dhan_history import DhanHistoryClient
    from backtest.dhan_replay import parse_series
    probe=json.loads((OUT/'far_strike_probe.json').read_text())
    trade=provider_trades().set_index('signal_id').loc[probe['signal_id']]
    first=trade.exit.date();last=first+timedelta(days=1)
    # Reuse cache, or obtain the three read-only historical requests if absent.
    client=DhanHistoryClient();series={};requests=[]
    for strike in ('ATM+3','ATM+4','ATM+10'):
        request=dict(probe['request']);request['strike']=strike
        request['requiredData']=['open','high','low','close','volume','strike','spot']
        raw=client.request('rollingoption',request)
        series[strike]=parse_series(raw['data']['ce'],first,last,ProviderCalendar())
        requests.append(request)
    if trade.option_type!='CE' or trade.expiry!=first:
        raise ValueError('This explicit case expects the September call spread expiring on the exit date')
    short=pd.concat([series[s].loc[series[s].strike.eq(trade.short_strike)] for s in ('ATM+3','ATM+4')]).sort_index()
    if short.index.duplicated().any():raise ValueError('Duplicate fixed-strike rows; do not choose one silently')
    bound=series['ATM+10']
    valid_bound=bound.strike.lt(trade.hedge_strike)&bound.strike.gt(trade.short_strike)
    bound=bound.loc[valid_bound]
    frame=pd.DataFrame({'short_strike':short.strike,'short_open':short.open,'short_low':short.low,
        'short_high':short.high,'short_close':short.close,'observed_lower_strike':bound.strike,
        'DIAGNOSTIC_hedge_upper_high':bound.high,'DIAGNOSTIC_hedge_upper_close':bound.close})
    frame=frame.loc[frame.index<=trade.exit_minute+pd.Timedelta(minutes=2)]
    frame['bar_close_known_at']=frame.index+pd.Timedelta(minutes=1)
    frame['DIAGNOSTIC_net_lower_intrabar']=frame.short_low-frame.DIAGNOSTIC_hedge_upper_high
    frame['DIAGNOSTIC_net_upper_intrabar']=frame.short_high
    frame['DIAGNOSTIC_net_lower_at_close']=frame.short_close-frame.DIAGNOSTIC_hedge_upper_close
    frame['DIAGNOSTIC_net_upper_at_close']=frame.short_close
    frame.index.name='bar_start'
    frame.to_csv(OUT/'september_exit_bounds_DIAGNOSTIC.csv')
    results=[]
    for level in (5.,10.,10.5,12.,15.):
        possible=frame.DIAGNOSTIC_net_lower_intrabar.le(level)
        hits=frame.index[possible]
        rows=frame.DIAGNOSTIC_net_lower_intrabar.notna()
        results.append({'target':level,'first_possible_bar_start':str(hits[0]) if len(hits) else None,
            'not_excluded_before_source_exit':bool(possible.loc[possible.index<=trade.exit_minute].any()),
            'earlier_unknown_bars':int((~rows.loc[rows.index<hits[0]]).sum()) if len(hits) else int((~rows).sum())})
    design={'signal_id':probe['signal_id'],'source_exit':str(trade.exit),'source_exit_net_fill':trade.debit,
        'short_strike':trade.short_strike,'missing_hedge_strike':trade.hedge_strike,'targets':results,'requests':requests,
        'assumption':'For synchronous non-arbitrage prices of European calls sharing expiry, the higher-strike hedge is between zero and the observed lower-strike call. High/low combinations produce only an outer interval, not a realized spread path.',
        'limitations':['Last-traded OHLC prices are not guaranteed synchronous or executable bid/ask quotes.',
            'Current-bar high/low are unavailable before bar completion; these bounds never enter autonomous decisions.',
            'A possible target is not proof of a touch before the recorded exit, and does not distinguish broker liquidation.',
            'No hedge quote is filled, interpolated, marked at zero or used to score an incomplete path as an exit match.']}
    (OUT/'september_exit_bounds_design.json').write_text(json.dumps(design,indent=2,default=str))
    print(pd.DataFrame(results).to_string(index=False),flush=True)


def review_margin_exits():
    """Screen all source trades; only overnight expiry carry gets an extra uplift.

    These are conditional scenarios on source positions, not autonomous exits.
    Starting broker margin and capital are held fixed, and marked P&L is only an
    alternative equity proxy. Actual broker funds, daily SPAN, top-ups, released
    premium and RMS decisions are unavailable. A breach is not an execution.
    """
    OUT.mkdir(exist_ok=True)
    trades=provider_trades()
    bars=pd.read_csv(BAR_CACHE)
    bars.index=pd.to_datetime(bars.pop('timestamp'),utc=True).dt.tz_convert(IST)+pd.Timedelta(minutes=1)
    paths=pd.read_csv(OUTPUT/'actual_contract_paths.csv.gz')
    paths.minute=pd.to_datetime(paths.minute,utc=True).dt.tz_convert(IST)
    coverage=pd.read_csv(OUTPUT/'exit_diagnostics.csv').set_index('signal_id')
    summaries=[];observations=[]
    scenarios=[('multiplier',1.5),('multiplier',1.54),('additional_elm',None)]
    for t in trades.itertuples():
        overnight=requires_expiry_uplift(t.entry.date(),t.expiry,t.exit.date())
        held=bars.loc[(bars.index.date==t.expiry)&(bars.index<=t.exit_minute)] if overnight else bars.iloc[:0]
        p=paths.loc[paths.signal_id.eq(t.signal_id)].set_index('minute').reindex(held.index)
        profit=(t.credit-p.net.to_numpy())*t.units
        entry_margin=t.margin_per_lot*t.lots
        for mode,factor in scenarios:
            required=np.broadcast_to(margin_requirement(entry_margin,t.units,held.close.to_numpy(),mode,factor),len(held))
            for equity in ('fixed_capital','capital_plus_marked_pnl'):
                shortfall=margin_shortfall(required,320000.,profit if equity=='capital_plus_marked_pnl' else None)
                hit=np.flatnonzero(shortfall>0)
                k=int(hit[0]) if len(hit) else None
                first=held.index[k] if k is not None else pd.NaT
                delta=(first-t.exit_minute).total_seconds()/60 if k is not None else np.nan
                valid=np.isfinite(shortfall)
                row={'signal_id':t.signal_id,'split':t.split,'entry':t.entry,'source_exit':t.exit,'expiry':t.expiry,
                    'lots':t.lots,'units':t.units,'allocation_pct':t.allocation_pct,'entry_total_margin':entry_margin,
                    'capital_assumed':320000.,'overnight_into_expiry':overnight,
                    'entry_on_expiry':t.entry.date()==t.expiry,'after_expiry_record':t.exit_recorded_after_expiry,
                    'scenario':mode,'multiplier':factor,'equity_proxy':equity,
                    'snapshots':len(held),'unknown_equity_snapshots':int((~valid).sum()),
                    'earlier_unknown_snapshots':int((~valid[:k]).sum()) if k is not None else int((~valid).sum()),
                    'first_known_shortfall':first,'minutes_after_source_exit':delta,
                    'shortfall_at_first_known_breach':shortfall[k] if k is not None else np.nan,
                    'margin_at_first_expiry_snapshot':required[0] if len(held) else np.nan,
                    'margin_at_last_snapshot':required[-1] if len(held) else np.nan,
                    'shortfall_at_last_snapshot':shortfall[-1] if len(held) else np.nan,
                    'same_minute_as_source_exit':bool(delta==0),
                    'within_two_minutes':bool(abs(delta)<=2),
                    'source_pnl':t.pnl_reported,'source_pnl_reconciles':t.pnl_reconciles,
                    # Exit-fill P&L is available only afterwards. This column
                    # cannot trigger a replay exit or fill a missing leg quote.
                    'preclose_shortfall_at_source_fill_DIAGNOSTIC':required[-1]-320000.-t.pnl_reported if len(held) else np.nan,
                    'complete_option_path_to_exit':bool(coverage.loc[t.signal_id,'complete_to_exit']),
                    'baseline_exit':coverage.loc[t.signal_id,'baseline_first_exit'],
                    'baseline_reason':coverage.loc[t.signal_id,'baseline_exit_reason'],
                    'interpretation':('no_overnight_expiry_uplift_tested' if not overnight else
                        'possible_shortfall_not_confirmed_liquidation' if k is not None else 'no_observed_shortfall_in_this_scenario')}
                summaries.append(row)
                if len(held):
                    observations.append(pd.DataFrame({'signal_id':t.signal_id,'minute':held.index,'scenario':mode,
                        'multiplier':factor,'equity_proxy':equity,'spot_known':held.close.to_numpy(),
                        'estimated_required_margin':required,'marked_spread_pnl':profit,
                        'estimated_shortfall':shortfall,'both_legs_known':p.net.notna().to_numpy()}))
    details=pd.DataFrame(summaries)
    details.to_csv(OUT/'margin_exit_scenarios.csv',index=False)
    if observations:pd.concat(observations,ignore_index=True).to_csv(OUT/'margin_expiry_snapshots.csv.gz',index=False)
    carry=details.loc[details.overnight_into_expiry]
    score=carry.groupby(['scenario','multiplier','equity_proxy'],dropna=False).agg(
        trades=('signal_id','size'),possible_shortfalls=('first_known_shortfall','count'),
        same_exit_minute=('same_minute_as_source_exit','sum'),within_two_minutes=('within_two_minutes','sum')).reset_index()
    score.to_csv(OUT/'margin_exit_scorecard.csv',index=False)
    limitations=[
        'Source positions condition this diagnostic; no autonomous liquidation policy has been added.',
        'Full account capital is assumed INR 320,000, not the sometimes smaller entry allocation. No top-ups or other positions are known.',
        'The 1.50/1.54 multiplier scenarios are assumptions. The additional-ELM scenario adds 2% of short index notional to the entry margin, holding all other components constant.',
        'Expiry-day entries already report their entry margin; they are not multiplied again. Trades closed before expiry receive no additional expiry uplift.',
        'Capital plus marked spread P&L is an equity proxy, not actual broker available funds or a model of option premium settlement.',
        'First snapshots use completed index bars from 09:16, so an overnight breach could exist before our first observation. Missing option prices leave marked equity unknown.',
        'A shortfall does not establish whether, when, or how many lots the broker liquidated. Broker margin/ledger/order-reason records are needed to confirm.',
        'Paths end at the source exit; no later data or reported exit P&L is used to trigger a scenario. Post-expiry recorded exits remain flagged.'
        ,'The source-fill shortfall column is a counterfactual using reported exit P&L as pre-close equity. It is an after-the-fact diagnostic, never a replay trigger or a claim about post-close margin.'
    ]
    report=['# Expiry margin and possible broker exits','',
        f'Checked all {len(trades)} published trades. {carry.signal_id.nunique()} entered before expiry and were recorded open into expiry.',
        '',score.to_string(index=False),'','## Interpretation','',
        'Possible shortfalls are candidates for broker-driven exits, not confirmed strategy signals or liquidation fills.',
        '', '## Assumptions and limitations','']+['- '+x for x in limitations]
    report+=['','Sources: [NSE Clearing additional expiry-day ELM circular](https://nsearchives.nseindia.com/content/circulars/CMPT64639.pdf); [Dhan automatic position closure policy](https://dhan.co/support/orders-and-positions/positions/under-what-circumstances-will-dhan-automatically-close-my-positions-trades/).']
    unexplained=details.loc[details.scenario.eq('multiplier')&details.multiplier.eq(1.5)&details.equity_proxy.eq('fixed_capital')&
        details.within_two_minutes&details.complete_option_path_to_exit&details.baseline_reason.eq('not_observed')]
    report+=['','## Margin candidates without an observed baseline exit','',
        'These source exits coincide with the first margin scenario snapshot while the existing stop/target/time baseline did not trigger on the complete minute-close path. This supports investigating RMS; it still does not exclude an intraminute strategy trigger.',
        '',unexplained[['entry','source_exit','entry_total_margin','source_pnl','first_known_shortfall']].to_string(index=False)]
    report+=['','## Last two source trades','',details.loc[details.signal_id.isin(trades.tail(2).signal_id)&details.scenario.eq('multiplier')&details.multiplier.eq(1.5),
        ['entry','source_exit','lots','entry_total_margin','equity_proxy','first_known_shortfall','shortfall_at_last_snapshot','preclose_shortfall_at_source_fill_DIAGNOSTIC']].to_string(index=False)]
    (OUT/'margin_exit_review.md').write_text('\n'.join(report),encoding='utf-8')
    print(score.to_string(index=False),flush=True)
    print(f'Margin scenarios reviewed {len(trades)} source trades; overnight expiry carry={carry.signal_id.nunique()}',flush=True)


def profit_trigger(profit,mode,level,arm_multiple=1.,trail_fraction=.25):
    """Return first completed-observation trigger; locking starts after arming."""
    profit=np.asarray(profit,dtype=float)
    if mode=='hard':return profit>=level
    maximum=np.maximum.accumulate(np.where(np.isfinite(profit),profit,-np.inf))
    # A first crossing arms the lock. Exit checks start at a later observation.
    prior=np.r_[-np.inf,maximum[:-1]]
    armed=prior>=level*arm_multiple
    floor=level if mode=='floor' else prior*(1-trail_fraction)
    return armed & (profit<=floor) & np.isfinite(profit)


def premium_target(path,basis,level):
    """Known observed premium only; an absent leg never becomes zero."""
    if basis=='none':return np.zeros(len(path),dtype=bool)
    column={'net':'net','gross':'gross','short':'short'}[basis]
    value=path[column].to_numpy(dtype=float)
    return np.isfinite(value)&(value<=level)


def rank_exit_trigger(alpha,alpha2,direction,basis,level,persistence=1):
    """Exit after consecutive observed ranks lose support for the held direction.

    Inputs start strictly after this position's entry. Missing ranks break a
    persistence run; these are trading observations, not elapsed wall minutes.
    """
    if direction not in (-1,1) or persistence not in (1,3,5):
        raise ValueError('Invalid rank-exit direction or persistence')
    a=np.asarray(alpha,dtype=float);b=np.asarray(alpha2,dtype=float)
    if a.shape!=b.shape or a.ndim!=1:raise ValueError('Unaligned exit ranks')
    if basis=='none':return np.zeros(len(a),dtype=bool)
    if basis not in ('alpha','alpha2','either','both'):raise ValueError('Unknown rank-exit basis')
    a=a if direction==1 else 1-a;b=b if direction==1 else 1-b
    left=a<level;right=b<level
    condition=left if basis=='alpha' else right if basis=='alpha2' else left|right if basis=='either' else left&right
    condition&=np.isfinite(a)&np.isfinite(b)
    return pd.Series(condition).rolling(persistence,min_periods=persistence).sum().eq(persistence).to_numpy()


def review_rank_exits():
    """Screen alpha exits with first-hit scoring, including earlier false exits."""
    seeds=(('main','423e6e825459ca2c'),('opening_atm','c6a30e15e1bbf4e8'),
           ('opening_volume','15b3eed5b443e0cd'),('boundaries','0868ced4b10c99d7'))
    trades=provider_trades();calendar=ProviderCalendar()
    paths=pd.read_csv(OUTPUT/'actual_contract_paths.csv.gz')
    paths.minute=pd.to_datetime(paths.minute,utc=True).dt.tz_convert(IST)
    coverage=pd.read_csv(OUTPUT/'exit_diagnostics.csv').set_index('signal_id')
    rules=[('none',0.,1)]+[(basis,level,n) for basis in ('alpha','alpha2','either','both')
        for level in (.8,.5,.2) for n in (1,3,5)]
    rows=[];observations=[]
    for family,cid in seeds:
        directory=OUT if family=='main' else OUT/family
        with np.load(directory/f'candidate_{cid}.npz',allow_pickle=False) as stored:
            index=pd.to_datetime(stored['minutes'],unit='ns',utc=True).tz_convert(IST)
            ranks=pd.DataFrame({'alpha':stored['alpha'],'alpha2':stored['alpha2']},index=index)
        for t in trades.itertuples():
            p=paths.loc[paths.signal_id.eq(t.signal_id)&(paths.minute>t.entry_minute)].sort_values('minute')
            selected=ranks.reindex(p.minute)
            a=selected.alpha.to_numpy();b=selected.alpha2.to_numpy()
            before=p.minute<=t.exit_minute
            rank_complete=bool(len(p) and np.isfinite(a[before]).all() and np.isfinite(b[before]).all())
            complete=bool(coverage.loc[t.signal_id,'complete_to_exit']) and bool(t.pnl_reconciles) and rank_complete
            entry_values=ranks.reindex([t.entry_minute]).iloc[0]
            exit_values=ranks.reindex([t.exit_minute]).iloc[0]
            observations.append({'candidate_id':cid,'family':family,'signal_id':t.signal_id,
                'entry':t.entry,'exit':t.exit,'option_type':t.option_type,'split':t.split,
                'entry_alpha':entry_values.alpha,'entry_alpha2':entry_values.alpha2,
                'exit_alpha':exit_values.alpha,'exit_alpha2':exit_values.alpha2,
                'original_spread_complete':bool(coverage.loc[t.signal_id,'complete_to_exit']),
                'ranks_complete_to_exit':rank_complete,'complete_to_exit':complete})
            day=min(calendar.next_trading_day(t.entry.date()),t.expiry) if t.entry.date()<t.expiry else t.expiry
            clock='15:00' if t.entry.date()<date(2026,7,1) else '14:53'
            due=pd.Timestamp(f'{day} {clock}',tz=IST)
            timed=(p.minute>=due).to_numpy()
            for basis,level,n in rules:
                rank_hit=rank_exit_trigger(a,b,t.direction,basis,level,n)
                for stop_basis in ('reported_margin','normal_margin'):
                    margin=t.margin_per_lot/(1.54 if stop_basis=='normal_margin' and t.entry.date()==t.expiry else 1.)
                    sl=p.net.to_numpy()>=t.credit+.05*margin/t.lot_size
                    for target in (0.,10.):
                        tp=premium_target(p,'none' if target==0 else 'net',target)
                        hit=np.flatnonzero(rank_hit|sl|tp|timed)
                        k=int(hit[0]) if len(hit) else None
                        ts=p.minute.iloc[k] if k is not None else pd.NaT
                        delta=(ts-t.exit_minute).total_seconds()/60 if k is not None else np.nan
                        recipe={'candidate_id':cid,'rank_basis':basis,'rank_support_below':level,
                            'persistence':n,'stop_basis':stop_basis,'net_target':target,'schedule':'dated'}
                        rows.append({'recipe':json.dumps(recipe,sort_keys=True),'signal_id':t.signal_id,'split':t.split,
                            **recipe,'complete_to_exit':complete,'first_exit':ts,'minutes_after_source_exit':delta,
                            'exact':bool(delta==0),'within_two_minutes':bool(abs(delta)<=2),'earlier':bool(delta < -2),
                            'not_observed':k is None,'reason':('stop' if sl[k] else 'target_net' if tp[k] else
                                'rank_'+basis if rank_hit[k] else 'time') if k is not None else 'not_observed'})
        print(f'Rank exits screened {family}/{cid}: {len(rules)*4} rules on {len(trades)} original positions',flush=True)
    evidence=pd.DataFrame(observations)
    eligible=evidence.groupby('signal_id').complete_to_exit.all()
    evidence['common_scoring_eligible']=evidence.signal_id.map(eligible)
    evidence.to_csv(OUT/'rank_exit_every_trade.csv',index=False)
    detail=pd.DataFrame(rows)
    detail['complete_to_exit']=detail.signal_id.map(eligible)
    detail.to_csv(OUT/'rank_exit_trials_per_trade.csv.gz',index=False)
    valid=detail.loc[detail.complete_to_exit]
    score=valid.groupby(['recipe','candidate_id','rank_basis','split'],sort=False).agg(
        trades=('signal_id','size'),exact=('exact','sum'),within_two_minutes=('within_two_minutes','sum'),
        earlier=('earlier','sum'),not_observed=('not_observed','sum')).reset_index()
    score.to_csv(OUT/'rank_exit_trials.csv',index=False)
    leaders=[];lines=['# Alpha and alpha2 exit hypotheses','',
        f'{detail.recipe.nunique()} recipes on four saved causal reconstructions. {valid.signal_id.nunique()}/210 original-spread paths have complete, reconciled prices and ranks for every candidate; every recipe uses this common sample.',
        '', 'Tests: exit when alpha, alpha2, either, or both have directional support below 0.8, 0.5 or 0.2 for 1, 3 or 5 consecutive trading observations. Bullish support equals rank; bearish support equals 1 minus rank. Missing ranks break persistence. Stops, net-10/no-target and the existing exit schedule remain matched controls.',
        '', '| Signal candidate | Rank recipe exact / within 2 min | Matched no-rank exact / within 2 min | Rank recipe early exits |',
        '|---|---:|---:|---:|']
    for family,cid in seeds:
        fit=score.loc[score.candidate_id.eq(cid)&score.split.eq('fit')&score.rank_basis.ne('none')]
        selected=fit.sort_values(['exact','within_two_minutes','earlier','recipe'],ascending=[False,False,True,True]).iloc[0].recipe
        rule=json.loads(selected);baseline={**rule,'rank_basis':'none','rank_support_below':0.,'persistence':1}
        chosen=valid.loc[valid.recipe.eq(selected)];control=valid.loc[valid.recipe.eq(json.dumps(baseline,sort_keys=True))]
        if set(chosen.signal_id)!=set(control.signal_id):raise ValueError('Rank and baseline coverage differ')
        leaders.append({'family':family,'candidate_id':cid,'recipe':rule,
            'exact':int(chosen.exact.sum()),'within_two_minutes':int(chosen.within_two_minutes.sum()),
            'earlier':int(chosen.earlier.sum()),'control_exact':int(control.exact.sum()),
            'control_within_two_minutes':int(control.within_two_minutes.sum())})
        lines.append(f'| {family} `{cid}` | {int(chosen.exact.sum())} / {int(chosen.within_two_minutes.sum())} | {int(control.exact.sum())} / {int(control.within_two_minutes.sum())} | {int(chosen.earlier.sum())} |')
    lines+=['','## Fit-selected rank rules','', '```json',json.dumps(leaders,indent=2),'```',
        '', '## Limits','',
        '- This is a source-conditioned exit screen, not an autonomous replication or an entry reset. Actual source entry credit and reported entry margin set stops; neither the future source exit nor P&L feeds a trigger.',
        '- Selection uses exact fit exit minutes, then fit matches within two minutes, then fewer fit early exits. Later periods were previously inspected and are not an untouched holdout.',
        '- Only the first modeled exit scores. A rank crossing at the source exit does not count if this rule would already have exited.',
        '- Paths include a diagnostic tail up to two minutes after the source exit; later quotes are never used to make an earlier decision. Minute-close prices cannot recover intraminute touches or broker RMS actions.',
        '- No production exit rule or sizing changed.', '', 'Reproduce from `zen_credit/`: `..\\.venv\\Scripts\\python.exe -B -u -m backtest.provider_exit_trials --rank-exits`.']
    (OUT/'rank_exit_review.md').write_text('\n'.join(lines),encoding='utf-8')
    (OUT/'rank_exit_selected.json').write_text(json.dumps(leaders,indent=2),encoding='utf-8')
    print(json.dumps(leaders,indent=2),flush=True)


def review_premium_exits(fractional=False):
    """Net-spread, gross-premium and sold-option targets versus no target."""
    OUT.mkdir(exist_ok=True)
    trades=provider_trades();calendar=ProviderCalendar()
    paths=pd.read_csv(OUTPUT/'actual_contract_paths.csv.gz')
    paths.minute=pd.to_datetime(paths.minute,utc=True).dt.tz_convert(IST)
    coverage=pd.read_csv(OUTPUT/'exit_diagnostics.csv').set_index('signal_id')
    recipes=([(basis,level,'entry_fraction') for basis in ('net','gross','short') for level in (.05,.10,.15,.20,.25,.50)]+[('none',0.,'absolute'),('net',10.,'absolute')]
        if fractional else [(basis,level,'absolute') for basis in ('net','gross','short') for level in (5.,10.,15.,20.)]+[('none',0.,'absolute')])
    stem='premium_fraction_exit' if fractional else 'premium_exit'
    rows=[]
    for t in trades.itertuples():
        p=paths.loc[paths.signal_id.eq(t.signal_id)&(paths.minute>t.entry_minute)].sort_values('minute')
        complete=bool(coverage.loc[t.signal_id,'complete_to_exit']) and bool(t.pnl_reconciles)
        day=min(calendar.next_trading_day(t.entry.date()),t.expiry) if t.entry.date()<t.expiry else t.expiry
        for stop_basis in ('reported_margin','normal_margin'):
            margin=t.margin_per_lot/(1.54 if stop_basis=='normal_margin' and t.entry.date()==t.expiry else 1.)
            stop=t.credit+.05*margin/t.lot_size
            sl=p.net.to_numpy()>=stop
            for basis,level,units in recipes:
                opening_premium={'net':t.credit,'gross':t.short_entry+t.hedge_entry,'short':t.short_entry,'none':0.}[basis]
                threshold=level*opening_premium if units=='entry_fraction' else level
                tp=premium_target(p,basis,threshold)
                for schedule in ('dated','14:53','15:00'):
                    clock=('15:00' if t.entry.date()<date(2026,7,1) else '14:53') if schedule=='dated' else schedule
                    due=pd.Timestamp(f'{day} {clock}',tz=IST)
                    hit=np.flatnonzero(sl|tp|(p.minute>=due).to_numpy())
                    k=int(hit[0]) if len(hit) else None
                    ts=p.minute.iloc[k] if k is not None else pd.NaT
                    delta=(ts-t.exit_minute).total_seconds()/60 if k is not None else np.nan
                    recipe={'target_basis':basis,'target_level':level,'stop_basis':stop_basis,'schedule':schedule}
                    if fractional:recipe['target_units']=units
                    rows.append({'recipe':json.dumps(recipe,sort_keys=True),'signal_id':t.signal_id,'split':t.split,**recipe,
                        'complete_to_exit':complete,'first_exit':ts,'minutes_after_source_exit':delta,
                        'exact':bool(delta==0),'within_two_minutes':bool(abs(delta)<=2),'earlier':bool(delta < -2),
                        'not_observed':k is None,'reason':('stop' if sl[k] else 'target_'+basis if tp[k] else 'time') if k is not None else 'not_observed',
                        'missing_short_observations':int(p.short.isna().sum()),'missing_spread_observations':int(p.net.isna().sum()),
                        'source_entry':t.entry,'source_exit':t.exit,'source_short_exit':t.short_exit,
                        'source_net_exit':t.debit,'source_gross_exit':t.gross_exit_premium,'source_pnl':t.pnl_reported,
                        'target_in_premium_points':threshold})
    detail=pd.DataFrame(rows);detail.to_csv(OUT/f'{stem}_trials_per_trade.csv.gz',index=False)
    valid=detail.loc[detail.complete_to_exit]
    score=valid.groupby(['recipe','split'],sort=False).agg(trades=('signal_id','size'),exact=('exact','sum'),
        within_two_minutes=('within_two_minutes','sum'),earlier=('earlier','sum'),not_observed=('not_observed','sum')).reset_index()
    score.to_csv(OUT/f'{stem}_trials.csv',index=False)
    fit=score.loc[score.split.eq('fit')].sort_values(['exact','within_two_minutes','earlier'],ascending=[False,False,True])
    selected=fit.iloc[0].recipe
    shown=score.loc[score.recipe.eq(selected)]
    r=json.loads(selected)
    baseline=valid.loc[valid.target_basis.eq('net')&valid.target_level.eq(10)&valid.stop_basis.eq('normal_margin')&valid.schedule.eq('dated')]
    best=valid.loc[valid.recipe.eq(selected)]
    targeted=trades.loc[(trades.entry.dt.date==date(2026,2,9))|trades.signal_id.isin(trades.tail(2).signal_id)]
    if fractional:
        levels=(detail.target_level.eq(.1)&detail.target_units.eq('entry_fraction'))|(detail.target_level.eq(10)&detail.target_basis.eq('net'))|detail.target_basis.eq('none')
    else:
        levels=(detail.target_level.eq(10)&detail.target_basis.eq('net'))|(detail.target_level.eq(15)&detail.target_basis.isin(['gross','short']))|detail.target_basis.eq('none')
    case=detail.loc[detail.signal_id.isin(targeted.signal_id)&detail.target_basis.isin(['net','gross','short','none'])&levels&
        detail.stop_basis.eq('normal_margin')&detail.schedule.eq('dated')]
    case.to_csv(OUT/f'{stem}_case_comparison.csv',index=False)
    lines=['# Premium target fractions' if fractional else '# Premium target interpretations','',
        f'{detail.recipe.nunique()} exit recipes checked against all {len(trades)} source trades; only {valid.signal_id.nunique()} complete, reconciled paths contribute scores.',
        '', 'Fit-selected recipe:', '', '```json',json.dumps(r,indent=2),'```','',shown.to_string(index=False),'',
        f'Across scored paths: selected exact {int(best.exact.sum())}, within two minutes {int(best.within_two_minutes.sum())}; net-10 / normal-margin / dated baseline exact {int(baseline.exact.sum())}, within two minutes {int(baseline.within_two_minutes.sum())}.',
        '', '## Scope','',
        '- Source-conditioned exit diagnostics, not autonomous replay. Actual entry fills set entry credit and stop. Positions are not generated by these rules.',
        '- Targets test net spread, sum of both premiums, sold-option premium, or no target. Stops remain 5% of margin on the net spread. All recipes get the same complete-path sample.',
        '- Sold-option targets can be observed when a hedge quote is missing, but such incomplete paths remain excluded: an earlier spread stop cannot be ruled out.',
        '- Minute-close prices miss intraminute touches and differ from exact fills. The existing two-minute post-source-exit diagnostic tail is available for late modeled triggers, not for decisions at the source exit.',
        '- Fit selection uses the earliest chronological period. Later dates were already inspected and are not an untouched holdout.',
        '- A target interpretation does not establish broker liquidation. No production target or margin-sizing rule has changed.',
        '- In the fraction bank, 0.10 means the remaining premium is 10% of its entry value (90% decay), not a 10% return on account margin.' if fractional else '- Target levels are absolute premium points.',
        '', '## Selected case comparisons','',case[['source_entry','source_exit','target_basis','target_level','target_in_premium_points','complete_to_exit','first_exit','minutes_after_source_exit','reason']].to_string(index=False)]
    (OUT/f'{stem}_review.md').write_text('\n'.join(lines),encoding='utf-8')
    print(f'Premium-exit recipes: {detail.recipe.nunique()}; complete paths: {valid.signal_id.nunique()}',flush=True)
    print(shown.to_string(index=False),flush=True)
    print(case[['source_entry','target_basis','target_level','complete_to_exit','first_exit','minutes_after_source_exit','reason']].to_string(index=False),flush=True)


def main():
    OUT.mkdir(exist_ok=True)
    trades=provider_trades();calendar=ProviderCalendar()
    paths=pd.read_csv(OUTPUT/'actual_contract_paths.csv.gz')
    paths.minute=pd.to_datetime(paths.minute,utc=True).dt.tz_convert(IST)
    coverage=pd.read_csv(OUTPUT/'exit_diagnostics.csv').set_index('signal_id')
    rows=[]
    for t in trades.itertuples():
        p=paths.loc[paths.signal_id.eq(t.signal_id)&(paths.minute>t.entry_minute)].sort_values('minute')
        complete=bool(coverage.loc[t.signal_id,'complete_to_exit']) and bool(t.pnl_reconciles)
        profit=(t.credit-p.net.to_numpy())*t.lot_size/t.margin_per_lot
        day=min(calendar.next_trading_day(t.entry.date()),t.expiry) if t.entry.date()<t.expiry else t.expiry
        for stop_basis in ('reported_margin','normal_margin'):
            stop=.05/(1.54 if stop_basis=='normal_margin' and t.entry.date()==t.expiry else 1.)
            for mode in ('hard','floor','trail'):
                for level in (.05,.10,.15):
                    for arm in ((1.,1.25,1.5) if mode=='floor' else (1.,)):
                        for trail in ((.1,.25,.5) if mode=='trail' else (.25,)):
                            tp=profit_trigger(profit,mode,level,arm,trail)
                            sl=profit<=-stop
                            for schedule in ('dated','14:53','15:00'):
                                clock=('15:00' if t.entry.date()<date(2026,7,1) else '14:53') if schedule=='dated' else schedule
                                due=pd.Timestamp(f'{day} {clock}',tz=IST)
                                hit=np.flatnonzero(tp|sl|(p.minute>=due).to_numpy())
                                k=hit[0] if len(hit) else None
                                ts=p.minute.iloc[k] if k is not None else pd.NaT
                                delta=(ts-t.exit_minute).total_seconds()/60 if pd.notna(ts) else np.nan
                                recipe={'profit_mode':mode,'level':level,'arm_multiple':arm,'trail_fraction':trail,'stop_basis':stop_basis,'schedule':schedule}
                                rows.append({'recipe':json.dumps(recipe,sort_keys=True),'signal_id':t.signal_id,'split':t.split,**recipe,
                                    'complete_to_exit':complete,'first_exit':ts,'minutes_after_source_exit':delta,
                                    'exact':bool(delta==0),'within_two_minutes':bool(abs(delta)<=2),
                                    'earlier':bool(delta < -2),'not_observed':bool(k is None),
                                    'reason':('stop' if sl[k] else 'profit_'+mode if tp[k] else 'time') if k is not None else 'not_observed'})
    details=pd.DataFrame(rows);details.to_csv(OUT/'exit_rule_trials_per_trade.csv.gz',index=False)
    valid=details.loc[details.complete_to_exit]
    score=valid.groupby(['recipe','split'],sort=False).agg(trades=('signal_id','size'),exact=('exact','sum'),within_two_minutes=('within_two_minutes','sum'),earlier=('earlier','sum'),not_observed=('not_observed','sum')).reset_index()
    score.to_csv(OUT/'exit_rule_trials.csv',index=False)
    fit=score.loc[score.split.eq('fit')].sort_values(['exact','within_two_minutes','earlier'],ascending=[False,False,True])
    print(f'Complete, reconciled paths: {valid.signal_id.nunique()}/{len(trades)}; recipes: {details.recipe.nunique()}',flush=True)
    print(fit.head(8).to_string(index=False),flush=True)
    last=trades.tail(2).signal_id
    print(details.loc[details.signal_id.isin(last)&details.profit_mode.eq('floor')&details.level.eq(.1)&details.arm_multiple.eq(1)&details.schedule.eq('dated')&details.stop_basis.eq('normal_margin'),['signal_id','complete_to_exit','first_exit','minutes_after_source_exit','reason']].to_string(index=False),flush=True)
    (OUT/'exit_trial_design.json').write_text(json.dumps({'coverage':int(valid.signal_id.nunique()),'trades':len(trades),'recipes':int(details.recipe.nunique()),
        'limitation':'These are source-conditioned original-spread paths, censored two minutes after reported exit; not autonomous replays. Incomplete paths excluded from score. Margin is the historical margin reported in the source ledger. Current-minute intrabar touches and fills cannot be inferred from minute closes. Later dates previously inspected; no untouched holdout.',
        'selection':'fit exact, then fit within two minutes; all later splits reported'},indent=2))


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--margin',action='store_true',help='Screen possible expiry margin shortfalls without changing strategy sizing')
    parser.add_argument('--premium-exits',action='store_true',help='Compare targets on net spread, gross premiums or the sold option')
    parser.add_argument('--september-bounds',action='store_true',help='Bound the missing September hedge using an observed lower-strike call; diagnostic only')
    parser.add_argument('--premium-fractions',action='store_true',help='Compare targets as fractions of entry net, gross or sold-option premiums')
    parser.add_argument('--rank-exits',action='store_true',help='Compare alpha/alpha2 loss-of-support exits with matched no-rank controls')
    args=parser.parse_args()
    if sum((args.margin,args.premium_exits,args.september_bounds,args.premium_fractions,args.rank_exits))>1:parser.error('Select one exit diagnostic')
    review_rank_exits() if args.rank_exits else review_premium_exits(True) if args.premium_fractions else review_september_exit_bounds() if args.september_bounds else review_premium_exits() if args.premium_exits else review_margin_exits() if args.margin else main()
