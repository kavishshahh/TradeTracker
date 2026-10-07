"""Option factors from each selected ATM contract's own prior history.

Reindex every fixed contract to observed index decision minutes. Absent quotes
remain absent; rolling windows cannot silently compress a gap in a contract.
"""
from pathlib import Path
import argparse
import json
import gc
import numpy as np
import pandas as pd
from backtest.provider_research import BAR_CACHE,FEATURE_CACHE,OUTPUT,history_blocks
from backtest.dhan_history import DhanHistoryClient,option_payload
from backtest.dhan_replay import load_history,supplement_fixed_contracts,parse_series
from backtest.provider_calendar import ProviderCalendar,expiries_for,lot_size
from utils.time import IST

FIXED_CACHE=FEATURE_CACHE.with_name('provider_fixed_atm_factors.csv.gz')
OPENING_CACHE=FEATURE_CACHE.with_name('provider_opening_atm_features.csv.gz')
OPENING_FULL_FIELDS_CACHE=FEATURE_CACHE.with_name('provider_opening_atm_full_fields.csv.gz')
OPENING_FIXED_OHLC_CACHE=FEATURE_CACHE.with_name('provider_opening_fixed_ohlc_factors.csv.gz')
OPENING_FULL_FIELDS=('open','high','low','close','volume','strike','spot','iv','oi')
OPENING_FIXED_CACHE=FEATURE_CACHE.with_name('provider_opening_fixed_atm_factors.csv.gz')
OPENING_FIXED_RANK_CACHE=FEATURE_CACHE.with_name('provider_opening_fixed_contract_ranks.csv.gz')
CUMULATIVE_CACHE=FEATURE_CACHE.with_name('provider_contract_cumulative_volume.csv.gz')
WINDOWS=(20,60,300)
SHORTS=(1,5,15)
# Longest OHLC dependency: STD/mean300 at lag5 needs304 prior clock slots.
FIXED_OHLC_HISTORY_SLOTS=305


def contract_cumulative_features(bars,quotes):
    """Exact known volume prefixes of each selected contract, independently by day.

    All regular-session minute observations from 09:15 must be present. A missing,
    negative or invalid volume invalidates that contract's remaining daily prefix;
    it is never treated as zero. Selection uses the completed index candle open.
    """
    if quotes.index.has_duplicates:raise ValueError('Duplicate contract-volume observations')
    q=quotes[['ce_volume','pe_volume']].reset_index().sort_values('minute')
    clock=q.minute.dt.hour*60+q.minute.dt.minute
    q=q.loc[clock.between(556,930)].copy()
    expected=q.minute.dt.hour*60+q.minute.dt.minute-555
    groups=[q.minute.dt.date,q.expiry,q.strike]
    for side in ('ce','pe'):
        volume=q[f'{side}_volume'].astype(float)
        known=np.isfinite(volume)&volume.ge(0)
        count=known.astype(int).groupby(groups,sort=False).cumsum()
        complete=known&count.eq(expected)
        cumulative=volume.where(known).groupby(groups,sort=False).cumsum()
        q[f'{side}_contract_cumulative_volume']=cumulative.where(complete)
        q[f'{side}_cumulative_prefix_complete']=complete
    q=q.set_index(['minute','expiry','strike'])
    minutes=bars.index+pd.Timedelta(minutes=1)
    mapping={d:expiries_for(d) for d in set(bars.index.date)}
    strikes=np.floor((bars.open.to_numpy()+25-1e-8)/50)*50
    frames=[]
    for number in (0,1):
        expiry=[mapping[d][number] for d in bars.index.date]
        keys=pd.MultiIndex.from_arrays([minutes,expiry,strikes],names=quotes.index.names)
        selected=q.reindex(keys)
        frame=pd.DataFrame({'minute':minutes,'expiry':expiry,'atm_strike':strikes})
        for side in ('ce','pe'):
            frame[f'{side}_native_volume']=selected[f'{side}_volume'].to_numpy()
            frame[f'{side}_contract_cumulative_volume']=selected[f'{side}_contract_cumulative_volume'].to_numpy()
            frame[f'{side}_cumulative_prefix_complete']=selected[f'{side}_cumulative_prefix_complete'].eq(True).to_numpy()
        frames.append(frame)
    return pd.concat(frames,ignore_index=True)


def prepare_contract_cumulative():
    """Rebuild from original fixed-strike candle volumes, with coverage evidence."""
    client=DhanHistoryClient(offline=True);calendar=ProviderCalendar();frames=[];quality=[]
    for number,(first,last) in enumerate(history_blocks()):
        bars,quotes,conflicts=load_history(client,first,last,calendar=calendar,expiry_resolver=expiries_for)
        quotes,fixed=supplement_fixed_contracts(client,bars,quotes,last,calendar,expiries_for,lot_size)
        frame=contract_cumulative_features(bars,quotes);frames.append(frame)
        # Distinguish candle volume from a monotone cumulative feed empirically.
        q=quotes[['ce_volume','pe_volume']].reset_index().sort_values('minute')
        group=q.groupby([q.minute.dt.date,'expiry','strike'],sort=False)
        adjacent=group.minute.diff().eq(pd.Timedelta(minutes=1))
        decreases={side:int((group[f'{side}_volume'].diff().lt(0)&adjacent).sum()) for side in ('ce','pe')}
        quality.append({'start':str(first),'end_exclusive':str(last),'rows':len(frame),
            'ce_complete_prefixes':int(frame.ce_cumulative_prefix_complete.sum()),
            'pe_complete_prefixes':int(frame.pe_cumulative_prefix_complete.sum()),
            'adjacent_fixed_contract_native_volume_decreases':decreases,'conflicts':len(conflicts)})
        print(f'Contract cumulative volume {number+1}/{len(history_blocks())}: {len(frame):,} rows; both complete={int((frame.ce_cumulative_prefix_complete&frame.pe_cumulative_prefix_complete).sum()):,}',flush=True)
        del bars,quotes,q,group,conflicts;gc.collect()
    result=pd.concat(frames,ignore_index=True).sort_values(['expiry','minute'])
    if result.duplicated(['minute','expiry']).any():raise ValueError('Duplicate cumulative selected-contract rows')
    result.to_csv(CUMULATIVE_CACHE,index=False)
    from backtest.provider_research import provider_trades
    trades=provider_trades();result.expiry=pd.to_datetime(result.expiry).dt.date
    panel=result.set_index(['minute','expiry'])
    evidence=trades[['signal_id','entry','entry_minute','option_type','expiry','short_strike']].copy()
    chosen=panel.reindex(pd.MultiIndex.from_arrays([trades.entry_minute,trades.expiry]))
    for column in chosen.columns:evidence[column]=chosen[column].to_numpy()
    evidence['both_prefixes_complete']=evidence.ce_cumulative_prefix_complete.eq(True)&evidence.pe_cumulative_prefix_complete.eq(True)
    if not evidence.atm_strike.eq(evidence.short_strike).all():raise ValueError('Cumulative ATM reference differs from source strike audit')
    target=OUTPUT/'replication_trials'/'contract_cumulative';target.mkdir(exist_ok=True)
    evidence.to_csv(target/'source_cumulative_volume_coverage.csv',index=False)
    (target/'panel_design.json').write_text(json.dumps({'rows':len(result),'source_entries':len(trades),
        'source_entries_with_both_complete_prefixes':int(evidence.both_prefixes_complete.sum()),
        'reference':'Nearest ATM to the last completed index candle open, lower tie; near and next expiries.',
        'volume':'Sum known native candle volumes of the SAME expiry and strike from regular-session 09:15 through the completed candle.',
        'missing':'Every regular-session minute must be known independently for each leg. Missing, negative or invalid volume makes the current and remaining daily prefix unavailable. No forward fill or zero substitution.',
        'causality':'Each prefix includes only candles completed by its decision minute. Each trading date resets each fixed contract. Source entries only label the coverage audit, never input to sums or contract selection.',
        'scope':'Alternative volume-input preparation, not an alpha2 formula or a strategy replica. Minute totals cannot recover the exact intraminute exchange total at a source timestamp.',
        'chunks':quality},indent=2,default=str))
    print(f'Saved {len(result):,} rows; source complete prefixes {int(evidence.both_prefixes_complete.sum())}/{len(trades)}',flush=True)


def opening_atm_features(bars,quotes):
    """Select ATM from each completed index candle's open, never from its close.

    One-minute option returns use the previous quote of the SAME current strike.
    Native volume stays native; missing prices are not filled or replaced by a
    neighboring strike. This panel is a research alternative, not a service edit.
    """
    minutes=bars.index+pd.Timedelta(minutes=1)
    mapping={d:expiries_for(d) for d in set(bars.index.date)}
    strike=np.floor((bars.open.to_numpy()+25-1e-8)/50)*50
    frames=[]
    same_session=(minutes.time!=pd.Timestamp('09:16').time())
    for number in (0,1):
        expiry=[mapping[d][number] for d in bars.index.date]
        keys=pd.MultiIndex.from_arrays([minutes,expiry,strike],names=quotes.index.names)
        previous_keys=pd.MultiIndex.from_arrays([minutes-pd.Timedelta(minutes=1),expiry,strike],names=quotes.index.names)
        current=quotes.reindex(keys);previous=quotes.reindex(previous_keys)
        frame=pd.DataFrame({'minute':minutes,'expiry':expiry,'atm_strike':strike,
            'spot':bars.close.to_numpy(),'reference_open':bars.open.to_numpy()})
        for side in ('ce','pe'):
            price=current[f'{side}_ltp'].to_numpy(dtype=float);old=previous[f'{side}_ltp'].to_numpy(dtype=float)
            volume=current[f'{side}_volume'].to_numpy(dtype=float)
            valid=same_session&np.isfinite(price)&np.isfinite(old)&(price>0)&(old>0)
            frame[f'{side}_ltp']=price
            frame[f'{side}_native_volume']=volume
            frame[f'{side}_volume']=np.where(same_session&np.isfinite(previous[f'{side}_volume'].to_numpy()),volume,np.nan)
            frame[f'{side}_return']=np.divide(price,old,out=np.full(len(price),np.nan),where=valid)-1
        frames.append(frame)
    return pd.concat(frames,ignore_index=True)


def prepare_opening_features():
    client=DhanHistoryClient(offline=True);calendar=ProviderCalendar();frames=[];quality=[]
    for number,(first,last) in enumerate(history_blocks()):
        bars,quotes,conflicts=load_history(client,first,last,calendar=calendar,expiry_resolver=expiries_for)
        quotes,fixed=supplement_fixed_contracts(client,bars,quotes,last,calendar,expiries_for,lot_size)
        frame=opening_atm_features(bars,quotes);frames.append(frame)
        quality.append({'start':str(first),'end_exclusive':str(last),'rows':len(frame),'conflicts':len(conflicts),'fixed':fixed})
        print(f'Opening-reference ATM panel {number+1}/{len(history_blocks())}: {len(frame):,} rows',flush=True)
        del bars,quotes,conflicts;gc.collect()
    result=pd.concat(frames,ignore_index=True).sort_values(['expiry','minute'])
    if result.duplicated(['minute','expiry']).any():raise ValueError('Duplicate opening-reference factor minutes')
    result.to_csv(OPENING_CACHE,index=False)
    target=OUTPUT/'replication_trials'/'opening_atm';target.mkdir(exist_ok=True)
    (target/'panel_design.json').write_text(json.dumps({'reference':'last completed index candle open; nearest strike, lower tie',
        'returns':'current selected strike current close / SAME strike previous-minute close - 1; no overnight return',
        'volume':'native option candle volume; no cumulative ATM proxy',
        'data':'Existing offline raw Dhan quotes, including fixed-contract supplements; no source trade values as inputs.',
        'limitations':'Unavailable selected contracts remain unavailable. Selected ATM changes between observations; rolling factors are a selected-contract path, not one fixed contract throughout the window.',
        'chunks':quality},indent=2,default=str))
    print('Saved opening-reference ATM features:',len(result),flush=True)


def opening_full_field_rows(frame,code):
    """Completed full-field candles, dated expiry inferred from their raw day."""
    if code not in (1,2):raise ValueError('Full-field expiry code must be near or next')
    if frame.empty:return pd.DataFrame(columns=['minute','expiry',*OPENING_FULL_FIELDS])
    result=frame.reindex(columns=OPENING_FULL_FIELDS).copy()
    result['minute']=frame.index+pd.Timedelta(minutes=1)
    result['expiry']=[expiries_for(day)[code-1] for day in frame.index.date]
    return result.reset_index(drop=True)


def clean_opening_full_rows(frames):
    """Identical duplicates collapse; conflicting exact contract rows disappear."""
    columns=['minute','expiry',*OPENING_FULL_FIELDS]
    if not frames:return pd.DataFrame(columns=columns),set()
    rows=pd.concat(frames,ignore_index=True).reindex(columns=columns)
    if rows.empty:return rows,set()
    rows.minute=pd.to_datetime(rows.minute,utc=True).dt.tz_convert(IST)
    rows.expiry=pd.to_datetime(rows.expiry).dt.date
    for field in OPENING_FULL_FIELDS:rows[field]=pd.to_numeric(rows[field],errors='coerce')
    rows=rows.loc[np.isfinite(rows.strike)&rows.strike.gt(0)].copy()
    keys=['minute','expiry','strike'];dup=rows.duplicated(keys,keep=False)
    conflicts=set()
    if dup.any():
        counts=rows.loc[dup].groupby(keys,dropna=False)[list(OPENING_FULL_FIELDS)].nunique(dropna=False)
        conflicts=set(counts.index[(counts>1).any(axis=1)].tolist())
        if conflicts:
            rows=rows.loc[~pd.MultiIndex.from_frame(rows[keys]).isin(conflicts)]
    return rows.drop_duplicates(keys),conflicts


def opening_full_field_offsets(labels,atm,code,bound=2):
    """Offsets derive from market ATM at the same completed candle, not events."""
    clean,_=clean_opening_full_rows([atm])
    references=clean.set_index(['minute','expiry'])['strike']
    ambiguous=references.index.duplicated(keep=False)
    references=references.loc[~ambiguous]
    keys=pd.MultiIndex.from_frame(labels[['minute','expiry']])
    reference=references.reindex(keys).to_numpy(dtype=float)
    offset=(labels.atm_strike.to_numpy(dtype=float)-reference)/50
    exact=np.isfinite(offset)&(offset==np.floor(offset))
    allowed=exact&(np.abs(offset)<=bound)
    status=np.where(~np.isfinite(reference),'atm_reference_unknown',np.where(~exact,'strike_grid_unknown',
        np.where(~allowed,'outside_initial_offset_bound','available')))
    return sorted({int(value) for value in offset[allowed]}),pd.DataFrame({'offset':np.where(allowed,offset,np.nan),
        'status':status},index=labels.index)


def join_opening_full_fields(labels,side_frames):
    """Exact minute/expiry/strike pair; absent/conflicting sides never substituted."""
    result=labels[['minute','expiry','atm_strike']].copy().reset_index(drop=True)
    result.minute=pd.to_datetime(result.minute,utc=True).dt.tz_convert(IST)
    result.expiry=pd.to_datetime(result.expiry).dt.date
    if result.duplicated(['minute','expiry']).any():raise ValueError('Duplicate opening full-field labels')
    keys=pd.MultiIndex.from_arrays([result.minute,result.expiry,result.atm_strike],names=['minute','expiry','strike'])
    for side in ('ce','pe'):
        rows,conflicts=clean_opening_full_rows(side_frames.get(side,[]))
        rows=rows.set_index(['minute','expiry','strike'])
        available=keys.isin(rows.index)
        result[f'{side}_row_available']=available
        result[f'{side}_row_conflict']=keys.isin(conflicts)
        selected=rows.reindex(keys)
        for field in OPENING_FULL_FIELDS:
            result[f'{side}_{field}']=result.atm_strike.where(available) if field=='strike' else selected[field].to_numpy()
    result['both_exact_rows_available']=result.ce_row_available&result.pe_row_available
    # The paired input requires both exact contracts. Keep leg availability flags.
    for side in ('ce','pe'):
        for field in OPENING_FULL_FIELDS:
            result.loc[~result.both_exact_rows_available,f'{side}_{field}']=np.nan
    return result


def prepare_opening_full_fields(client=None,limit_blocks=0):
    """Small read-only offset responses; resume committed full-panel chunks."""
    if isinstance(limit_blocks,bool) or not isinstance(limit_blocks,int) or limit_blocks<0:
        raise ValueError('Full-field block limit must be a nonnegative integer')
    client=client or DhanHistoryClient();calendar=ProviderCalendar()
    selected=pd.read_csv(OPENING_CACHE,usecols=['minute','expiry','atm_strike'])
    selected.minute=pd.to_datetime(selected.minute,utc=True).dt.tz_convert(IST)
    selected.expiry=pd.to_datetime(selected.expiry).dt.date
    target=OUTPUT/'opening_full_field_chunks';target.mkdir(exist_ok=True)
    frames=[];quality=[];new_blocks=0;blocks=history_blocks()
    for first,last in blocks:
        path=target/f'{first}_{last}.csv.gz';meta=path.with_name(path.name+'.json')
        if path.exists() and meta.exists():
            frame=pd.read_csv(path);frame.minute=pd.to_datetime(frame.minute,utc=True).dt.tz_convert(IST)
            frame.expiry=pd.to_datetime(frame.expiry).dt.date;details=json.loads(meta.read_text())
        else:
            if limit_blocks and new_blocks>=limit_blocks:break
            labels=selected.loc[(selected.minute.dt.date>=first)&(selected.minute.dt.date<last)].copy()
            side_frames={'ce':[],'pe':[]};requests=[];statuses={}
            desired=pd.MultiIndex.from_arrays([labels.minute,labels.expiry,labels.atm_strike],names=['minute','expiry','strike'])
            for code in (1,2):
                chosen=labels.loc[[expiry==expiries_for(minute.date())[code-1] for expiry,minute in zip(labels.expiry,labels.minute)]]
                for side,label in (('CALL','ce'),('PUT','pe')):
                    def fetch(offset):
                        payload=option_payload(first,last,code,offset,side)
                        payload['requiredData']=list(OPENING_FULL_FIELDS)
                        data=client.request('rollingoption',payload)
                        requests.append({'expiry_code':code,'side':side,'offset':offset})
                        return opening_full_field_rows(parse_series(data['data'].get(label),first,last,calendar),code)
                    atm=fetch(0);offsets,state=opening_full_field_offsets(chosen,atm,code)
                    statuses[f'{code}_{label}']=state.status.value_counts().to_dict()
                    for offset in sorted(set(offsets)|{0}):
                        response=atm if offset==0 else fetch(offset)
                        keep=pd.MultiIndex.from_frame(response[['minute','expiry','strike']]).isin(desired)
                        side_frames[label].append(response.loc[keep].copy())
                        if offset!=0:del response
                    del atm
            frame=join_opening_full_fields(labels,side_frames)
            details={'start':str(first),'end_exclusive':str(last),'rows':len(frame),
                'requests':requests,'offset_statuses':statuses,
                'both_exact_rows_available':int(frame.both_exact_rows_available.sum()),
                'known_fields':{c:int(frame[c].notna().sum()) for c in frame if c.startswith(('ce_','pe_')) and c.split('_',1)[1] in OPENING_FULL_FIELDS}}
            frame.to_csv(path,index=False);meta.write_text(json.dumps(details,indent=2));new_blocks+=1
            del side_frames;gc.collect()
        frames.append(frame);quality.append(details)
        print(f'Opening full fields {len(frames)}/{len(blocks)}: both exact={details["both_exact_rows_available"]}/{len(frame)}, downloaded={getattr(client,"downloaded",None)}',flush=True)
    result=pd.concat(frames,ignore_index=True).sort_values(['expiry','minute'])
    if result.duplicated(['minute','expiry']).any():raise ValueError('Duplicate opening full-field output')
    result.to_csv(OPENING_FULL_FIELDS_CACHE,index=False)
    (OUTPUT/'opening_full_fields_design.json').write_text(json.dumps({'rows':len(result),
        'completed_blocks':len(frames),'total_blocks':len(blocks),'complete':len(frames)==len(blocks),
        'cache':str(OPENING_FULL_FIELDS_CACHE),'initial_offset_bound':2,
        'requiredData':list(OPENING_FULL_FIELDS),'both_exact_rows_available':int(result.both_exact_rows_available.sum()),
        'selection':'All opening-ATM market labels for near and next expiries; no published trade labels as inputs.',
        'clock':'Raw candle starts +1 minute, completed decision clock. Exact expiry inferred from raw calendar date and rolling expiry code.',
        'offsets':'Only offsets required by selected opening strike minus same-minute raw ATM strike, divided by50. Near/next initially restricted to±2; wider/unknown offsets remain unknown.',
        'missing':'No fill or neighboring-strike substitution. Both CE/PE exact-minute/expiry/strike rows required for paired fields. Identical duplicates collapse; any conflicting full-field exact row excluded.',
        'chunks':quality},indent=2,default=str))
    return result


def fixed_ohlc_history_needs(labels,clock,slots=FIXED_OHLC_HISTORY_SLOTS):
    """Union exact-contract clock slots needed by current market selections."""
    if not isinstance(clock,pd.DatetimeIndex) or clock.has_duplicates or not clock.is_monotonic_increasing:
        raise ValueError('OHLC history clock must be unique and ordered')
    if isinstance(slots,bool) or not isinstance(slots,int) or slots<1:raise ValueError('OHLC history slots must be positive')
    if labels.duplicated(['minute','expiry']).any():raise ValueError('Duplicate opening OHLC labels')
    frames=[]
    for (expiry,strike),visits in labels.groupby(['expiry','atm_strike'],sort=False):
        ends=clock.get_indexer(pd.DatetimeIndex(visits.minute))
        if (ends<0).any():raise ValueError('Opening OHLC visit absent from decision clock')
        # Difference array marks union without repeating305 rows per visit.
        delta=np.zeros(len(clock)+1,dtype=np.int64)
        np.add.at(delta,np.maximum(0,ends-slots+1),1);np.add.at(delta,ends+1,-1)
        wanted=np.cumsum(delta[:-1])>0
        frames.append(pd.DataFrame({'minute':clock[wanted],'expiry':expiry,'atm_strike':strike}))
    return pd.concat(frames,ignore_index=True) if frames else pd.DataFrame(columns=['minute','expiry','atm_strike'])


def fixed_ohlc_contract_clock(clock,visits):
    """Contiguous common-clock bounds sufficient for every selected OHLC factor.

    Keep intervening missing slots: compressing separated visits or quote holes
    would change rolling windows and lag5. Quotes outside these bounds are
    already excluded by the305-slot request-needs union.
    """
    if not isinstance(clock,pd.DatetimeIndex) or clock.has_duplicates or not clock.is_monotonic_increasing:
        raise ValueError('OHLC history clock must be unique and ordered')
    minutes=pd.DatetimeIndex(visits)
    if minutes.empty:raise ValueError('Opening OHLC contract needs selected visits')
    positions=clock.get_indexer(minutes)
    if (positions<0).any():raise ValueError('Opening OHLC visit absent from decision clock')
    start=max(0,int(positions.min())-FIXED_OHLC_HISTORY_SLOTS+1)
    return clock[start:int(positions.max())+1]


def prepare_opening_fixed_ohlc(client=None,limit_blocks=0,offline=False):
    """Own-contract OHLC histories, exact market-selected305-slot request needs.

    Each block recomputes its prior330-slot history from the relevant dated raw
    payloads. A current strike may therefore request a previously unused offset
    of the previous block. No saved selected-ATM panel is a history substitute.
    """
    if isinstance(limit_blocks,bool) or not isinstance(limit_blocks,int) or limit_blocks<0:
        raise ValueError('OHLC block limit must be a nonnegative integer')
    client=client or DhanHistoryClient(offline=offline);calendar=ProviderCalendar()
    bars=pd.read_csv(BAR_CACHE,index_col=0,float_precision='round_trip')
    index=pd.to_datetime(bars.index,utc=True).tz_convert(IST)+pd.Timedelta(minutes=1)
    if index.has_duplicates or not index.is_monotonic_increasing:raise ValueError('Underlying OHLC clock must be unique and ordered')
    selected=pd.read_csv(OPENING_CACHE,usecols=['minute','expiry','atm_strike'],float_precision='round_trip')
    selected.minute=pd.to_datetime(selected.minute,utc=True).dt.tz_convert(IST)
    selected.expiry=pd.to_datetime(selected.expiry).dt.date
    target=OUTPUT/'opening_fixed_ohlc_chunks';target.mkdir(exist_ok=True)
    blocks=history_blocks();frames=[];quality=[];new_blocks=0
    for first,last in blocks:
        path=target/f'{first}_{last}.csv.gz';meta=path.with_name(path.name+'.json')
        saved=json.loads(meta.read_text()) if path.exists() and meta.exists() else None
        reusable=saved is not None and (offline or saved.get('requests_complete',
            not any(r.get('status')=='offline_cache_unknown' for r in saved.get('requests',[]))))
        if reusable:
            frame=pd.read_csv(path,float_precision='round_trip')
            frame.minute=pd.to_datetime(frame.minute,utc=True).dt.tz_convert(IST)
            frame.expiry=pd.to_datetime(frame.expiry).dt.date;details=saved
        else:
            if limit_blocks and new_blocks>=limit_blocks:break
            current=index[(index.date>=first)&(index.date<last)]
            if current.empty:raise ValueError('OHLC preparation block has no underlying clock')
            start=max(0,index.searchsorted(current[0])-330);stop=index.searchsorted(current[-1])+1
            clock=index[start:stop]
            labels=selected.loc[selected.minute.isin(current)].copy()
            if labels.empty:raise ValueError('OHLC preparation block has no opening market labels')
            needs=fixed_ohlc_history_needs(labels,clock)
            side_frames={'ce':[],'pe':[]};requests=[];statuses={}
            for scope_first,scope_last in blocks:
                scope_clock=clock[(clock.date>=scope_first)&(clock.date<scope_last)]
                if scope_clock.empty:continue
                scope_needs=needs.loc[needs.minute.isin(scope_clock)]
                mapping={day:expiries_for(day) for day in set(scope_clock.date)}
                codes=np.array([mapping[minute.date()].index(expiry)+1 if expiry in mapping[minute.date()] else 0
                    for expiry,minute in zip(scope_needs.expiry,scope_needs.minute)])
                unsupported=int((codes==0).sum())
                for side,label in (('CALL','ce'),('PUT','pe')):
                    statuses[f'{scope_first}_{label}_expiry_unknown']=unsupported
                    for code in (1,2):
                        chosen=scope_needs.loc[codes==code]
                        if chosen.empty:continue
                        keys=pd.MultiIndex.from_arrays([chosen.minute,chosen.expiry,chosen.atm_strike],names=['minute','expiry','strike'])
                        def fetch(offset):
                            payload=option_payload(scope_first,scope_last,code,offset,side)
                            payload['requiredData']=list(OPENING_FULL_FIELDS)
                            cached_before=getattr(client,'cached',0);download_before=getattr(client,'downloaded',0)
                            try:data=client.request('rollingoption',payload)
                            except RuntimeError as error:
                                if offline and str(error).startswith('Missing offline cache:'):
                                    requests.append({'fromDate':str(scope_first),'toDate':str(scope_last),
                                        'expiry_code':code,'side':side,'offset':offset,'status':'offline_cache_unknown'})
                                    return pd.DataFrame(columns=['minute','expiry',*OPENING_FULL_FIELDS])
                                raise
                            requests.append({'fromDate':str(scope_first),'toDate':str(scope_last),
                                'expiry_code':code,'side':side,'offset':offset,'status':'available_response',
                                'cache_hits_change':getattr(client,'cached',0)-cached_before,
                                'downloads_change':getattr(client,'downloaded',0)-download_before})
                            rows=opening_full_field_rows(parse_series(data['data'].get(label),scope_first,scope_last,calendar),code)
                            return rows.loc[rows.minute.isin(scope_clock)]
                        atm=fetch(0)
                        offsets,state=opening_full_field_offsets(chosen,atm,code,bound=10 if code==1 else 3)
                        statuses[f'{scope_first}_{code}_{label}']=state.status.value_counts().to_dict()
                        for offset in sorted(set(offsets)|{0}):
                            rows=atm if offset==0 else fetch(offset)
                            keep=pd.MultiIndex.from_frame(rows[['minute','expiry','strike']]).isin(keys)
                            side_frames[label].append(rows.loc[keep].copy())
                            if offset!=0:del rows
                        del atm
            clean={};conflicts={}
            for side in ('ce','pe'):
                clean[side],bad=clean_opening_full_rows(side_frames[side]);conflicts[side]=len(bad)
                clean[side]=clean[side].set_index(['minute','expiry','strike'])
            results=[]
            for (expiry,strike),visits in labels.groupby(['expiry','atm_strike'],sort=False):
                contract_clock=fixed_ohlc_contract_clock(clock,visits.minute)
                keys=pd.MultiIndex.from_arrays([contract_clock,[expiry]*len(contract_clock),[strike]*len(contract_clock)],names=['minute','expiry','strike'])
                series=pd.DataFrame(index=contract_clock)
                for side in ('ce','pe'):
                    exact=clean[side].reindex(keys)
                    for field in ('open','high','low','close','volume'):series[f'{side}_{field}']=exact[field].to_numpy()
                factors=contract_ohlc_factors(series).reindex(pd.DatetimeIndex(visits.minute))
                factors['minute']=visits.minute.to_numpy();factors['expiry']=expiry;factors['atm_strike']=strike
                results.append(factors.reset_index(drop=True))
            frame=pd.concat(results,ignore_index=True)
            known={c:int(frame[c].notna().sum()) for c in frame if c.startswith('fixed_ohlc_')}
            details={'start':str(first),'end_exclusive':str(last),'rows':len(frame),
                'requests_complete':not any(r.get('status')=='offline_cache_unknown' for r in requests),
                'history_clock_rows':len(clock),'prior_clock_rows':len(clock)-len(current),
                'exact_history_keys_needed':len(needs),'requests':requests,'support_statuses':statuses,
                'exact_conflict_keys':conflicts,'known_factor_counts':known,
                'total_downloads_this_block':sum(r.get('downloads_change',0) for r in requests),
                'total_cache_hits_this_block':sum(r.get('cache_hits_change',0) for r in requests)}
            frame.to_csv(path,index=False);meta.write_text(json.dumps(details,indent=2));new_blocks+=1
            del side_frames,clean,results,series,factors;gc.collect()
        frames.append(frame);quality.append(details)
        print(f'Opening fixed OHLC {len(frames)}/{len(blocks)}: rows={len(frame)}, downloads={details["total_downloads_this_block"]}, requests={len(details["requests"])}',flush=True)
    result=pd.concat(frames,ignore_index=True).sort_values(['expiry','minute'])
    if result.duplicated(['minute','expiry']).any():raise ValueError('Duplicate opening fixed OHLC output')
    result.to_csv(OPENING_FIXED_OHLC_CACHE,index=False)
    (OUTPUT/'opening_fixed_ohlc_design.json').write_text(json.dumps({'cache':str(OPENING_FIXED_OHLC_CACHE),
        'rows':len(result),'complete':len(frames)==len(blocks) and all(q.get('requests_complete',True) for q in quality),
        'computed_blocks':len(frames),'completed_blocks':sum(q.get('requests_complete',True) for q in quality),'total_blocks':len(blocks),
        'selection':'All opening-selected near/next market labels; no published source trades.',
        'history':'Union of each selected exact expiry/strike trailing305 observed decision-clock slots;prior330 slots recomputed from their original dated raw payload scopes.',
        'request_policy':'Same-minute raw ATM determines needed offsets independently by date scope,expiry code and side. Near±10,next±3;unknown references or wider offsets stay unknown. Only exact returned minute/expiry/strike rows retained.',
        'clock':'Raw starts+1minute;missing observed-clock contract rows never compressed or filled.',
        'factors':'108columns from unchanged contract_ohlc_factors;volatility150/300,80%minimum;volume baselines10/15/20;native/geometric/total;own-contract lag0/5 BEFORE selection.',
        'conflicts':'Identical duplicates collapse;conflicting exact full-field rows excluded.',
        'known_factor_counts':{c:int(result[c].notna().sum()) for c in result if c.startswith('fixed_ohlc_')},
        'limitations':'Coverage is not trigger or strategy replication. Unsupported histories remain unknown; no source prices, position resets or synthesized OHLC.',
        'chunks':quality},indent=2,default=str))
    return result


def contract_ohlc_factors(series):
    """108 lagged factors for ONE fixed expiry/strike on the common clock.

    Windows and lags count existing clock slots, including missing quote rows.
    Overnight jumps add no return: every volatility input uses its own OHLC.
    The caller must reindex full fixed-contract quotes before invoking this.
    """
    from backtest.provider_trials import opening_ohlc_volatility
    if not isinstance(series.index,pd.DatetimeIndex) or series.index.has_duplicates or not series.index.is_monotonic_increasing:
        raise ValueError('Fixed OHLC factors need a unique ordered DatetimeIndex')
    columns=[f'{side}_{field}' for side in ('ce','pe') for field in ('open','high','low','close','volume')]
    if not set(columns).issubset(series.columns):raise ValueError('Fixed OHLC factors need both exact OHLC and own-volume columns')
    values=series[columns].apply(pd.to_numeric,errors='coerce')
    volumes={side:values[f'{side}_volume'].where(lambda v:np.isfinite(v)&v.ge(0)) for side in ('ce','pe')}
    scales={(kind,window):opening_ohlc_volatility(values,kind,window)
        for kind in ('intrabar_return_std','parkinson','garman_klass') for window in (150,300)}
    result={}
    for baseline in (10,15,20):
        minimum=int(np.ceil(.8*baseline))
        ratios={side:volume/volume.rolling(baseline,min_periods=minimum).mean().where(lambda v:v>0)
            for side,volume in volumes.items()}
        total=volumes['ce']+volumes['pe']
        multipliers={'native':(ratios['ce']+ratios['pe'])/2,
            'geometric_ratios':np.sqrt(ratios['ce']*ratios['pe']),
            'total_ratio':total/total.rolling(baseline,min_periods=minimum).mean().where(lambda v:v>0)}
        for (kind,window),scale in scales.items():
            denominator=scale.where(lambda v:np.isfinite(v)&v.gt(0))
            for volume_kind,multiplier in multipliers.items():
                factor=multiplier/denominator
                factor=factor.where(np.isfinite(factor))
                for lag in (0,5):
                    result[f'fixed_ohlc_{kind}_{window}_{volume_kind}_b{baseline}_lag{lag}']=factor.shift(lag)
    return pd.DataFrame(result,index=series.index)


def contract_factors(series, windows=WINDOWS, shorts=SHORTS):
    """One fixed expiry/strike, on the common index clock, never filled."""
    result={}
    for side in ('ce','pe'):
        price=series[f'{side}_ltp'];volume=series[f'{side}_volume']
        elapsed=pd.Series(series.index,index=series.index).diff()
        old=price.shift()
        returns=(price/old-1).where((elapsed==pd.Timedelta(minutes=1))&(old>0)&(price>0))
        for w in windows:
            minimum=int(np.ceil(.8*w))
            for label,v in (('same_return',returns),('log_return',np.log1p(returns)),('price_std',price)):
                result[f'{side}_fixed_{label}_{w}']=v.rolling(w,min_periods=minimum).std()
            denominator=volume.rolling(w,min_periods=minimum).mean().where(lambda v:v>0)
            for short in shorts:
                result[f'{side}_fixed_volume_ratio_{short}_{w}']=volume.rolling(short,min_periods=short).mean()/denominator
    frame=pd.DataFrame(result,index=series.index)
    for w in windows:
        for kind in ('same_return','log_return','price_std'):
            frame[f'fixed_{kind}_{w}']=frame[f'ce_fixed_{kind}_{w}']+frame[f'pe_fixed_{kind}_{w}']
        for short in shorts:
            frame[f'fixed_volume_ratio_{short}_{w}']=(frame[f'ce_fixed_volume_ratio_{short}_{w}']+frame[f'pe_fixed_volume_ratio_{short}_{w}'])/2
    return frame[[c for c in frame if c.startswith('fixed_')]]


FIXED_RANK_VOLATILITIES=('adjacent_log_return','observed_log_return','price_std',
    'adjacent_five_minute_log_return','adjacent_log_rms')
FIXED_RANK_TAGS={'adjacent_log_return':'logstd','observed_log_return':'observedlogstd',
    'price_std':'pricestd','adjacent_five_minute_log_return':'five_minute_logstd',
    'adjacent_log_rms':'adjacentlogrms'}
FIXED_RANK_DESCRIPTIONS={
    'adjacent_log_return':'Sum CE+PE adjacent same-contract log-return STD150/300;80% minimum;overnight/gap returns unknown.',
    'observed_log_return':'Sum CE+PE same-contract log-return STD150/300 between successive observed-clock rows;80% minimum;overnight/gap changes included only with both known positive prices;missing quote rows never skipped or filled.',
    'price_std':'Sum CE+PE fixed-contract nonnegative finite price STD150/300;80% minimum;prices never filled.',
    'adjacent_five_minute_log_return':'Sum CE+PE STD150/300 of log(current price / price.shift(5));80% minimum;all six prices positive and known and all five clock links exactly one minute;overlapping five-minute returns.',
    'adjacent_log_rms':'Sum CE+PE sqrt(rolling mean squared adjacent one-minute log return),windows150/300;80% minimum;overnight/gap returns unknown;no mean subtraction.'}


def fixed_rank_variant_paths(volatility='adjacent_log_return'):
    """Distinct cached products; the original variant retains its existing paths."""
    if volatility not in FIXED_RANK_VOLATILITIES:raise ValueError('Unknown fixed-rank volatility')
    suffix='' if volatility=='adjacent_log_return' else '_'+volatility
    destination=OPENING_FIXED_RANK_CACHE if not suffix else OPENING_FIXED_RANK_CACHE.with_name(
        f'provider_opening_fixed_contract_ranks{suffix}.csv.gz')
    return destination,OUTPUT/f'opening_fixed_rank{suffix}_chunks',OUTPUT/f'opening_fixed_rank{suffix}_design.json'


def contract_alpha2_ranks(series, price_changes, volatility='adjacent_log_return'):
    """Raw factors and ranks for ONE fixed expiry/strike, before ATM selection.

    Inputs share the observed decision clock. No contract quotes or returns are
    filled. The default masks returns across overnight or intraday clock gaps;
    observed_log_return includes those changes only when both consecutive
    observed-clock prices are known. price_std uses known nonnegative prices.
    Underlying changes must already be causally known at each decision minute.
    """
    if not series.index.equals(price_changes.index):
        raise ValueError('Contract quotes and underlying changes need the same clock')
    if series.index.has_duplicates or not series.index.is_monotonic_increasing:
        raise ValueError('Contract decision clock must be unique and ordered')
    expected=('close_old_open_h5','close_close_old_open_h5')
    if tuple(price_changes.columns)!=expected:
        raise ValueError('Expected the two original completed five-bar price changes')
    if volatility not in FIXED_RANK_VOLATILITIES:raise ValueError('Unknown fixed-rank volatility')
    tag=FIXED_RANK_TAGS[volatility]
    elapsed=pd.Series(series.index,index=series.index).diff()
    scales={};ratios={};current_prices=[]
    for side in ('ce','pe'):
        price=series[f'{side}_ltp'].where(lambda p:np.isfinite(p)&(p.ge(0) if volatility=='price_std' else p.gt(0)))
        current_prices.append(price.notna())
        volume=series[f'{side}_volume'].where(lambda v:np.isfinite(v)&v.ge(0))
        if volatility=='price_std':values=price
        elif volatility=='adjacent_five_minute_log_return':
            complete=price.rolling(6,min_periods=6).count().eq(6)
            links=elapsed.eq(pd.Timedelta(minutes=1)).astype(int).rolling(5,min_periods=5).sum().eq(5)
            values=np.log(price/price.shift(5)).where(complete&links)
        else:
            values=np.log(price/price.shift())
            if volatility in ('adjacent_log_return','adjacent_log_rms'):
                values=values.where(elapsed.eq(pd.Timedelta(minutes=1)))
        for window in (150,300):
            minimum=int(np.ceil(.8*window))
            scales[side,window]=(np.sqrt(values.pow(2).rolling(window,min_periods=minimum).mean())
                if volatility=='adjacent_log_rms' else values.rolling(window,min_periods=minimum).std())
        for baseline in (10,15,20):
            mean=volume.rolling(baseline,min_periods=int(np.ceil(.8*baseline))).mean()
            ratios[side,baseline]=volume/mean.where(mean.gt(0))
    result={}
    for change in expected:
        for baseline in (10,15,20):
            multiplier=(ratios['ce',baseline]+ratios['pe',baseline])/2
            for window in (150,300):
                scale=scales['ce',window]+scales['pe',window]
                factor=(multiplier/scale.where(scale.gt(0))).where(lambda v:np.isfinite(v))
                if volatility!='adjacent_log_return':
                    factor=factor.where(current_prices[0]&current_prices[1])
                for lag in (0,5):
                    name=f'{change}_native_v1_b{baseline}_{tag}{window}_lag{lag}'
                    raw=(price_changes[change]*factor.shift(lag)).where(lambda v:np.isfinite(v))
                    result[f'raw_{name}']=raw
                    result[f'rank_{name}']=raw.rolling(300,min_periods=270).rank(pct=True)
    return pd.DataFrame(result,index=series.index)


def prepare_opening_fixed_ranks(volatility='adjacent_log_return'):
    """Cached-only exact-contract ranks, selected AFTER every contract's rank."""
    destination,chunks_dir,design_path=fixed_rank_variant_paths(volatility)
    client=DhanHistoryClient(offline=True);calendar=ProviderCalendar()
    bars=pd.read_csv(BAR_CACHE,index_col=0)
    bars.index=pd.to_datetime(bars.index,utc=True).tz_convert(IST)+pd.Timedelta(minutes=1)
    index=bars.index
    if index.has_duplicates or not index.is_monotonic_increasing:
        raise ValueError('Underlying decision clock must be unique and ordered')
    changes=contract_rank_price_changes(bars)
    selected=pd.read_csv(OPENING_CACHE,usecols=['minute','expiry','atm_strike'])
    selected.minute=pd.to_datetime(selected.minute,utc=True).dt.tz_convert(IST)
    selected.expiry=pd.to_datetime(selected.expiry).dt.date
    chunks_dir.mkdir(exist_ok=True)
    previous=None;frames=[];quality=[];carry=610
    for number,(first,last) in enumerate(history_blocks()):
        current,quotes,conflicts=load_history(client,first,last,calendar=calendar,expiry_resolver=expiries_for)
        quotes,fixed=supplement_fixed_contracts(client,current,quotes,last,calendar,expiries_for,lot_size)
        clock=current.index+pd.Timedelta(minutes=1)
        stop=index.searchsorted(clock[-1])+1;start=max(0,index.searchsorted(clock[0])-carry)
        history_index=index[start:stop]
        history=pd.concat([previous,quotes]) if previous is not None else quotes
        if history.index.has_duplicates:raise ValueError('Duplicate carried contract quote keys')
        target=chunks_dir/f'{first}_{last}.csv.gz';cached=target.exists();by_contract=None
        if cached:
            frame=pd.read_csv(target);frame.minute=pd.to_datetime(frame.minute,utc=True).dt.tz_convert(IST)
            frame.expiry=pd.to_datetime(frame.expiry).dt.date
        else:
            wanted=selected.loc[selected.minute.isin(clock)].copy();results=[]
            by_contract=history.groupby(level=['expiry','strike'],sort=False)
            # Also emit unknown rows for an entirely absent selected contract.
            empty=pd.DataFrame(index=history_index,columns=['ce_ltp','pe_ltp','ce_volume','pe_volume'],dtype=float)
            for (expiry,strike),labels in wanted.groupby(['expiry','atm_strike'],sort=False):
                try:values=by_contract.get_group((expiry,strike)).droplevel(['expiry','strike']).reindex(history_index)
                except KeyError:values=empty
                factors=contract_alpha2_ranks(values,changes.reindex(history_index),volatility).reindex(pd.DatetimeIndex(labels.minute))
                factors['minute']=labels.minute.to_numpy();factors['expiry']=expiry;factors['atm_strike']=strike
                results.append(factors.reset_index(drop=True))
            frame=pd.concat(results,ignore_index=True);frame.to_csv(target,index=False)
        frames.append(frame)
        quality.append({'start':str(first),'end_exclusive':str(last),'rows':len(frame),'cached':cached,
            'conflicts':len(conflicts),'fixed_contract_source':fixed})
        # Retain history, not just this chunk: some terminal chunks have <610 bars.
        previous=history.loc[history.index.get_level_values('minute').isin(index[max(0,stop-carry):stop])].copy()
        print(f'Opening fixed-contract ranks {number+1}/{len(history_blocks())}: {len(frame):,} rows, cached={cached}',flush=True)
        # GroupBy retains the full quote panel; release it before loading the
        # next chunk so two large panels do not overlap unnecessarily.
        del quotes,history,conflicts,by_contract;gc.collect()
    result=pd.concat(frames,ignore_index=True).sort_values(['expiry','minute'])
    if result.duplicated(['minute','expiry']).any():raise ValueError('Duplicate opening-selected contract rank rows')
    result.to_csv(destination,index=False)
    design_path.write_text(json.dumps({
        'selection':'Completed index candle open, nearest ATM with lower tie; ranks calculated BEFORE selection separately for every exact expiry/strike.',
        'destination':str(destination),'rows':len(result),'warmup_carry':carry,
        'price_changes':{'close_old_open_h5':'(completed close - completed open.shift(5)) / completed open.shift(5)',
            'close_close_old_open_h5':'(completed close - completed close.shift(5)) / completed open.shift(5)'},
        'alpha1_scaling':'Original opening-price denominator retained; no additional volatility normalization.',
        'volume':'Arithmetic average CE and PE native volume / own same-contract rolling mean; short1; baselines10/15/20; 80% minimum.',
        'volatility_kind':volatility,
        'volatility':FIXED_RANK_DESCRIPTIONS[volatility],
        'current_quote':'Original adjacent-return factor behavior preserved. Alternative factor modes require known current CE/PE prices at the factor observation; lag5 uses that observation five known clock slots earlier.',
        'factor_lags':[0,5],'rank':'Each fixed contract raw alpha2 rolling300 percentile,270 valid minimum; current unavailable raw has unavailable rank.',
        'formula_count':24,'columns':list(result.columns),
        'known_rows':{c:int(result[c].notna().sum()) for c in result if c.startswith(('raw_','rank_'))},
        'causality':'Only cached historical quotes and completed underlying candles. No fill, neighboring strike substitution, source trades or source position resets.',
        'chunks':quality},indent=2,default=str))
    print(f'Saved {len(result):,} exact-contract rank rows to {destination.name}',flush=True)


def prepare_opening_fixed_rank_variants(volatilities):
    """Share only cached quote loading/grouping; each mode computes its own ranks.

    At most two modes run together. Already committed mode chunks are reused,
    while raw quotes are still loaded for the common610-observation carry.
    """
    modes=tuple(volatilities)
    if not 1<=len(modes)<=2:raise ValueError('Select one or two fixed-rank volatility modes')
    if len(set(modes))!=len(modes):raise ValueError('Duplicate fixed-rank volatility modes')
    paths={mode:fixed_rank_variant_paths(mode) for mode in modes}
    if len(modes)==1:return prepare_opening_fixed_ranks(modes[0])
    client=DhanHistoryClient(offline=True);calendar=ProviderCalendar()
    bars=pd.read_csv(BAR_CACHE,index_col=0)
    bars.index=pd.to_datetime(bars.index,utc=True).tz_convert(IST)+pd.Timedelta(minutes=1)
    index=bars.index
    if index.has_duplicates or not index.is_monotonic_increasing:
        raise ValueError('Underlying decision clock must be unique and ordered')
    changes=contract_rank_price_changes(bars)
    selected=pd.read_csv(OPENING_CACHE,usecols=['minute','expiry','atm_strike'])
    selected.minute=pd.to_datetime(selected.minute,utc=True).dt.tz_convert(IST)
    selected.expiry=pd.to_datetime(selected.expiry).dt.date
    for _,chunks_dir,_ in paths.values():chunks_dir.mkdir(exist_ok=True)
    frames={mode:[] for mode in modes};quality={mode:[] for mode in modes}
    previous=None;carry=610
    blocks=history_blocks()
    for number,(first,last) in enumerate(blocks):
        current,quotes,conflicts=load_history(client,first,last,calendar=calendar,expiry_resolver=expiries_for)
        quotes,fixed=supplement_fixed_contracts(client,current,quotes,last,calendar,expiries_for,lot_size)
        clock=current.index+pd.Timedelta(minutes=1)
        stop=index.searchsorted(clock[-1])+1;start=max(0,index.searchsorted(clock[0])-carry)
        history_index=index[start:stop]
        history=pd.concat([previous,quotes]) if previous is not None else quotes
        if history.index.has_duplicates:raise ValueError('Duplicate carried contract quote keys')
        targets={mode:paths[mode][1]/f'{first}_{last}.csv.gz' for mode in modes}
        cached={mode:targets[mode].exists() for mode in modes}
        pending=[mode for mode in modes if not cached[mode]]
        results={mode:[] for mode in pending};by_contract=None;values=None;factors=None
        if pending:
            wanted=selected.loc[selected.minute.isin(clock)]
            by_contract=history.groupby(level=['expiry','strike'],sort=False)
            empty=pd.DataFrame(index=history_index,columns=['ce_ltp','pe_ltp','ce_volume','pe_volume'],dtype=float)
            history_changes=changes.reindex(history_index)
            for (expiry,strike),labels in wanted.groupby(['expiry','atm_strike'],sort=False):
                try:values=by_contract.get_group((expiry,strike)).droplevel(['expiry','strike']).reindex(history_index)
                except KeyError:values=empty
                for mode in pending:
                    factors=contract_alpha2_ranks(values,history_changes,mode).reindex(pd.DatetimeIndex(labels.minute))
                    factors['minute']=labels.minute.to_numpy();factors['expiry']=expiry;factors['atm_strike']=strike
                    results[mode].append(factors.reset_index(drop=True))
        for mode in modes:
            if cached[mode]:
                frame=pd.read_csv(targets[mode]);frame.minute=pd.to_datetime(frame.minute,utc=True).dt.tz_convert(IST)
                frame.expiry=pd.to_datetime(frame.expiry).dt.date
            else:
                frame=pd.concat(results[mode],ignore_index=True);frame.to_csv(targets[mode],index=False)
            frames[mode].append(frame)
            quality[mode].append({'start':str(first),'end_exclusive':str(last),'rows':len(frame),
                'cached':cached[mode],'conflicts':len(conflicts),'fixed_contract_source':fixed})
        previous=history.loc[history.index.get_level_values('minute').isin(index[max(0,stop-carry):stop])].copy()
        print(f'Shared opening fixed-contract ranks {number+1}/{len(blocks)}: modes={modes}, cached={cached}',flush=True)
        # Release GroupBy and aligned temporary quote views before next load.
        del quotes,history,conflicts,by_contract,results
        if pending:del values,factors,empty,history_changes
        gc.collect()
    for mode in modes:
        destination,_,design_path=paths[mode]
        result=pd.concat(frames[mode],ignore_index=True).sort_values(['expiry','minute'])
        if result.duplicated(['minute','expiry']).any():raise ValueError('Duplicate opening-selected contract rank rows')
        result.to_csv(destination,index=False)
        design_path.write_text(json.dumps({
            'selection':'Completed index candle open, nearest ATM with lower tie; ranks calculated BEFORE selection separately for every exact expiry/strike.',
            'destination':str(destination),'rows':len(result),'warmup_carry':carry,
            'price_changes':{'close_old_open_h5':'(completed close - completed open.shift(5)) / completed open.shift(5)',
                'close_close_old_open_h5':'(completed close - completed close.shift(5)) / completed open.shift(5)'},
            'alpha1_scaling':'Original opening-price denominator retained; no additional volatility normalization.',
            'volume':'Arithmetic average CE and PE native volume / own same-contract rolling mean; short1; baselines10/15/20; 80% minimum.',
            'volatility_kind':mode,'volatility':FIXED_RANK_DESCRIPTIONS[mode],
            'current_quote':'Original adjacent-return factor behavior preserved. Alternative factor modes require known current CE/PE prices at the factor observation; lag5 uses that observation five known clock slots earlier.',
            'factor_lags':[0,5],'rank':'Each fixed contract raw alpha2 rolling300 percentile,270 valid minimum; current unavailable raw has unavailable rank.',
            'formula_count':24,'columns':list(result.columns),
            'known_rows':{c:int(result[c].notna().sum()) for c in result if c.startswith(('raw_','rank_'))},
            'causality':'Only cached historical quotes and completed underlying candles. No fill, neighboring strike substitution, source trades or source position resets.',
            'shared_history_modes':modes,'shared_history':'Loading, supplements, contract grouping and quote alignment shared; calculations and output caches independent.',
            'chunks':quality[mode]},indent=2,default=str))
        print(f'Saved {len(result):,} exact-contract rank rows to {destination.name}',flush=True)


def contract_rank_price_changes(bars):
    """Original price-normalized changes on an already shifted decision clock."""
    denominator=bars.open.shift(5)
    return pd.DataFrame({'close_old_open_h5':(bars.close-denominator)/denominator,
        'close_close_old_open_h5':(bars.close-bars.close.shift(5))/denominator},index=bars.index)


def main(opening_fixed=False):
    client=DhanHistoryClient(offline=True);calendar=ProviderCalendar()
    bars=pd.read_csv(BAR_CACHE,index_col=0)
    index=pd.to_datetime(bars.index,utc=True).tz_convert(IST)+pd.Timedelta(minutes=1)
    selected=pd.read_csv(OPENING_CACHE if opening_fixed else FEATURE_CACHE,usecols=['minute','expiry','atm_strike'])
    selected.minute=pd.to_datetime(selected.minute,utc=True).dt.tz_convert(IST)
    selected.expiry=pd.to_datetime(selected.expiry).dt.date
    chunks_dir=OUTPUT/('opening_fixed_factor_chunks' if opening_fixed else 'fixed_factor_chunks');chunks_dir.mkdir(exist_ok=True)
    windows=(10,15,20,60,150,300) if opening_fixed else WINDOWS
    shorts=(1,) if opening_fixed else SHORTS
    destination=OPENING_FIXED_CACHE if opening_fixed else FIXED_CACHE
    previous=None;frames=[]
    for number,(first,last) in enumerate(history_blocks()):
        # Loading a completed chunk is still needed to carry its final 300
        # observations into the next chunk's calculation after resumption.
        current,quotes,conflicts=load_history(client,first,last,calendar=calendar,expiry_resolver=expiries_for)
        quotes,_=supplement_fixed_contracts(client,current,quotes,last,calendar,expiries_for,lot_size)
        clock=current.index+pd.Timedelta(minutes=1)
        stop=index.searchsorted(clock[-1])+1;start=max(0,index.searchsorted(clock[0])-300)
        history_index=index[start:stop]
        history=pd.concat([previous,quotes]) if previous is not None else quotes
        target=chunks_dir/f'{first}_{last}.csv.gz'
        cached=target.exists();by_contract=None
        if cached:
            frame=pd.read_csv(target);frame.minute=pd.to_datetime(frame.minute,utc=True).dt.tz_convert(IST)
        else:
            wanted=selected.loc[selected.minute.isin(clock)].copy()
            results=[]
            by_contract=history.groupby(level=['expiry','strike'],sort=False)
            for (expiry,strike),labels in wanted.groupby(['expiry','atm_strike'],sort=False):
                try:values=by_contract.get_group((expiry,strike)).droplevel(['expiry','strike'])
                except KeyError:continue
                aligned=values.reindex(history_index)
                factors=contract_factors(aligned,windows,shorts).reindex(pd.DatetimeIndex(labels.minute))
                factors['minute']=labels.minute.to_numpy();factors['expiry']=expiry;factors['atm_strike']=strike
                results.append(factors.reset_index(drop=True))
            frame=pd.concat(results,ignore_index=True)
            frame.to_csv(target,index=False)
        frames.append(frame)
        previous=quotes.loc[quotes.index.get_level_values('minute').isin(index[max(0,stop-300):stop])].copy()
        print(f'Fixed-contract factors {number+1}/18: {len(frame):,} selected ATM rows, cached={cached}',flush=True)
        del quotes,history,by_contract,conflicts
        gc.collect()
    result=pd.concat(frames,ignore_index=True).sort_values(['expiry','minute'])
    if result.duplicated(['minute','expiry']).any():raise ValueError('Duplicate selected-contract factor timestamps')
    result.to_csv(destination,index=False)
    if opening_fixed:
        (OUTPUT/'opening_fixed_factor_design.json').write_text(json.dumps({
            'selection':'Completed index candle open, same expiry and selected ATM strike.',
            'source':str(OPENING_CACHE),'rows':len(result),'windows':windows,'volume_short_windows':shorts,
            'clock':'Common observed index decision minutes, reindexed independently for each fixed contract.',
            'returns':'Adjacent same-contract minute returns only; overnight, minute gaps and absent quotes are unknown.',
            'minimum_fraction':.8,'warmup_carry':300,
            'factor_known_rows':{column:int(result[column].notna().sum()) for column in result if column.startswith('fixed_')},
            'limitations':'Coverage counts are factor observations, not trade replication. Selection differs from existing close-selected FIXED_CACHE; neither source fills nor source positions enter factor calculations.'},indent=2))
    print(f'Saved {len(result):,} fixed-contract factor rows to {destination.name}',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--opening-reference',action='store_true',help='prepare an alternative ATM panel selected from completed index candle opens')
    parser.add_argument('--contract-cumulative',action='store_true',help='reconstruct cumulative daily volume of each actual opening-selected ATM contract')
    parser.add_argument('--opening-fixed',action='store_true',help='prepare opening-selected ATM factors from that exact strike\'s own rolling history')
    parser.add_argument('--opening-fixed-ranks',action='store_true',help='rank alpha2 independently within each fixed contract before opening-ATM selection')
    parser.add_argument('--opening-full-fields',action='store_true',help='download exact opening-selected CE/PE full fields with bounded rolling offsets')
    parser.add_argument('--opening-fixed-ohlc',action='store_true',help='prepare own-contract OHLC histories before opening ATM selection')
    parser.add_argument('--ohlc-limit-blocks',type=int,default=0,help='new own-contract OHLC blocks per invocation;0 means all')
    parser.add_argument('--ohlc-offline',action='store_true',help='own-contract OHLC preparation from existing raw cache only')
    parser.add_argument('--full-field-limit-blocks',type=int,default=0,help='new full-field chunks per invocation;0 means all')
    parser.add_argument('--fixed-rank-volatility',choices=FIXED_RANK_VOLATILITIES,default=None,
        help='volatility convention for --opening-fixed-ranks; default adjacent_log_return')
    parser.add_argument('--fixed-rank-volatilities',choices=FIXED_RANK_VOLATILITIES,nargs='+',default=None,
        help='one or two independent fixed-rank modes sharing cached quote loading')
    args=parser.parse_args()
    if sum((args.opening_reference,args.contract_cumulative,args.opening_fixed,args.opening_fixed_ranks,args.opening_full_fields,args.opening_fixed_ohlc))>1:parser.error('Select one option-factor preparation')
    if args.ohlc_limit_blocks<0 or ((args.ohlc_limit_blocks or args.ohlc_offline) and not args.opening_fixed_ohlc):parser.error('OHLC options require --opening-fixed-ohlc and nonnegative block limit')
    if args.full_field_limit_blocks<0 or (args.full_field_limit_blocks and not args.opening_full_fields):parser.error('Full-field block limit requires --opening-full-fields and must be nonnegative')
    if args.fixed_rank_volatility is not None and not args.opening_fixed_ranks:
        parser.error('--fixed-rank-volatility requires --opening-fixed-ranks')
    if args.fixed_rank_volatilities is not None:
        if not args.opening_fixed_ranks:parser.error('--fixed-rank-volatilities requires --opening-fixed-ranks')
        if args.fixed_rank_volatility is not None:parser.error('Choose singular or plural volatility flag')
        if len(args.fixed_rank_volatilities)>2:parser.error('Select at most two volatility modes')
        if len(set(args.fixed_rank_volatilities))!=len(args.fixed_rank_volatilities):parser.error('Duplicate volatility modes')
    if args.contract_cumulative:prepare_contract_cumulative()
    elif args.opening_reference:prepare_opening_features()
    elif args.opening_fixed:main(opening_fixed=True)
    elif args.opening_full_fields:prepare_opening_full_fields(limit_blocks=args.full_field_limit_blocks)
    elif args.opening_fixed_ohlc:prepare_opening_fixed_ohlc(limit_blocks=args.ohlc_limit_blocks,offline=args.ohlc_offline)
    elif args.opening_fixed_ranks:
        if args.fixed_rank_volatilities is not None:prepare_opening_fixed_rank_variants(args.fixed_rank_volatilities)
        else:prepare_opening_fixed_ranks(args.fixed_rank_volatility or 'adjacent_log_return')
    else:main()
