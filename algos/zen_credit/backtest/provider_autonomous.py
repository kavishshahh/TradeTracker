"""Resumable, bounded-memory full-history replay with positions carried across chunks."""
from collections import Counter
from dataclasses import asdict,replace
from datetime import datetime,date,time
import argparse
import gc
import json
import numpy as np
import pandas as pd
from backtest.provider_trials import OUT,SPLITS,threshold_config,apply_research_gates
from backtest.provider_research import history_blocks,provider_trades
from backtest.provider_calendar import ProviderCalendar,expiries_for,lot_size,history_config
from backtest.dhan_history import DhanHistoryClient
from backtest.dhan_replay import DhanReplay,load_history,supplement_fixed_contracts,mark_open_trades,prepare_option_quotes
from backtest.nse_settlement import NSESettlementClient
from strategy.engine import Position
from config import StrategyConfig
from utils.time import IST


def restore_position(data):
    if data is None:return None
    data=dict(data)
    for key in ('entry_ts','exit_due'):data[key]=datetime.fromisoformat(data[key])
    data['expiry']=date.fromisoformat(data['expiry'])
    return Position(**data)


def normalize_trades(frame):
    if frame.empty:return frame
    frame=frame.copy()
    for key in ('entry_ts','exit_ts','scheduled_exit','exit_observed_ts','effective_exit_ts'):
        if key in frame:frame[key]=pd.to_datetime(frame[key],utc=True).dt.tz_convert(IST)
    frame.expiry=pd.to_datetime(frame.expiry).dt.date
    return frame


def performance_ledger(frame,start,end,position=None):
    """Select the ledger known by an observation date; future exits stay open."""
    first=pd.Timestamp(start).date();last=pd.Timestamp(end).date()
    first_stamp=pd.Timestamp(first,tz=IST)
    end_stamp=pd.Timestamp(last,tz=IST)+pd.Timedelta(days=1)
    result=frame.copy()
    for column in ('entry_ts','exit_ts','pnl'):
        if column not in result:result[column]=pd.Series(dtype=object)
    entries=pd.to_datetime(result.entry_ts,utc=True).dt.tz_convert(IST)
    exits=pd.to_datetime(result.exit_ts,utc=True).dt.tz_convert(IST)
    result['entry_ts']=entries;result['exit_ts']=exits
    eligible=entries.ge(first_stamp)&entries.lt(end_stamp)
    result=result.loc[eligible].copy();exits=exits.loc[eligible]
    # Earlier closed positions do not belong in this period; later closes were
    # not known at its endpoint and cannot provide realized P&L or an MTM mark.
    result=result.loc[exits.isna()|exits.ge(first_stamp)].copy()
    later=exits.reindex(result.index).ge(end_stamp)
    # Settlement can be booked at expiry close but only observed next session.
    # A prefix report must not use that later observation to close an earlier day.
    if 'exit_observed_ts' in result:
        observed=pd.to_datetime(result.exit_observed_ts,utc=True).dt.tz_convert(IST)
        later |= observed.ge(end_stamp)
    result.loc[later,'exit_ts']=None;result.loc[later,'pnl']=None
    for column in ('unrealized_pnl','valuation_ts'):
        if column in result:result.loc[later,column]=None
    if position:
        stamp=pd.Timestamp(position['entry_ts'])
        if stamp.tzinfo is None:raise ValueError('Carried position timestamp must be timezone aware')
        stamp=stamp.tz_convert(IST)
        present=pd.to_datetime(result.entry_ts,utc=True).eq(stamp.tz_convert('UTC')).any()
        if first<=stamp.date()<=last and not present:
            result=pd.concat([result,pd.DataFrame([{'entry_ts':stamp,'exit_ts':None,'pnl':None}])],ignore_index=True)
    return result


def write_trial_performance(target,frame,capital,start,end,position=None,metadata=None,source=None):
    """Gross period statistics and a Zen comparison on exactly the same dates."""
    from backtest.metrics import compute_period_performance
    ledger=performance_ledger(frame,start,end,position)
    performance=compute_period_performance(ledger,capital,start,end)
    published=provider_trades() if source is None else source
    source_ledger=published.rename(columns={'entry':'entry_ts','exit':'exit_ts','pnl_reported':'pnl'})
    zen=compute_period_performance(performance_ledger(source_ledger,start,end),capital,start,end)
    payload={'performance':performance,'zen_same_period':zen,'metadata':metadata or {},
        'comparison_policy':'Same inclusive IST observation dates and capital; only entries since the start. P&L booked on exit date. Published Zen uses reported P&L without changing fills or dates.',
        'limitations':['Trial values are gross before brokerage, taxes, slippage and funding; published Zen fee basis is undisclosed.',
            'CAGR annualizes ending realized value on fixed capital; trade sizing did not compound.',
            'Open MTM is separate and unknown when no endpoint mark exists. Realized drawdown excludes intratrade losses.',
            'Missing quotes, historical margin assumptions and RMS liquidation can affect results. A high in-sample return is not evidence of a deployable advantage.']}
    (target/'performance.json').write_text(json.dumps(payload,indent=2,allow_nan=False,default=str))
    monthly=pd.DataFrame(performance['monthly'])
    zen_monthly=pd.DataFrame(zen['monthly'])[['month','pnl','return_pct','closed_trades','win_rate_pct']]
    zen_monthly=zen_monthly.rename(columns={c:'zen_'+c for c in zen_monthly if c!='month'})
    monthly=monthly.merge(zen_monthly,on='month',validate='one_to_one')
    monthly['excess_pnl_vs_zen']=monthly.pnl-monthly.zen_pnl
    monthly.to_csv(target/'performance_monthly.csv',index=False)
    return payload


def backfill_performance_reports():
    """Summarize committed replays without rerunning or altering their outcomes."""
    source=provider_trades();rows=[];months=[];excluded=[]
    paths=sorted(OUT.rglob('checkpoint.json'))
    states={path:json.loads(path.read_text()) for path in paths}
    common_end=min(pd.Timestamp(state['last_decision']).tz_convert(IST).date()
        for path,state in states.items() if 'unresolved_settlement' not in path.parent.name
        and state.get('completed_blocks',0)>0 and state.get('last_decision'))
    for checkpoint in paths:
        target=checkpoint.parent
        # This preserved diagnostic ran before the settlement archive was
        # recovered and is explicitly excluded in the existing research audit.
        if 'unresolved_settlement' in target.name:
            excluded.append({'path':str(target),'reason':'Known invalid unresolved-settlement control'});continue
        state=states[checkpoint];completed=state.get('completed_blocks',0)
        if not completed or not state.get('last_decision'):
            excluded.append({'path':str(target),'reason':'No committed observed replay period'});continue
        frame=normalize_trades(pd.DataFrame(state['trades'])) if 'trades' in state else normalize_trades(pd.read_csv(target/'trades.csv'))
        start=pd.Timestamp(state['entry_start']).tz_convert(IST).date()
        end=pd.Timestamp(state['last_decision']).tz_convert(IST).date()
        cid=state['candidate']['candidate_id'];capital=state['config']['capital']
        total=len(state.get('history_blocks') or history_blocks())
        metadata={'candidate_id':cid,'family':str(target.parent.relative_to(OUT)),
            'execution_style':target.name.rsplit('_',1)[-1],'completed_blocks':completed,'total_blocks':total,
            'complete_history':completed==total,'ledger_source':'checkpoint trades' if 'trades' in state else 'legacy trade CSV',
            'alpha_recipe':state['candidate'].get('alpha'),
            'volatility':state['candidate']['recipe'].get('volatility'),
            'volume_kind':state['candidate']['recipe'].get('volume_kind'),
            'factor_context':state['candidate']['recipe'].get('context'),
            'profit_target_mode':state['candidate']['recipe'].get('profit_target_mode','configured'),
            'reentry_after_exit':state['candidate']['recipe'].get('reentry_after_exit',False),
            'missing_held_quote_minutes':sum(state.get('gap_minutes_by_entry',{}).values())}
        payload=write_trial_performance(target,frame,capital,start,end,state.get('position'),metadata,source)
        report_path=target/'report.json'
        if report_path.exists():
            report=json.loads(report_path.read_text());report['performance']=payload['performance']
            report['zen_same_period_performance']=payload['zen_same_period']
            report_path.write_text(json.dumps(report,indent=2,default=str))
        scopes=[('observed',payload)]
        cutoff=date(2026,2,28)
        if start<=cutoff<=end:
            # Independent fit-period performance; future closes become unknown
            # open positions and cannot leak their eventual P&L into February.
            from backtest.metrics import compute_period_performance
            fit={'performance':compute_period_performance(performance_ledger(frame,start,cutoff,state.get('position')),capital,start,cutoff),
                'zen_same_period':compute_period_performance(performance_ledger(source.rename(columns={'entry':'entry_ts','exit':'exit_ts','pnl_reported':'pnl'}),start,cutoff),capital,start,cutoff)}
            (target/'performance_fit.json').write_text(json.dumps(fit,indent=2,allow_nan=False,default=str))
            scopes.append(('fit',fit))
        from backtest.metrics import compute_period_performance
        common={'performance':compute_period_performance(performance_ledger(frame,start,common_end,state.get('position')),capital,start,common_end),
            'zen_same_period':compute_period_performance(performance_ledger(source.rename(columns={'entry':'entry_ts','exit':'exit_ts','pnl_reported':'pnl'}),start,common_end),capital,start,common_end)}
        (target/'performance_common.json').write_text(json.dumps(common,indent=2,allow_nan=False,default=str))
        scopes.append(('common',common))
        for scope,data in scopes:
            p=data['performance'];z=data['zen_same_period']
            row={**metadata,'scope':scope,'path':str(target)}
            for key in ('period_start','period_end','capital','trade_count','winning_trades','losing_trades','breakeven_trades','win_rate_pct','total_pnl','total_return_pct','cagr_pct','return_1m_pct','return_3m_pct','return_6m_pct','max_drawdown_pct','profit_factor','open_trade_count','open_mtm_pnl','open_mtm_status'):
                row[key]=p[key]
            for key in ('trade_count','win_rate_pct','total_pnl','total_return_pct','cagr_pct','return_1m_pct','return_3m_pct','return_6m_pct','max_drawdown_pct'):
                row['zen_'+key]=z[key]
            row['excess_pnl_vs_zen']=p['total_pnl']-z['total_pnl'];rows.append(row)
            for month in p['monthly']:
                zen_month=next(m for m in z['monthly'] if m['month']==month['month'])
                months.append({**metadata,'scope':scope,**month,'zen_pnl':zen_month['pnl'],'zen_return_pct':zen_month['return_pct'],
                    'excess_pnl_vs_zen':month['pnl']-zen_month['pnl']})
    weekly_paths=sorted(path for path in OUT.rglob('report.json')
        if path.parent.name.startswith('autonomous_') and not (path.parent/'checkpoint.json').exists())
    for path in weekly_paths:
        target=path.parent;report=json.loads(path.read_text())
        decisions=pd.read_csv(target/'decisions.csv.gz',usecols=['minute'])
        clock=pd.to_datetime(decisions.minute,utc=True).dt.tz_convert(IST)
        start=clock.min().date();end=clock.max().date()
        frame=normalize_trades(pd.read_csv(target/'trades.csv'))
        recipe=report['candidate']['recipe']
        metadata={'candidate_id':report['candidate']['candidate_id'],'family':str(target.parent.relative_to(OUT)),
            'execution_style':report['result']['execution_style'],'complete_history':False,
            'period_kind':'recent-week; starts flat','alpha_recipe':report['candidate'].get('alpha'),
            'volatility':recipe.get('volatility'),'volume_kind':recipe.get('volume_kind'),
            'factor_context':recipe.get('context'),'profit_target_mode':recipe.get('profit_target_mode','configured'),
            'reentry_after_exit':recipe.get('reentry_after_exit',False),
            'missing_held_quote_minutes':report['result'].get('missing_held_quote_minutes')}
        payload=write_trial_performance(target,frame,report['config']['capital'],start,end,metadata=metadata,source=source)
        p=payload['performance'];z=payload['zen_same_period'];report['performance']=p;report['zen_same_period_performance']=z
        path.write_text(json.dumps(report,indent=2,default=str))
        row={**metadata,'scope':'recent_week','path':str(target)}
        for key in ('period_start','period_end','capital','trade_count','winning_trades','losing_trades','breakeven_trades','win_rate_pct','total_pnl','total_return_pct','cagr_pct','return_1m_pct','return_3m_pct','return_6m_pct','max_drawdown_pct','profit_factor','open_trade_count','open_mtm_pnl','open_mtm_status'):
            row[key]=p[key]
        for key in ('trade_count','win_rate_pct','total_pnl','total_return_pct','cagr_pct','return_1m_pct','return_3m_pct','return_6m_pct','max_drawdown_pct'):
            row['zen_'+key]=z[key]
        row['excess_pnl_vs_zen']=p['total_pnl']-z['total_pnl'];rows.append(row)
        for month in p['monthly']:
            zen_month=next(m for m in z['monthly'] if m['month']==month['month'])
            months.append({**metadata,'scope':'recent_week',**month,'zen_pnl':zen_month['pnl'],
                'zen_return_pct':zen_month['return_pct'],'excess_pnl_vs_zen':month['pnl']-zen_month['pnl']})
    comparison=pd.DataFrame(rows);comparison.to_csv(OUT/'performance_comparison.csv',index=False)
    pd.DataFrame(months).to_csv(OUT/'performance_monthly.csv',index=False)
    from backtest.dhan_replay import write_replay_performance
    ordinary=[]
    for path in sorted(OUT.parent.parent.glob('*/report.json')):
        report=json.loads(path.read_text())
        if 'entry_start' not in report:continue
        asof=report.get('valuation_asof')
        if not asof and (path.parent/'decisions.csv.gz').exists():
            decisions=pd.read_csv(path.parent/'decisions.csv.gz',usecols=['minute'])
            if not decisions.empty:asof=pd.to_datetime(decisions.minute,utc=True).max()
        if not asof:continue
        frame=pd.read_csv(path.parent/'trades.csv')
        performance=write_replay_performance(path.parent,frame,report['config']['capital'],
            report['entry_start'],pd.Timestamp(asof).tz_convert(IST).date())
        report['period_performance']=performance;path.write_text(json.dumps(report,indent=2,default=str))
        ordinary.append(str(path.parent))
    (OUT/'performance_report_design.json').write_text(json.dumps({'checkpoint_replays':len(paths),'reported_replays':len(paths)-len(excluded),
        'recent_week_replays':len(weekly_paths),'common_period_end':str(common_end),
        'ordinary_replay_reports':ordinary,
        'excluded':excluded,'scope':'Observed committed period plus separate fit period. Gross closed-trade results; all windows use calendar dates and fixed capital.',
        'selection':'Comparison report only; no automatic promotion or replication claim.'},indent=2))
    print(json.dumps({'reported_replays':len(paths)-len(excluded),'recent_week_replays':len(weekly_paths),
        'ordinary_replays':len(ordinary),'common_period_end':str(common_end),
        'comparison_rows':len(rows),'monthly_rows':len(months),'excluded':excluded},indent=2),flush=True)
    return comparison


def compare(frame,source,gaps):
    frame=normalize_trades(frame);matches=[]
    for t in source.itertuples():
        possible=frame.loc[(frame.entry_ts==t.entry_minute)&frame.option_type.eq(t.option_type)&
            frame.sell_strike.eq(t.short_strike)&frame.buy_strike.eq(t.hedge_strike)&frame.expiry.eq(t.expiry)] if not frame.empty else frame
        matched=not possible.empty
        exact_exit=matched and pd.notna(possible.iloc[0].exit_ts) and possible.iloc[0].exit_ts==t.exit_minute
        matches.append({'signal_id':t.signal_id,'split':t.split,'source_entry':t.entry,'source_exit':t.exit,
            'option_type':t.option_type,'short_strike':t.short_strike,'hedge_strike':t.hedge_strike,'expiry':t.expiry,
            'exact_entry_direction_strikes_expiry':matched,'exact_exit_for_exact_entry':bool(exact_exit),
            'simulated_exit':possible.iloc[0].exit_ts if matched else None,
            'missing_quotes_after_matched_entry':gaps.get(t.entry_minute.isoformat(),0) if matched else None})
    evidence=pd.DataFrame(matches)
    paired=int(evidence.exact_entry_direction_strikes_expiry.sum())
    return evidence,{'source_trades':len(source),'simulated_entries':len(frame),'exact_entries':paired,
        'exact_exits_for_exact_entries':int(evidence.exact_exit_for_exact_entry.sum()),'extra_entries':len(frame)-paired,
        'missing_source_entries':len(source)-paired,'missing_held_quote_minutes':sum(gaps.values()),
        'open_positions':int(frame.exit_ts.isna().sum()) if not frame.empty else 0}


def _prepare_candidate(candidate,trial_dir,style,source,blocks,restart):
    cid=candidate['candidate_id'];target=trial_dir/f'full_autonomous_{cid}_{style}';target.mkdir(exist_ok=True)
    cfg=StrategyConfig()
    if style=='ledger':cfg=replace(cfg,strike_reference='last_bar_open',max_short_premium=200,monday_capital_fraction=.8)
    cfg=threshold_config(cfg,candidate['recipe'].get('threshold_comparison','strict'))
    cfg=history_config(cfg)
    with np.load(trial_dir/f'candidate_{cid}.npz',allow_pickle=False) as data:
        idx=pd.to_datetime(data['minutes'],unit='ns',utc=True).tz_convert(IST)
        indicators=pd.DataFrame({'alpha':data['alpha'],'alpha2':data['alpha2']},index=idx)
    entry_start=datetime.combine(source.entry.min().date(),time.min,IST)
    # Permit extra entries through the final source EXIT date too. Cutting at
    # the last source entry date would hide false entries on the following day.
    entry_end=datetime.combine(source.exit.max().date(),time.max,IST)
    state_path=target/'checkpoint.json';position=None;details={};last_decision=None;completed=0;gaps=Counter();frames=[]
    if state_path.exists() and not restart:
        state=json.loads(state_path.read_text())
        if state.get('entry_start')!=entry_start.isoformat() or state.get('entry_end')!=entry_end.isoformat():
            raise ValueError('Replay period changed; use --restart to rebuild this generated research result')
        if state['candidate']!=candidate or state['config']!=json.loads(json.dumps(asdict(cfg),default=str)):
            raise ValueError('Checkpoint candidate/config changed; preserve this experiment and use a new output identity')
        completed=state['completed_blocks'];position=restore_position(state['position'])
        if not isinstance(completed,int) or not 0<=completed<=len(blocks):
            raise ValueError('Checkpoint has an invalid completed chunk count')
        if 'history_blocks' in state and state['history_blocks']!=[[str(a),str(b)] for a,b in blocks]:
            raise ValueError('Checkpoint historical chunks changed; use a new replay identity')
        details={datetime.fromisoformat(k):v for k,v in state['trade_details'].items()}
        last_decision=datetime.fromisoformat(state['last_decision']) if state['last_decision'] else None
        gaps=Counter(state['gap_minutes_by_entry'])
        # New checkpoints own their committed trades. A failed subsequent chunk
        # may already have overwritten trades.csv before its checkpoint commits.
        if 'trades' in state:
            frames=[normalize_trades(pd.DataFrame(state['trades']))] if state['trades'] else []
        elif (target/'trades.csv').exists() and (target/'trades.csv').stat().st_size>1:
            frames=[normalize_trades(pd.read_csv(target/'trades.csv'))]
        print(f'Resuming full autonomous candidate {cid} after {completed}/{len(blocks)} blocks',flush=True)
    return dict(candidate=candidate,target=target,cfg=cfg,indicators=indicators,entry_start=entry_start,
        entry_end=entry_end,state_path=state_path,position=position,details=details,last_decision=last_decision,
        completed=completed,gaps=gaps,frames=frames,tested=0)


def _advance_candidate(state,bars,options,number,first,blocks,source,calendar,required_settlement,style,prepared_quotes=None):
        candidate=state['candidate'];cid=candidate['candidate_id'];cfg=state['cfg'];target=state['target']
        entry_start=state['entry_start'];entry_end=state['entry_end'];gaps=state['gaps'];frames=state['frames']
        replay=DhanReplay(cfg,bars,options,settlement_loader=required_settlement,calendar=calendar,expiry_resolver=expiries_for,lot_resolver=lot_size,prepared_quotes=prepared_quotes)
        replay._indicator_frame=lambda:state['indicators']
        apply_research_gates(replay,candidate)
        replay.trade_details=state['details'];replay._last_decision=state['last_decision']
        result=replay.run(start=entry_start,entry_end=entry_end,initial_position=state['position'],include_open_trade=number==len(blocks)-1,
                         reentry_after_exit=candidate['recipe'].get('reentry_after_exit',False))
        position=result.final_position;last_decision=result.last_decision or state['last_decision'];details=replay.trade_details
        part=result.to_frame()
        if not part.empty:
            for key in ('sell_leg_entry','buy_leg_entry','sell_leg_exit','buy_leg_exit','scheduled_exit','exit_observed_ts','effective_exit_ts'):
                part[key]=[details[t].get(key) for t in part.entry_ts]
            part.exit_ts=[details[t].get('effective_exit_ts',e) for t,e in zip(part.entry_ts,part.exit_ts)]
            mark_open_trades(part,replay,result.last_decision)
            frames.append(part)
        gaps.update(e['entry_ts'] for e in replay.coverage_events)
        pd.DataFrame(replay.decisions).to_csv(target/f'decisions_{first}.csv.gz',index=False)
        pd.DataFrame(replay.coverage_events).to_csv(target/f'missing_quotes_{first}.csv.gz',index=False)
        frame=normalize_trades(pd.concat(frames,ignore_index=True)) if frames else pd.DataFrame()
        frame.to_csv(target/'trades.csv',index=False)
        evidence,metrics=compare(frame,source,gaps)
        evidence.to_csv(target/'source_trade_comparison.csv',index=False)
        metrics.update({'candidate_id':cid,'completed_blocks':number+1,'total_blocks':len(blocks),'complete_history':number+1==len(blocks),
            'entry_start_inclusive':entry_start,'entry_end_inclusive':entry_end,
            'execution_style':style,'settlements':'Official NSE final settlement after expiry; no source position resets',
            'limitations':['Minute close quotes approximate exact source fills. Missing original quotes can delay exits and suppress subsequent entries.',
                'Published broker margin unavailable independently; reconstruction sizing and 5% stop remain assumptions.',
                'Source entry/exit dates used only for comparison and period bounds. Positions carry through each raw-data chunk.',
                'Selection uses earlier fit data, but later periods were previously inspected and are not untouched.']})
        performance=write_trial_performance(target,frame,cfg.capital,entry_start.date(),pd.Timestamp(last_decision).date(),
            asdict(position) if position else None,
            {'candidate_id':cid,'completed_blocks':number+1,'total_blocks':len(blocks),
             'complete_history':number+1==len(blocks),'missing_held_quote_minutes':sum(gaps.values())},source)
        (target/'report.json').write_text(json.dumps({'result':metrics,'candidate':candidate,'config':asdict(cfg),
            'performance':performance['performance'],'zen_same_period_performance':performance['zen_same_period']},indent=2,default=str))
        checkpoint={'candidate':candidate,'config':asdict(cfg),'completed_blocks':number+1,'position':asdict(position) if position else None,
            'entry_start':entry_start.isoformat(),'entry_end':entry_end.isoformat(),
            'trade_details':{k.isoformat():v for k,v in details.items()},'last_decision':last_decision,'gap_minutes_by_entry':dict(gaps),
            'history_blocks':[[str(a),str(b)] for a,b in blocks],'trades':frame.to_dict('records')}
        state_path=state['state_path']
        temp=state_path.with_suffix('.tmp');temp.write_text(json.dumps(checkpoint,default=str));temp.replace(state_path)
        print(f'Full autonomous {cid} block {number+1}/{len(blocks)}: entries={len(frame)}, exact={metrics["exact_entries"]}/210, extra={metrics["extra_entries"]}, gaps={sum(gaps.values())}, carried={position is not None}',flush=True)
        state.update(position=position,last_decision=last_decision,details=details,completed=number+1,tested=state['tested']+1)
        del replay;gc.collect()


def run_batch(candidates,trial_dir,style='ledger',limit_blocks=0,restart=False,batch_size=2):
    """Share a raw chunk while sequentially evaluating independent candidates.

    One immutable quote index is prepared per chunk when multiple candidates
    are active. Only one engine runs at a time; positions, decisions and
    checkpoints remain independent. Committed chunks are never re-run.
    """
    candidates=list(candidates)
    if style not in ('ledger','description'):raise ValueError('Unknown execution style')
    if not isinstance(batch_size,int) or not 1<=batch_size<=4:raise ValueError('Batch size must be 1 through 4')
    if not isinstance(limit_blocks,int) or limit_blocks<0:raise ValueError('Chunk limit must be nonnegative')
    identities=[c['candidate_id'] for c in candidates]
    if len(set(identities))!=len(identities):raise ValueError('Duplicate candidate in batch')
    if not candidates:return []
    blocks=history_blocks();source=provider_trades();calendar=ProviderCalendar();client=DhanHistoryClient(offline=True)
    settlements=NSESettlementClient(client.cache_dir,offline=False)
    def required_settlement(expiry):
        settlement=settlements.get(expiry)
        if settlement is None:
            raise RuntimeError(f'Official NSE settlement for {expiry} is unavailable. Replay stopped before scoring later entries; recover the dated archive and resume the saved checkpoint.')
        return settlement
    targets=[]
    for offset in range(0,len(candidates),batch_size):
        states=[_prepare_candidate(c,trial_dir,style,source,blocks,restart)
                for c in candidates[offset:offset+batch_size]]
        targets.extend(s['target'] for s in states)
        for number,(first,last) in enumerate(blocks):
            active=[s for s in states if s['completed']<=number and (not limit_blocks or s['tested']<limit_blocks)]
            if not active:continue
            if any(s['completed']!=number for s in active):raise ValueError('Candidate has an uncommitted earlier chunk')
            bars,options,conflicts=load_history(client,first,last,calendar=calendar,expiry_resolver=expiries_for)
            options,_=supplement_fixed_contracts(client,bars,options,last,calendar,expiries_for,lot_size)
            prepared_quotes=prepare_option_quotes(options) if len(active)>1 else None
            for state in active:
                _advance_candidate(state,bars,options,number,first,blocks,source,calendar,required_settlement,style,prepared_quotes)
            del bars,options,conflicts,prepared_quotes;gc.collect()
        del states;gc.collect()
    for target in targets:
        path=target/'performance.json'
        if path.exists():
            performance=json.loads(path.read_text())['performance']
            print(json.dumps({'performance_report':str(path),'monthly_report':str(target/'performance_monthly.csv'),
                **{key:performance[key] for key in ('period_start','period_end','trade_count','win_rate_pct','total_pnl',
                    'cagr_pct','return_1m_pct','return_3m_pct','return_6m_pct','max_drawdown_pct','open_trade_count','open_mtm_pnl')}
                }),flush=True)
    return targets


def run(candidate,trial_dir,style='ledger',limit_blocks=0,restart=False):
    return run_batch([candidate],trial_dir,style,limit_blocks,restart,batch_size=1)[0]


def fit_replay_score(target,cutoff=date(2026,2,28)):
    """Score an autonomous path using only entry labels through the fit cutoff."""
    state=json.loads((target/'checkpoint.json').read_text())
    blocks=state.get('history_blocks') or [[str(a),str(b)] for a,b in history_blocks()]
    completed=state['completed_blocks']
    if not 1<=completed<=len(blocks) or date.fromisoformat(blocks[completed-1][1])<=cutoff:
        raise ValueError('Replay has not covered the whole fit period')
    if datetime.fromisoformat(state['entry_end']).date()<cutoff:
        raise ValueError('Replay entry cutoff excludes part of the fit period')
    source=provider_trades();expected=source.loc[source.entry.dt.date<=cutoff]
    # The checkpoint owns committed trades, even if a subsequent chunk failed
    # after overwriting trades.csv. Later trades and exits are not fit inputs.
    trades=normalize_trades(pd.DataFrame(state['trades'])) if 'trades' in state else normalize_trades(pd.read_csv(target/'trades.csv'))
    if state['position']:
        position=dict(state['position']);stamp=pd.Timestamp(position['entry_ts'])
        if trades.empty or not trades.entry_ts.eq(stamp).any():
            position['exit_ts']=None
            trades=normalize_trades(pd.concat([trades,pd.DataFrame([position])],ignore_index=True))
    entries=trades.loc[trades.entry_ts.dt.date<=cutoff] if not trades.empty else trades
    keys=set(zip(entries.entry_ts,entries.option_type,entries.sell_strike,entries.buy_strike,entries.expiry)) if not entries.empty else set()
    exact=sum((t.entry_minute,t.option_type,t.short_strike,t.hedge_strike,t.expiry) in keys for t in expected.itertuples())
    return {'candidate_id':state['candidate']['candidate_id'],'fit_cutoff_inclusive':str(cutoff),
        'fit_source_trades':len(expected),'fit_actual_entries':len(entries),
        'fit_actual_exact_entries':exact,'fit_actual_extra_entries':len(entries)-exact}


def rank_fit_replays(candidates,trial_dir,style='ledger'):
    """Retain original candidate metadata so partial replays resume unchanged."""
    scored=[];pending=[]
    for candidate in candidates:
        cid=candidate['candidate_id'];target=trial_dir/f'full_autonomous_{cid}_{style}'
        if not (target/'checkpoint.json').exists():pending.append(cid);continue
        state=json.loads((target/'checkpoint.json').read_text())
        if state['candidate']!=candidate:raise ValueError('Fit replay candidate metadata differs')
        try:metrics=fit_replay_score(target)
        except ValueError as error:
            if str(error)=='Replay has not covered the whole fit period':pending.append(cid);continue
            raise
        scored.append((candidate,metrics))
    scored.sort(key=lambda pair:(-pair[1]['fit_actual_exact_entries'],pair[1]['fit_actual_extra_entries'],pair[0]['candidate_id']))
    (trial_dir/'fit_autonomous_frontier.json').write_text(json.dumps([c for c,m in scored],indent=2))
    (trial_dir/'fit_autonomous_selection.json').write_text(json.dumps({'scored':[m for c,m in scored],'pending_candidates':pending,
        'selection':'Actual autonomous fit entry matches, then fewer extra fit entries. Source exits and labels after 28 February 2026 are excluded from selection.',
        'limits':'Quote gaps can affect the replay. Later periods already inspected; they are not untouched holdouts. A fit winner still requires full-history validation.'},indent=2))
    return [m for c,m in scored]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fine',action='store_true');parser.add_argument('--candidate',help='candidate ID, default current fit leader')
    parser.add_argument('--family',choices=('main','fine','sampling','expanded','mixed','fixed_contract','boundaries','rank_conventions','eligibility','opening_atm','opening_volume','opening_pcr','contract_cumulative','crossings','bulk','implied_volatility','implied_volatility_opening_complete','opening_ohlc_volatility','opening_fixed_ohlc','weighted_volatility','volatility_definitions','calendar_rank_pairs','weighted_rank_pairs','weighted_alpha_volatility_definitions','complete_case_pairs','hysteresis_pairs','opening_fixed','opening_fixed_rank','opening_fixed_rank_observed_log_return','opening_fixed_rank_price_std','opening_fixed_rank_adjacent_five_minute_log_return','opening_fixed_rank_adjacent_log_rms','opening_fixed_selected_raw_adjacent_log_return','opening_fixed_selected_raw_observed_log_return','opening_fixed_selected_raw_price_std','opening_fixed_selected_raw_adjacent_five_minute_log_return','opening_fixed_selected_raw_adjacent_log_rms'),default='main')
    parser.add_argument('--style',choices=('ledger','description'),default='ledger')
    parser.add_argument('--limit-blocks',type=int,default=0)
    parser.add_argument('--restart',action='store_true',help='rebuild generated replay outputs from the first cached block')
    parser.add_argument('--batch-finalists',type=int,help='replay this many saved finalists, sharing raw chunks')
    parser.add_argument('--batch-size',type=int,default=2,help='bounded shared-chunk group size (1 through 4; default 2)')
    parser.add_argument('--frontier-name',choices=('frontier','pilot_frontier','diverse_frontier','fit_stage_frontier','diverse_fit_frontier','no_target_frontier','final_grid_fit_frontier','reentry_frontier','replay_pool','fit_autonomous_frontier'),default='frontier')
    parser.add_argument('--rank-fit',action='store_true',help='rank committed replays using actual fit-period entry matches and extras')
    parser.add_argument('--performance-report',action='store_true',help='backfill gross performance and monthly Zen comparisons for all committed trial replays')
    args=parser.parse_args()
    if args.performance_report:
        if args.candidate or args.batch_finalists is not None or args.restart or args.limit_blocks or args.rank_fit:
            parser.error('--performance-report reports existing replays only')
        backfill_performance_reports();return
    if args.fine and args.family not in ('main','fine'):parser.error('--fine conflicts with selected family')
    family='fine' if args.fine else args.family
    trial_dir=OUT if family=='main' else OUT/family
    frontier=json.loads((trial_dir/f'{args.frontier_name}.json').read_text())
    if args.rank_fit:
        if args.candidate or args.batch_finalists is not None or args.restart or args.limit_blocks:parser.error('--rank-fit scores existing committed replays only')
        print(json.dumps(rank_fit_replays(frontier,trial_dir,args.style)),flush=True)
        return
    if args.batch_finalists is not None:
        if args.candidate:parser.error('--batch-finalists conflicts with --candidate')
        if not 1<=args.batch_finalists<=len(frontier):parser.error('--batch-finalists must be within saved frontier size')
        if not 1<=args.batch_size<=4:parser.error('--batch-size must be 1 through 4')
        run_batch(frontier[:args.batch_finalists],trial_dir,args.style,args.limit_blocks,args.restart,args.batch_size)
        return
    candidate=next((f for f in frontier if f['candidate_id']==args.candidate),None) if args.candidate else frontier[0]
    if candidate is None:raise ValueError('Candidate not in saved frontier')
    run(candidate,trial_dir,args.style,args.limit_blocks,args.restart)


if __name__=='__main__':main()
