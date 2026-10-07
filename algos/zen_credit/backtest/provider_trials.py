"""Resumable formula trials scored against published entries and flat controls.

No broker orders. Exact source timestamps are labels, never predictors. Selection
uses the first chronological fit period; later periods are reported separately.
"""
from __future__ import annotations
import argparse
from dataclasses import asdict,replace
from datetime import datetime,date,time
import json
import csv
import hashlib
from collections import OrderedDict
from pathlib import Path
import numpy as np
import pandas as pd
from backtest.provider_research import BAR_CACHE,FEATURE_CACHE,ENTRY_QUOTE_CACHE,OUTPUT,provider_trades
from backtest.provider_calendar import expiries_for,ProviderCalendar,lot_size,history_config
from backtest.provider_triggers import context
from config import REPO_ROOT,StrategyConfig
from utils.time import IST

OUT=OUTPUT/'replication_trials'
SPLITS=('fit','validation','evaluation','case_study')
CROSS_VOLUME_KINDS=('put_call_ratio','call_put_ratio','reciprocal_put_call','literal_put_call',
    'literal_call_put','literal_reciprocal_put_call','mean_put_call','mean_reciprocal_put_call')
BULK_CONTEXTS=('continuous_near','expiry_near')
BULK_KINDS=('native','geometric_ratios','harmonic_ratios','minimum_ratios','total_ratio',
    'put_call_ratio','call_put_ratio','reciprocal_put_call')
BULK_ALPHAS=tuple(f'{kind}_h5_r800' for kind in ('close_close_old_open','close_close_current_open',
    'body_h','close_old_open','open_open'))
BULK_SHORTS=(1,2,3,5,15)
BULK_BASELINES=(10,15,20,30,60,300)
BULK_VOLATILITIES=tuple(f'{kind}_{window}' for kind in ('same_return','log_return') for window in (20,60,150,300))
BULK_LAGS=tuple(range(8))
BULK_POLICY='opening-native-completed-v1;volume-min80;std-min80;rank-min90;alpha-min100;no-fill'


def bulk_shard_spec(shard):
    if not isinstance(shard,int) or isinstance(shard,bool) or not 0<=shard<16:
        raise ValueError('Bulk shard must be an integer from 0 through 15')
    return BULK_CONTEXTS[shard//8],BULK_KINDS[shard%8]


def bulk_recipe(context_name,kind,short,baseline,volatility,lag):
    return {'context':context_name,'volume_kind':kind,'volume_short':short,'volume_baseline':baseline,
        'volatility':volatility,'factor_lag':lag,'rank_window':300,'price_change':'same_as_alpha_v2',
        'atm_reference':'last_completed_bar_open','input_policy':BULK_POLICY}


def bulk_grid(shard):
    """Finite parameter identities; actual signal uniqueness is measured separately."""
    context_name,kind=bulk_shard_spec(shard)
    for short in BULK_SHORTS:
        for baseline in BULK_BASELINES:
            for volatility in BULK_VOLATILITIES:
                for lag in BULK_LAGS:
                    recipe=bulk_recipe(context_name,kind,short,baseline,volatility,lag)
                    for alpha in BULK_ALPHAS:yield alpha,recipe


def bulk_manifest(shard):
    context_name,kind=bulk_shard_spec(shard)
    return {'schema_version':1,'shard':shard,'context':context_name,'volume_kind':kind,
        'parameter_pairs_per_shard':9600,'formula_recipes_per_shard':1920,'shards':16,
        'parameter_pairs_total':153600,'alphas':list(BULK_ALPHAS),'short_windows':list(BULK_SHORTS),
        'baseline_windows':list(BULK_BASELINES),'volatilities':list(BULK_VOLATILITIES),
        'factor_lags':list(BULK_LAGS),'rank_windows':{'alpha':800,'alpha2':300},'thresholds':[.8,.2],
        'input_policy':BULK_POLICY,'selection':'Fit conditional first-exact, direction passes, fewer signal episodes.',
        'limits':['Parameter identities are not guaranteed distinct signals.',
            'Conditional screens use published position history and are not autonomous replication evidence.',
            'Existing later periods were inspected before and are not untouched holdouts.',
            'Full independent replay and quote-coverage audit are required for retained candidates.']}


def prune_bulk_archives(directory,frontier):
    """Drop generated, unselected rank archives after frontier persistence."""
    root=(OUTPUT/'replication_trials'/'bulk').resolve()
    directory=directory.resolve()
    if not directory.is_relative_to(root) or directory==root:
        raise ValueError('Archive pruning is restricted to bulk shard directories')
    retained={f['candidate_id'] for f in frontier}
    for path in directory.glob('candidate_*.npz'):
        cid=path.stem.removeprefix('candidate_')
        if len(cid)!=16 or any(c not in '0123456789abcdef' for c in cid):continue
        replayed=any(root.glob(f'full_autonomous_{cid}_*')) or any(directory.glob(f'full_autonomous_{cid}_*'))
        if cid not in retained and not replayed:path.unlink()


class ExpiryFactorTransforms:
    """Apply the same Series operation by expiry with contiguous positional slices.

    Unsorted/noncontiguous groups retain the original label-based path. Outputs
    start missing, so absent expiry groups never acquire invented observations.
    """
    def __init__(self,index,groups):
        self.index=index;self.groups=list(groups.values());self.slices=None
        if index.equals(pd.RangeIndex(len(index))):
            slices=[]
            for ids in self.groups:
                start=int(ids[0]);stop=int(ids[-1])+1
                if not np.array_equal(np.asarray(ids),np.arange(start,stop)):break
                slices.append((start,stop))
            else:self.slices=slices

    def transform(self,series,fn):
        if not series.index.equals(self.index):raise ValueError('Expiry factor indices differ')
        if self.slices is None:
            out=pd.Series(np.nan,index=self.index)
            for ids in self.groups:out.loc[ids]=fn(series.loc[ids]).to_numpy()
            return out
        values=np.full(len(series),np.nan)
        for start,stop in self.slices:values[start:stop]=fn(series.iloc[start:stop]).to_numpy()
        return pd.Series(values,index=self.index)


class FactorLagCache:
    """Reuse unchanged factor shifts within one context, preserving group edges.

    Caller identities name immutable series. Finite entry limits bound memory;
    the bulk volatility bank has 8 definitions times 8 lags.
    """
    def __init__(self, grouped, max_entries=64):
        self.grouped=grouped;self.max_entries=max_entries;self.values=OrderedDict()

    def shift(self, series, identity, lag):
        key=(identity,lag)
        if key in self.values:
            self.values.move_to_end(key);return self.values[key]
        value=self.grouped(series,lambda s:s.shift(lag))
        if self.max_entries>0:
            self.values[key]=value
            while len(self.values)>self.max_entries:self.values.popitem(last=False)
        return value


class RollingMeanCache:
    """Context-local LRU for identical trailing means, bounded by array bytes.

    Caller identities identify the unchanged source series within one context.
    Indices are shared with that context. Windows and minimum coverage are part
    of each key; numerators and denominators must never reuse different rules.
    """
    def __init__(self,grouped=None,max_bytes=64*1024*1024):
        self.grouped=grouped or (lambda s,fn:fn(s))
        self.max_bytes=max_bytes;self.bytes=0;self.hits=0;self.misses=0
        self.values=OrderedDict()

    def mean(self,series,identity,window,min_periods):
        key=(identity,window,min_periods)
        if key in self.values:
            self.hits+=1;self.values.move_to_end(key);return self.values[key]
        self.misses+=1
        value=self.grouped(series,lambda s:s.rolling(window,min_periods=min_periods).mean())
        size=int(value.memory_usage(index=False,deep=True))
        if size<=self.max_bytes:
            while self.values and self.bytes+size>self.max_bytes:
                _,old=self.values.popitem(last=False)
                self.bytes-=int(old.memory_usage(index=False,deep=True))
            self.values[key]=value;self.bytes+=size
        return value


def cross_volume_multiplier(ce,pe,kind,short,baseline,grouped=None):
    """Alternative CE/PE candle-volume ratios using trailing observations only.

    Ratio of rolling means differs from rolling mean of minute ratios. Normalized
    variants divide the chosen ratio by its trailing baseline mean. Zero/missing
    denominators remain missing, never substituted with a small constant.
    """
    if kind not in CROSS_VOLUME_KINDS or short<1 or baseline<1:raise ValueError('Invalid cross-volume recipe')
    grouped=(lambda s,fn:fn(s)) if grouped is None else grouped
    ce=ce.where(np.isfinite(ce)&(ce>=0));pe=pe.where(np.isfinite(pe)&(pe>=0))
    def average(s):return grouped(s,lambda v:v.rolling(short,min_periods=short).mean())
    if kind.startswith('mean_'):
        ratio=pe/ce.where(ce>0)
        if kind=='mean_reciprocal_put_call':ratio=(ratio+1/ratio.where(ratio>0))/2
        return average(ratio)
    c=average(ce);p=average(pe);ratio=p/c.where(c>0)
    if kind in ('call_put_ratio','literal_call_put'):ratio=c/p.where(p>0)
    elif kind in ('reciprocal_put_call','literal_reciprocal_put_call'):
        ratio=(ratio+1/ratio.where(ratio>0))/2
    if kind.startswith('literal_'):return ratio
    denominator=grouped(ratio,lambda v:v.rolling(baseline,min_periods=int(np.ceil(.8*baseline))).mean())
    return ratio/denominator.where(denominator>0)


def premium_limits(gate,expiry_day):
    """Research-only premium bounds; expiry is contract state, not a fitted date."""
    normal=float(gate['normal_day_min']);expiry=float(gate['expiry_day_min'])
    maximum=float(gate['maximum'])
    if not all(np.isfinite(v) for v in (normal,expiry,maximum)) or min(normal,expiry)<0 or maximum<=0 or max(normal,expiry)>maximum:
        raise ValueError('Invalid research premium bounds')
    return np.where(expiry_day,expiry,normal),maximum


def premium_eligibility(index,candidate,quotes=None):
    """Boolean columns PE/bullish, CE/bearish, aligned to decision minutes.

    Cached quotes use the last completed candle open to choose the short ATM.
    No filling or source trade prices; absent/invalid current quotes fail closed.
    """
    gate=candidate['recipe'].get('premium_gate')
    if gate is None:return None
    if quotes is None:
        quotes=pd.read_csv(ENTRY_QUOTE_CACHE)
        quotes.index=pd.to_datetime(quotes.pop('minute'),utc=True).dt.tz_convert(IST)
    if quotes.index.has_duplicates:raise ValueError('Duplicate research entry quote minutes')
    selected=quotes.reindex(index)
    expiry=pd.to_datetime(selected.expiry).dt.date.to_numpy()
    minimum,maximum=premium_limits(gate,expiry==index.date)
    prices=selected[['pe_ltp','ce_ltp']].to_numpy(dtype=float)
    return np.isfinite(prices)&(prices>0)&(prices>=minimum[:,None])&(prices<=maximum)&pd.notna(expiry)[:,None]


def entry_event_mask(alpha,alpha2,mode='level',comparison='strict'):
    """Causal PE/CE crossing masks from successive completed trading observations.

    The prior rank is checked before applying the entry clock or position state.
    Session opening and becoming flat do not reset a rank that is already extreme.
    Missing prior ranks cannot establish a fresh crossing.
    """
    if mode=='level':return None
    if mode not in ('joint','alpha','alpha2','both'):raise ValueError('Unknown entry crossing mode')
    a=np.asarray(alpha,dtype=float);b=np.asarray(alpha2,dtype=float)
    if a.shape!=b.shape or a.ndim!=1:raise ValueError('Unaligned entry crossing ranks')
    cfg=threshold_config(StrategyConfig(),comparison)
    left=np.column_stack((a>cfg.bullish_threshold,a<cfg.bearish_threshold))
    right=np.column_stack((b>cfg.bullish_threshold,b<cfg.bearish_threshold))
    pa=np.vstack((np.zeros((1,2),dtype=bool),left[:-1]))[:len(a)]
    pb=np.vstack((np.zeros((1,2),dtype=bool),right[:-1]))[:len(a)]
    prior_known=np.r_[False,np.isfinite(a[:-1])&np.isfinite(b[:-1])][:len(a)]
    changed=~(pa&pb) if mode=='joint' else ~pa if mode=='alpha' else ~pb if mode=='alpha2' else ~pa&~pb
    return left&right&changed&prior_known[:,None]


def signal_sequence_signature(index,alpha,alpha2,candidate,cutoff=None):
    """Hash directional rank proposals plus gates, without source-trade labels.

    This identifies potential replay duplicates. Reusing outcomes additionally
    requires identical raw quotes, execution config, period and initial state.
    Crossing masks are calculated before cutting the chronological prefix.
    """
    index=pd.DatetimeIndex(index)
    a=np.asarray(alpha,dtype=float);b=np.asarray(alpha2,dtype=float)
    if index.tz is None or index.has_duplicates or not index.is_monotonic_increasing:
        raise ValueError('Signal signatures need unique chronological aware minutes')
    index=index.tz_convert(IST)
    if a.shape!=b.shape or a.shape!=(len(index),):raise ValueError('Unaligned signal signature inputs')
    recipe=candidate['recipe'];comparison=recipe.get('threshold_comparison','strict')
    cfg=threshold_config(StrategyConfig(),comparison)
    signals=np.column_stack(((a>cfg.bullish_threshold)&(b>cfg.bullish_threshold),
                             (a<cfg.bearish_threshold)&(b<cfg.bearish_threshold)))
    events=entry_event_mask(a,b,recipe.get('entry_event','level'),comparison)
    if events is not None:signals&=events
    keep=np.ones(len(index),dtype=bool) if cutoff is None else index.date<=cutoff
    policy={'premium_gate':recipe.get('premium_gate'),
            'profit_target_mode':recipe.get('profit_target_mode','configured'),
            'reentry_after_exit':recipe.get('reentry_after_exit',False)}
    if not isinstance(policy['reentry_after_exit'],bool):raise ValueError('reentry_after_exit must be boolean')
    digest=hashlib.sha256(json.dumps(policy,sort_keys=True,separators=(',',':')).encode())
    digest.update(index[keep].as_unit('ns').asi8.tobytes())
    digest.update(signals[keep].astype(np.uint8).tobytes())
    return digest.hexdigest()


def candidate_entry_allowed(index,candidate,alpha,alpha2,quotes=None):
    premium=premium_eligibility(index,candidate,quotes)
    event=entry_event_mask(alpha,alpha2,candidate['recipe'].get('entry_event','level'),
        candidate['recipe'].get('threshold_comparison','strict'))
    if event is not None and event.shape!=(len(index),2):raise ValueError('Entry event minutes differ')
    return event if premium is None else premium if event is None else premium&event


def apply_research_gates(replay,candidate):
    """Apply explicit candidate entry gates and an optional no-target control."""
    gate=candidate['recipe'].get('premium_gate')
    event_mode=candidate['recipe'].get('entry_event','level')
    target_mode=candidate['recipe'].get('profit_target_mode','configured')
    if target_mode not in ('configured','disabled'):raise ValueError('Unknown research profit-target mode')
    if gate is None and event_mode=='level' and target_mode=='configured':return
    events=None
    if event_mode!='level':
        inputs=replay._indicator_frame()
        if inputs.index.has_duplicates or not inputs.index.is_monotonic_increasing:
            raise ValueError('Crossing inputs need unique ordered decision minutes')
        events=pd.DataFrame(entry_event_mask(inputs.alpha,inputs.alpha2,event_mode,
            candidate['recipe'].get('threshold_comparison','strict')),index=inputs.index,columns=['PE','CE'])
    from strategy.engine import EngineResult
    original=replay.engine.evaluate
    def evaluate(view,position):
        result=original(view,position)
        if position is not None or result.action!='entry':return result
        if target_mode=='disabled':
            result.position=replace(result.position,target=None)
            result.diagnostics={**result.diagnostics,'profit_target_mode':'disabled','target':None}
        proposed=result.position
        if events is not None:
            minute=pd.Timestamp(view.now).floor('min')
            if minute not in events.index or not bool(events.loc[minute,proposed.option_type]):
                return EngineResult('none','research entry crossing',diagnostics={**result.diagnostics,'entry_event':event_mode})
        if gate is None:return result
        minimum,maximum=premium_limits(gate,proposed.expiry==proposed.entry_ts.date())
        price=proposed.sell_price
        if price is None or not np.isfinite(price) or price<=0 or not minimum<=price<=maximum:
            return EngineResult('none','research premium eligibility',diagnostics={**result.diagnostics,
                'short_premium':price,'minimum_short_premium':float(minimum),'maximum_short_premium':maximum})
        return result
    replay.engine.evaluate=evaluate


def threshold_config(cfg,comparison='strict'):
    """Research comparison semantics without changing the nominal cutoff values.

    The service uses strict comparisons. Moving its comparison boundary by one
    representable float implements equality in replay, without a fuzzy tolerance.
    """
    if comparison not in ('strict','inclusive','bearish_inclusive','bullish_inclusive'):
        raise ValueError('Unknown threshold comparison')
    return replace(cfg,
        bullish_threshold=float(np.nextafter(cfg.bullish_threshold,-np.inf)) if comparison in ('inclusive','bullish_inclusive') else cfg.bullish_threshold,
        bearish_threshold=float(np.nextafter(cfg.bearish_threshold,np.inf)) if comparison in ('inclusive','bearish_inclusive') else cfg.bearish_threshold)


def rank(s,w=300,fraction=.9,reset=False):
    if reset:
        return s.groupby(s.index.date,group_keys=False).transform(lambda v:v.rolling(w,min_periods=min(20,w)).rank(pct=True))
    return s.rolling(w,min_periods=int(np.ceil(w*fraction))).rank(pct=True)


def provisional_rank(history,current,w=800):
    """Append a known current-minute price to prior completed-bar changes.

    The provisional value is ranked against the last w-1 completed changes;
    current-minute high, low, close and volume never enter this calculation.
    """
    h=history.to_numpy(dtype=float);c=current.to_numpy(dtype=float)
    windows=np.lib.stride_tricks.sliding_window_view(np.pad(h,(w-2,0),constant_values=np.nan),w-1)
    out=np.full(len(h),np.nan)
    for start in range(0,len(h),512):
        stop=min(start+512,len(h));v=windows[start:stop];cur=c[start:stop,None]
        valid=np.isfinite(v).sum(axis=1)
        numerator=(v<cur).sum(axis=1)+((v==cur).sum(axis=1)+2)/2
        ok=(valid==w-1)&np.isfinite(c[start:stop])
        out[start:stop]=np.where(ok,numerator/w,np.nan)
    return pd.Series(out,index=history.index)


def sampled_rank(history,current,sample_mask,w):
    """Rank current known value against w-1 strictly earlier sampled values.

    Sampling changes the historical observation frequency, never the entry
    eligibility clock. Missing values remain missing; no forward filling.
    """
    if w<2:raise ValueError('sampled rank needs at least two observations')
    if len(history)!=len(current) or len(history)!=len(sample_mask):raise ValueError('Unaligned sampled rank inputs')
    h=np.asarray(history,dtype=float);c=np.asarray(current,dtype=float)
    selected=np.flatnonzero(sample_mask)
    previous=np.searchsorted(selected,np.arange(len(h)),side='left')
    out=np.full(len(h),np.nan)
    if not len(selected):return pd.Series(out,index=history.index)
    offsets=np.arange(w-1,0,-1)
    for start in range(0,len(h),512):
        stop=min(start+512,len(h));ids=previous[start:stop,None]-offsets
        v=h[selected[np.clip(ids,0,len(selected)-1)]]
        valid=(ids>=0)&np.isfinite(v);cur=c[start:stop,None]
        numerator=((v<cur)&valid).sum(axis=1)+(((v==cur)&valid).sum(axis=1)+2)/2
        ok=valid.all(axis=1)&np.isfinite(c[start:stop])
        out[start:stop]=np.where(ok,numerator/w,np.nan)
    return pd.Series(out,index=history.index)


class Scorer:
    def __init__(self,index):
        self.index=index;self.trades=provider_trades();t=self.trades
        self.entries=index.get_indexer(t.entry_minute)
        if (self.entries<0).any():raise ValueError('Missing published entry bar')
        self.directions=t.direction.to_numpy()
        self.eligible=(index>=t.entry_minute.min())&((index.hour*60+index.minute>=615)&(index.hour*60+index.minute<=855))
        self.flat=np.ones(len(index),dtype=bool)
        for row in t.itertuples():
            self.flat[(index>row.entry_minute)&(index<=row.exit_minute)]=False
        self.flat[self.entries]=True
        self.starts=np.array([self.entries[0]]+[index.searchsorted(v+pd.Timedelta(minutes=1)) for v in t.exit_minute.iloc[:-1]])
        self.minute_split=np.select([index.date<=date(2026,2,28),index.date<=date(2026,6,30),index.date<=date(2026,8,31)],['fit','validation','evaluation'],default='case_study')
        self.trade_masks={s:t.split.eq(s).to_numpy() for s in SPLITS}
        self.minute_masks={s:self.minute_split==s for s in SPLITS}
        self.day_start=np.r_[True,index.date[1:]!=index.date[:-1]]
        self.minute_ns=index.as_unit('ns').asi8

    def score(self,a,b=None,comparison='strict',allowed=None):
        a=np.asarray(a);b=a if b is None else np.asarray(b)
        cfg=threshold_config(StrategyConfig(),comparison)
        signal=np.where((a>cfg.bullish_threshold)&(b>cfg.bullish_threshold),1,np.where((a<cfg.bearish_threshold)&(b<cfg.bearish_threshold),-1,0)).astype(np.int8)
        if allowed is not None:
            allowed=np.asarray(allowed,dtype=bool)
            if allowed.shape!=(len(signal),2):raise ValueError('Premium eligibility must have PE and CE columns')
            signal[((signal==1)&~allowed[:,0])|((signal==-1)&~allowed[:,1])]=0
        signal[~self.eligible]=0
        matches=signal[self.entries]==self.directions
        n=len(signal)
        next_hit=np.minimum.accumulate(np.where(signal!=0,np.arange(n),n)[::-1])[::-1]
        first=next_hit[np.minimum(self.starts,n-1)]
        exact=(self.starts<n)&(self.starts<=self.entries)&(first==self.entries)&matches
        near=(self.starts<n)&(self.starts<=self.entries)&(first<=self.entries)&(first<n)
        candidate=np.minimum(first,n-1)
        near&=(self.index[self.entries]-self.index[candidate]).total_seconds()<=120
        near&=signal[candidate]==self.directions
        hit=(signal!=0)&self.flat
        extra=hit.copy();extra[self.entries]&=~matches
        episodes=hit&((np.r_[0,signal[:-1]]!=signal)|~np.r_[False,self.flat[:-1]]|self.day_start)
        result={}
        for s in SPLITS:
            tm,mm=self.trade_masks[s],self.minute_masks[s]
            result.update({f'{s}_trades':int(tm.sum()),f'{s}_available':int((np.isfinite(a[self.entries])&np.isfinite(b[self.entries])&tm).sum()),
                f'{s}_direction_matches':int((matches&tm).sum()),f'{s}_first_exact':int((exact&tm).sum()),
                f'{s}_first_within_2m':int((near&tm).sum()),f'{s}_extra_signal_minutes':int((extra&mm).sum()),
                f'{s}_signal_episodes':int((episodes&mm).sum())})
        return result,signal

    def score_batch(self,a,b=None,comparison='strict'):
        """Exact scalar-score semantics on at most 64 pair rows, time last.

        Batches avoid per-candidate Python reductions while bounding temporary
        rank and signal matrices. Entry gates have their separate scalar path.
        """
        a=np.asarray(a);b=a if b is None else np.asarray(b)
        if a.ndim!=2 or b.shape!=a.shape or a.shape[1]!=len(self.index) or not 1<=len(a)<=64:
            raise ValueError('Batch must have 1..64 aligned pair rows')
        cfg=threshold_config(StrategyConfig(),comparison);n=len(self.index);k=len(a)
        signal=np.where((a>cfg.bullish_threshold)&(b>cfg.bullish_threshold),1,
            np.where((a<cfg.bearish_threshold)&(b<cfg.bearish_threshold),-1,0)).astype(np.int8)
        signal[:,~self.eligible]=0
        matches=signal[:,self.entries]==self.directions
        next_hit=np.minimum.accumulate(np.where(signal!=0,np.arange(n),n)[:,::-1],axis=1)[:,::-1]
        first=next_hit[:,np.minimum(self.starts,n-1)]
        exact=(self.starts<n)&(self.starts<=self.entries)&(first==self.entries)&matches
        near=(self.starts<n)&(self.starts<=self.entries)&(first<=self.entries)&(first<n)
        candidate=np.minimum(first,n-1)
        near&=(self.minute_ns[self.entries]-self.minute_ns[candidate])<=120_000_000_000
        near&=np.take_along_axis(signal,candidate,axis=1)==self.directions
        hit=(signal!=0)&self.flat
        extra=hit.copy();extra[:,self.entries]&=~matches
        previous=np.concatenate((np.zeros((k,1),dtype=np.int8),signal[:,:-1]),axis=1)
        previous_flat=np.r_[False,self.flat[:-1]]
        episodes=hit&((previous!=signal)|~previous_flat|self.day_start)
        available=np.isfinite(a[:,self.entries])&np.isfinite(b[:,self.entries])
        vectors={}
        for split in SPLITS:
            tm,mm=self.trade_masks[split],self.minute_masks[split]
            vectors.update({split+'_trades':np.full(k,int(tm.sum())),
                split+'_available':available[:,tm].sum(axis=1),
                split+'_direction_matches':matches[:,tm].sum(axis=1),
                split+'_first_exact':exact[:,tm].sum(axis=1),
                split+'_first_within_2m':near[:,tm].sum(axis=1),
                split+'_extra_signal_minutes':extra[:,mm].sum(axis=1),
                split+'_signal_episodes':episodes[:,mm].sum(axis=1)})
        return [{name:int(value[i]) for name,value in vectors.items()} for i in range(k)],signal


def alpha_bank(bars):
    """Documented lookback plus explicit alternative alignments/window semantics."""
    bank={};recipes={};changes={}
    for h in (3,4,5,6,10):
        variants={
            'close_close_old_open':(bars.close-bars.close.shift(h))/bars.open.shift(h),
            'close_close_current_open':(bars.close-bars.close.shift(h))/bars.open,
            'body_h':(bars.close-bars.open.shift(h-1))/bars.open.shift(h-1),
            'close_old_open':(bars.close-bars.open.shift(h))/bars.open.shift(h),
            'open_open':(bars.open-bars.open.shift(h))/bars.open.shift(h)}
        for label,change in variants.items():
            key=f'{label}_h{h}';changes[key]=change
            for w in ((800,300,1600) if h==5 else (800,)):
                name=f'{key}_r{w}';bank[name]=rank(change,w,1)
                recipes[name]={'kind':label,'horizon':h,'rank_window':w,'session_reset':False,'causal':'completed bars only'}
            if h==5:
                name=f'{key}_session_r800';bank[name]=rank(change,800,reset=True)
                recipes[name]={'kind':label,'horizon':h,'rank_window':800,'session_reset':True,'causal':'completed bars only; session-reset alternative'}
    # bars row T represents the completed bar starting T-1. Next row's opening
    # price starts exactly at T and is known at decision T, without its future
    # close/high/low/volume. Session boundaries and missing minutes fail closed.
    contiguous=pd.Series(bars.index,index=bars.index).shift(-1)-pd.Series(bars.index,index=bars.index)==pd.Timedelta(minutes=1)
    current_open=bars.open.shift(-1).where(contiguous)
    for h in (4,5,6):
        hist=(bars.close-bars.close.shift(h))/bars.open.shift(h)
        current=(current_open-bars.close.shift(h-1))/bars.open.shift(h-1)
        key=f'current_open_provisional_h{h}_r800'
        bank[key]=provisional_rank(hist,current)
        changes[key]=current
        recipes[key]={'kind':'current_open_provisional','horizon':h,'rank_window':800,'session_reset':False,
            'causal':'current minute opening price, prior completed changes; no current-minute close/volume'}
        # A completed bar ends one minute after its labelled opening. Its
        # h-minute open-to-close span therefore starts h-1 bar offsets back.
        hist=(bars.close-bars.open.shift(h-1))/bars.open.shift(h-1)
        current=(current_open-bars.open.shift(h-1))/bars.open.shift(h-1)
        key=f'current_open_from_open_h{h}_r800'
        bank[key]=provisional_rank(hist,current)
        changes[key]=current
        recipes[key]={'kind':'current_open_from_open','horizon':h,'rank_window':800,'session_reset':False,
            'causal':'current minute opening price versus prior opening, ranked against completed open-to-close changes'}
    return bank,recipes,changes


def prepare_alpha():
    OUT.mkdir(parents=True,exist_ok=True)
    bars,_,_=context();bank,recipes,changes=alpha_bank(bars);scorer=Scorer(bars.index)
    records=[]
    for key,series in bank.items():
        r,_=scorer.score(series);records.append({'alpha':key,**r})
    table=pd.DataFrame(records).sort_values(['fit_direction_matches','fit_first_exact'],ascending=False)
    table.to_csv(OUT/'alpha_trials.csv',index=False)
    np.savez_compressed(OUT/'alpha_bank.npz',minutes=bars.index.as_unit('ns').asi8,names=np.array(list(bank),dtype=str),values=np.column_stack(list(bank.values())))
    (OUT/'alpha_recipes.json').write_text(json.dumps(recipes,indent=2))
    print(table[['alpha','fit_direction_matches','validation_direction_matches','evaluation_direction_matches','case_study_direction_matches','fit_first_exact']].head(12).to_string(index=False),flush=True)


def load_alpha(directory=None):
    with np.load((OUT if directory is None else directory)/'alpha_bank.npz',allow_pickle=False) as cache:
        return pd.DataFrame(cache['values'],index=pd.to_datetime(cache['minutes'],unit='ns',utc=True).tz_convert(IST),columns=cache['names'])


def repair_trial_schema(path):
    """Preserve the initial exploratory rows when adding explicit price metadata."""
    if not path.exists():return
    with path.open(newline='',encoding='utf-8') as stream:
        reader=csv.reader(stream);header=next(reader)
        if 'price_change' in header:return
        rows=list(reader)
    offset=header.index('rank_window')+1
    new_header=header[:offset]+['price_change']+header[offset:]
    repaired=[]
    for row in rows:
        if len(row)==len(header):row=row[:offset]+['legacy_close_close_h5']+row[offset:]
        if len(row)!=len(new_header):raise ValueError('Unexpected incomplete trial record; preserving original journal')
        repaired.append(row)
    backup=path.with_name('formula_trials_schema1.csv')
    if not backup.exists():backup.write_bytes(path.read_bytes())
    with path.open('w',newline='',encoding='utf-8') as stream:
        writer=csv.writer(stream);writer.writerow(new_header);writer.writerows(repaired)


def price_change_series(bars,recipe):
    h=recipe['horizon'];kind=recipe['kind']
    if kind=='close_close_old_open':return (bars.close-bars.close.shift(h))/bars.open.shift(h)
    if kind=='close_close_current_open':return (bars.close-bars.close.shift(h))/bars.open
    if kind=='body_h':return (bars.close-bars.open.shift(h-1))/bars.open.shift(h-1)
    if kind=='close_old_open':return (bars.close-bars.open.shift(h))/bars.open.shift(h)
    if kind=='open_open':return (bars.open-bars.open.shift(h))/bars.open.shift(h)
    if kind in ('current_open_provisional','current_open_from_open'):
        contiguous=pd.Series(bars.index,index=bars.index).shift(-1)-pd.Series(bars.index,index=bars.index)==pd.Timedelta(minutes=1)
        reference=bars.open if kind=='current_open_from_open' else bars.close
        return (bars.open.shift(-1).where(contiguous)-reference.shift(h-1))/bars.open.shift(h-1)
    raise ValueError(kind)


CONTRACT_VOLUME_KINDS=('contract_cumulative','contract_session_mean','native_over_session_mean')


def contract_session_mean(p,side):
    """Known volume of the selected fixed contract / completed session minutes."""
    minute=pd.DatetimeIndex(p.minute if 'minute' in p else p.index)
    count=pd.Series(minute.hour*60+minute.minute-555,index=p.index,dtype=float)
    regular=count.between(1,375)
    return p[f'{side}_contract_cumulative_volume']/count.where(regular)


def factor_contexts(bars,fixed=False,opening=False,cumulative=False):
    if opening:
        from backtest.provider_fixed_factors import OPENING_CACHE
        p=pd.read_csv(OPENING_CACHE)
    else:p=pd.read_csv(FEATURE_CACHE)
    p.minute=pd.to_datetime(p.minute,utc=True).dt.tz_convert(IST)
    p=p.sort_values(['expiry','minute']).reset_index(drop=True)
    if cumulative:
        from backtest.provider_fixed_factors import CUMULATIVE_CACHE
        extra=pd.read_csv(CUMULATIVE_CACHE)
        extra.minute=pd.to_datetime(extra.minute,utc=True).dt.tz_convert(IST)
        columns=['minute','expiry','atm_strike','ce_contract_cumulative_volume','pe_contract_cumulative_volume']
        p=p.merge(extra[columns],on=['minute','expiry','atm_strike'],how='left',validate='one_to_one')
    if fixed:
        from backtest.provider_fixed_factors import FIXED_CACHE
        extra=pd.read_csv(FIXED_CACHE)
        extra.minute=pd.to_datetime(extra.minute,utc=True).dt.tz_convert(IST)
        p=p.merge(extra.drop(columns='atm_strike'),on=['minute','expiry'],how='left',validate='one_to_one')
    mapping={d:expiries_for(d) for d in set(bars.index.date)}
    contexts={}
    for number,name in ((0,'near'),(1,'next')):
        take=np.array([e==str(mapping[m.date()][number]) for e,m in zip(p.expiry,p.minute)])
        continuous=p.loc[take].set_index('minute').reindex(bars.index)
        contexts['continuous_'+name]=(continuous,None)
        contexts['expiry_'+name]=(p,take)
    return contexts


def scan(limit=0,expanded=False,fine=False,contexts=None,mixed_price=False,fixed_contract=False,opening_atm=False,opening_volume=False,opening_pcr=False,contract_cumulative=False,bulk_shard=None):
    bulk=bulk_shard is not None
    if bulk:
        bulk_context,bulk_kind=bulk_shard_spec(bulk_shard)
        contexts=[bulk_context];opening_atm=True
        (OUT/'bulk_manifest.json').write_text(json.dumps(bulk_manifest(bulk_shard),indent=2))
    alpha_directory=OUTPUT/'replication_trials' if bulk else OUT
    if not (alpha_directory/'alpha_bank.npz').exists():
        if bulk:raise ValueError('Prepare the shared main alpha bank before bulk scanning')
        prepare_alpha()
    bars,_,_=context();bank=load_alpha(alpha_directory);scorer=Scorer(bars.index)
    table=pd.read_csv(alpha_directory/'alpha_trials.csv')
    # Choose on fit-period compatibility only. Retain documented and current-open
    # recipes explicitly, even if their standalone score is lower.
    finalists=[];hashes=set()
    import hashlib
    for name in table.alpha:
        digest=hashlib.sha256(bank[name].to_numpy().tobytes()).hexdigest()
        if digest not in hashes:
            finalists.append(name);hashes.add(digest)
        if len(finalists)==4:break
    extra_alphas=('current_open_from_open_h5_r800','current_open_from_open_h6_r800') if expanded else ()
    for key in ('close_close_old_open_h5_r800','body_h_h5_r800','current_open_provisional_h5_r800')+extra_alphas:
        if key not in finalists:finalists.append(key)
    if bulk:finalists=list(BULK_ALPHAS)
    alpha_recipes=json.loads((alpha_directory/'alpha_recipes.json').read_text())
    frontier=[];old=[];done=set();done_pairs=set()
    path=OUT/'formula_trials.csv'
    repair_trial_schema(path)
    if path.exists():
        old=pd.read_csv(path).to_dict('records');done={r['recipe_id'] for r in old}
        done_pairs={(r['recipe_id'],r['alpha']) for r in old}
    controls=[]
    if (OUT/'frontier.json').exists():
        saved=json.loads((OUT/'frontier.json').read_text())
        controls=[f for f in saved if f.get('control_for')]
        frontier=[f for f in saved if not f.get('control_for')]
    pending=[];tested=0
    for context_name,(p,take) in factor_contexts(bars,fixed_contract,opening_atm,contract_cumulative).items():
        if contexts and context_name not in contexts:continue
        if fine and context_name not in ('continuous_near','expiry_near'):continue
        expiry_groups=p.groupby('expiry',sort=False).groups if take is not None else None
        bulk_transforms=ExpiryFactorTransforms(p.index,expiry_groups) if bulk and expiry_groups is not None else None
        def grouped(s,fn):
            if expiry_groups is None:return fn(s)
            if bulk_transforms is not None:return bulk_transforms.transform(s,fn)
            out=pd.Series(np.nan,index=p.index)
            for ids in expiry_groups.values():out.loc[ids]=fn(s.loc[ids]).to_numpy()
            return out
        def align(s):
            if take is None:return s.reindex(bars.index)
            return pd.Series(s.loc[take].to_numpy(),index=pd.DatetimeIndex(p.loc[take,'minute'])).reindex(bars.index)
        means=RollingMeanCache(grouped)
        changes={}
        for alpha_name in finalists:
            change=price_change_series(bars,alpha_recipes[alpha_name])
            changes[alpha_name]=(pd.Series(change.reindex(pd.DatetimeIndex(p.minute)).to_numpy(),index=p.index)
                                 if take is not None else change)
        fixed_change=(bars.close-bars.close.shift(5))/bars.open.shift(5)
        if take is not None:fixed_change=pd.Series(fixed_change.reindex(pd.DatetimeIndex(p.minute)).to_numpy(),index=p.index)
        def shift(s,h):return grouped(s,lambda v:v.shift(h))
        volatility_lags=FactorLagCache(grouped) if bulk else None
        vols={}
        for kind in (('same_return','log_return') if bulk or contract_cumulative or opening_pcr or opening_volume else ('same_return','log_return','price_std','price_difference_std') if opening_atm else ('same_return','log_return','price_std') if fixed_contract else ('same_return','log_return') if fine else ('same_return','overnight_return','rolling_atm_return','log_return','price_std')):
            for w in ((20,60,150,300) if bulk else (300,) if contract_cumulative or opening_pcr else (250,300,350) if opening_volume else (20,60,250,300,350) if opening_atm else (300,) if fixed_contract else (250,300,350) if fine else (20,60,300)):
                factors=[]
                for side in ('ce','pe'):
                    s=p[f'{side}_return']
                    if kind=='overnight_return':s=p[f'{side}_return_with_overnight']
                    elif kind=='rolling_atm_return':s=grouped(p[f'{side}_ltp'],lambda v:v.pct_change(fill_method=None))
                    elif kind=='log_return':s=np.log1p(s)
                    elif kind=='price_std':s=p[f'{side}_ltp']
                    elif kind=='price_difference_std':s=p[f'{side}_ltp']*s/(1+s).where(1+s>0)
                    factors.append(grouped(s,lambda v:v.rolling(w,min_periods=int(np.ceil(.8*w))).std()))
                vols[f'{kind}_{w}']=factors[0]+factors[1]
                if fixed_contract:vols[f'fixed_{kind}_{w}']=p[f'fixed_{kind}_{w}']
        if not bulk and not fine and not fixed_contract:vols['iv_sum']=p.ce_iv+p.pe_iv
        kinds=('native',)+CONTRACT_VOLUME_KINDS if contract_cumulative else ('native',)+CROSS_VOLUME_KINDS if opening_pcr else ('native','geometric_ratios','harmonic_ratios','minimum_ratios','total_ratio') if opening_volume else ('native','fixed') if fixed_contract else ('native',) if fine else ('literal_reciprocal_put_call','previous_bar_ratio','raw_volume','total_ratio','put_call_ratio','reciprocal_put_call','geometric_ratios','minimum_ratios') if expanded else ('native','masked','cumulative')
        if bulk:kinds=(bulk_kind,)
        for volume_kind in kinds:
            input_kind=volume_kind if volume_kind in ('masked','cumulative','contract_cumulative','contract_session_mean') else 'native'
            volumes={side:p[f'{side}_native_volume' if volume_kind!='masked' else f'{side}_volume'] for side in ('ce','pe')}
            if volume_kind=='contract_cumulative':
                volumes={side:p[f'{side}_contract_cumulative_volume'] for side in ('ce','pe')}
            elif volume_kind=='contract_session_mean':
                volumes={side:contract_session_mean(p,side) for side in ('ce','pe')}
            if volume_kind=='cumulative':
                for side,v in volumes.items():
                    dates=p.minute.dt.date.to_numpy() if take is not None else p.index.date
                    grouping=[p.expiry,dates] if take is not None else dates
                    volumes[side]=v.groupby(grouping).cumsum()
            for short in (BULK_SHORTS if bulk else (1,5,15) if contract_cumulative or opening_pcr else (1,5) if fixed_contract or opening_atm else (1,) if fine else (1,5,15)):
                if volume_kind=='native_over_session_mean' and short!=1:continue
                if opening_pcr and volume_kind.startswith('mean_') and short==1:continue
                baselines=(20,60,300) if contract_cumulative else ((20,) if volume_kind.startswith(('literal_','mean_')) else (20,60,300)) if opening_pcr else ((300,) if short==5 else (15,20,25)) if opening_atm else (20,300) if fixed_contract else (20,) if volume_kind in ('literal_reciprocal_put_call','previous_bar_ratio','raw_volume') else (15,20,25) if fine else (20,60,300)
                if bulk:baselines=BULK_BASELINES
                if volume_kind=='native_over_session_mean':baselines=(20,)
                for baseline in baselines:
                    ratios=[]
                    for side,v in volumes.items():
                        numerator=means.mean(v,(input_kind,side),short,short)
                        denominator=(contract_session_mean(p,side) if volume_kind=='native_over_session_mean'
                            else means.mean(v,(input_kind,side),baseline,int(np.ceil(.8*baseline))))
                        ratios.append(numerator/denominator.where(denominator>0))
                    multiplier=(ratios[0]+ratios[1])/2
                    if volume_kind=='fixed':multiplier=p[f'fixed_volume_ratio_{short}_{baseline}']
                    if volume_kind=='total_ratio':
                        total=volumes['ce']+volumes['pe']
                        numerator=means.mean(total,(input_kind,'total'),short,short)
                        denominator=means.mean(total,(input_kind,'total'),baseline,int(np.ceil(.8*baseline)))
                        multiplier=numerator/denominator.where(denominator>0)
                    elif volume_kind in ('put_call_ratio','reciprocal_put_call'):
                        ce=means.mean(volumes['ce'],(input_kind,'ce'),short,short)
                        pe=means.mean(volumes['pe'],(input_kind,'pe'),short,short)
                        pcr=pe/ce.where(ce>0)
                        numerator=(pcr+1/pcr.where(pcr>0))/2 if volume_kind=='reciprocal_put_call' else pcr
                        denominator=grouped(numerator,lambda s:s.rolling(baseline,min_periods=int(np.ceil(.8*baseline))).mean())
                        multiplier=numerator/denominator.where(denominator>0)
                    elif volume_kind=='geometric_ratios':multiplier=np.sqrt(ratios[0]*ratios[1])
                    elif volume_kind=='harmonic_ratios':
                        denominator=ratios[0]+ratios[1]
                        multiplier=2*ratios[0]*ratios[1]/denominator.where(denominator>0)
                    elif volume_kind=='minimum_ratios':multiplier=np.minimum(ratios[0],ratios[1])
                    elif volume_kind in ('literal_reciprocal_put_call','previous_bar_ratio','raw_volume'):
                        ce=means.mean(volumes['ce'],(input_kind,'ce'),short,short)
                        pe=means.mean(volumes['pe'],(input_kind,'pe'),short,short)
                        if volume_kind=='literal_reciprocal_put_call':
                            multiplier=(ce/pe.where(pe>0)+pe/ce.where(ce>0))/2
                        elif volume_kind=='previous_bar_ratio':
                            old_ce=shift(ce,1);old_pe=shift(pe,1)
                            multiplier=(ce/old_ce.where(old_ce>0)+pe/old_pe.where(old_pe>0))/2
                        else:multiplier=(ce+pe)/2
                    if (opening_pcr or bulk) and volume_kind in CROSS_VOLUME_KINDS:
                        multiplier=cross_volume_multiplier(volumes['ce'],volumes['pe'],volume_kind,short,baseline,grouped)
                    multiplier_lags=FactorLagCache(grouped,max_entries=8) if bulk else None
                    for vol_name,vol in vols.items():
                        for lag in (BULK_LAGS if bulk else (0,5) if contract_cumulative or opening_pcr else (5,) if opening_volume else (0,1,2,3,4,5,6,7) if opening_atm else (0,5) if fixed_contract else (2,3,4,5,6,7) if fine else (0,1,5)):
                            recipe={'context':context_name,'volume_kind':volume_kind,'volume_short':short,
                                'volume_baseline':baseline,'volatility':vol_name,'factor_lag':lag,'rank_window':300,
                                'price_change':'close_close_h5_fixed_v3' if mixed_price else 'same_as_alpha_v2'}
                            if opening_atm:recipe['atm_reference']='last_completed_bar_open'
                            if bulk:recipe=bulk_recipe(context_name,volume_kind,short,baseline,vol_name,lag)
                            recipe_id=json.dumps(recipe,sort_keys=True,separators=(',',':'))
                            remaining=[a for a in finalists if (recipe_id,a) not in done_pairs]
                            if not remaining:continue
                            vr=(multiplier_lags.shift(multiplier,'multiplier',lag) if bulk else shift(multiplier,lag))
                            vv=(volatility_lags.shift(vol,vol_name,lag) if bulk else shift(vol,lag))
                            ranked_cache={}
                            for alpha_name in remaining:
                                ar=alpha_recipes[alpha_name];raw_key=('fixed_close_close',5) if mixed_price else (ar['kind'],ar['horizon'])
                                if raw_key not in ranked_cache:
                                    raw=(fixed_change if mixed_price else changes[alpha_name])*vr/vv.where(vv>0)
                                    ranked_cache[raw_key]=align(grouped(raw,lambda v:rank(v,300,.9)))
                                alpha2=ranked_cache[raw_key]
                                metrics,_=scorer.score(bank[alpha_name],alpha2)
                                record={'recipe_id':recipe_id,'alpha':alpha_name,**recipe,**metrics}
                                pending.append(record)
                                done_pairs.add((recipe_id,alpha_name))
                                objective=(metrics['fit_first_exact'],metrics['fit_direction_matches'],-metrics['fit_signal_episodes'])
                                if len(frontier)<12 or objective>=tuple(frontier[-1]['objective']):
                                    entry={'objective':list(objective),'alpha':alpha_name,'recipe':recipe,
                                        'alpha_recipe':alpha_recipes[alpha_name],'metrics':metrics}
                                    identity=f'{alpha_name}|{recipe_id}'
                                    candidate_id=hashlib.sha256(identity.encode()).hexdigest()[:16]
                                    entry['candidate_id']=candidate_id
                                    if not any(f['candidate_id']==candidate_id for f in frontier):
                                        frontier.append(entry);frontier.sort(key=lambda f:(tuple(-x for x in f['objective']),f['candidate_id']));frontier=frontier[:12]
                                        if any(f['candidate_id']==candidate_id for f in frontier):
                                            np.savez_compressed(OUT/f'candidate_{candidate_id}.npz',minutes=bars.index.as_unit('ns').asi8,
                                                alpha=bank[alpha_name].to_numpy(),alpha2=alpha2.to_numpy())
                            tested+=1;done.add(recipe_id)
                            if tested%25==0:
                                pd.DataFrame(pending).to_csv(path,index=False,mode='a' if path.exists() else 'w',header=not path.exists());pending=[]
                                (OUT/'frontier.json').write_text(json.dumps(frontier+controls,indent=2))
                                if bulk:prune_bulk_archives(OUT,frontier+controls)
                                print(f'Tested {tested} new formulas ({len(done)} total); frontier fit={frontier[0]["objective"]}; context={context_name}',flush=True)
                            if limit and tested>=limit:break
                        if limit and tested>=limit:break
                    if limit and tested>=limit:break
                if limit and tested>=limit:break
            if limit and tested>=limit:break
        if limit and tested>=limit:break
    if pending:pd.DataFrame(pending).to_csv(path,index=False,mode='a' if path.exists() else 'w',header=not path.exists())
    (OUT/'frontier.json').write_text(json.dumps(frontier+controls,indent=2))
    if bulk:prune_bulk_archives(OUT,frontier+controls)
    (OUT/'search_design.json').write_text(json.dumps({'selection':'fit first exact, then fit direction matches, then fewer fit signal episodes',
        'alpha_finalists':finalists,'tested_formula_recipes':len(done),'known_thresholds':[.8,.2],
        'matched_controls':{f['candidate_id']:f['control_for'] for f in controls},
        'atm_reference':'last completed index candle open' if opening_atm else 'last completed index candle close',
        'contract_cumulative_design':{'inputs':['native minute volume control','same-contract complete daily cumulative volume','same-contract average volume per completed session minute','native minute volume / same-contract current session average'],
            'short_windows':[1,5,15],'baselines':[20,60,300],'volatility_windows':[300],
            'volatility_types':['same_return','log_return'],'factor_lags':[0,5],
            'averaging':'Arithmetic average of CE and PE short-volume / own trailing mean.',
            'session_average':'Complete fixed-contract daily prefix / elapsed completed regular-session minutes; unknown prefixes stay unknown. This is a volume-unit conversion, not a fitted clock filter.',
            'native_over_session_mean':'Each current native minute volume / its same-contract daily prefix average; short=1 only. Baseline=20 is nominal unused here and defines the matched native trailing-mean control. No duplicated 60/300 recipes.',
            'missing':'Incomplete daily contract prefixes stay unknown. Rolling means use the existing 80% minimum; alpha2 rank uses 90%.',
            'causality':'Completed candle volumes only; no changing-ATM cumulative proxy, date fitting, sizing or exit changes.'} if contract_cumulative else None,
        'volume_aggregation_definitions':{'native':'arithmetic mean of per-leg volume ratios',
            'geometric_ratios':'sqrt(CE ratio * PE ratio)','harmonic_ratios':'2*CE ratio*PE ratio/(CE ratio+PE ratio); zero denominator fails closed',
            'minimum_ratios':'minimum of the two leg ratios; not the stated average',
            'total_ratio':'mean(CE+PE volume,short)/mean(CE+PE volume,baseline)'} if opening_volume else None,
        'opening_volume_design':'Native arithmetic averages are controls already covered by opening_atm. Other aggregations are explicit hypotheses. Volatility windows 250/300/350, factor lag five, original thresholds unchanged.' if opening_volume else None,
        'opening_pcr_design':{'definitions':{
            'native':'Arithmetic average of each leg short-volume / own trailing baseline mean.',
            'put_call_ratio':'(mean(PE,short)/mean(CE,short)) / its trailing baseline mean.',
            'call_put_ratio':'(mean(CE,short)/mean(PE,short)) / its trailing baseline mean.',
            'reciprocal_put_call':'Average of PE/CE and CE/PE after averaging each leg; divided by its trailing baseline mean.',
            'literal_put_call':'mean(PE,short)/mean(CE,short), without baseline normalization.',
            'literal_call_put':'mean(CE,short)/mean(PE,short), without baseline normalization.',
            'literal_reciprocal_put_call':'Arithmetic average of PE/CE and CE/PE after averaging each leg.',
            'mean_put_call':'Trailing mean of native minute PE/CE ratios.',
            'mean_reciprocal_put_call':'Trailing mean of the native minute reciprocal-pair average.'},
            'short_windows':[1,5,15],'normalized_baselines':[20,60,300],'volatility_windows':[300],
            'volatility_types':['same_return','log_return'],'factor_lags':[0,5],
            'duplicates':'Mean-of-ratio short=1 duplicates literal ratios, so omitted. Native formulas overlap existing banks and remain controls.',
            'causality':'Trailing opening-selected ATM volume; missing/zero denominators remain missing. Original alpha and 0.8/0.2 thresholds unchanged.'} if opening_pcr else None,
        'volatility_definitions':{'price_difference_std':'std(current option price * same-contract one-minute return / (1+return)); sum CE+PE',
            'price_std':'std(selected ATM option price); sum CE+PE','same_return':'std(same-contract one-minute simple return); sum CE+PE',
            'log_return':'std(log(1+same-contract one-minute return)); sum CE+PE'} if opening_atm else None,
        'warning':'Conditional first-signal scoring uses published position history; only autonomous replay tests complete strategy replication. Later dates were inspected earlier; chronological splits are not an untouched holdout.',
        'coverage':'All 210 entry timestamps present. No clock/date/P&L predictors. No future candle closes or volumes.'},indent=2))
    print('Saved trials/frontier',len(done),flush=True)
    if contract_cumulative:
        for kind in CONTRACT_VOLUME_KINDS:prepare_cumulative_comparison(kind)


def continuous_native_components(bars,p,recipe,alpha_recipe):
    """Causal components for the matched native-volume, continuous ATM trials."""
    if recipe['context']!='continuous_near' or recipe['volume_kind'] not in ('native','harmonic_ratios','geometric_ratios','minimum_ratios','total_ratio')+CONTRACT_VOLUME_KINDS+CROSS_VOLUME_KINDS:
        raise ValueError('Components require continuous-near native candle-volume inputs')
    ratios=[];vols=[];kind,window=recipe['volatility'].rsplit('_',1);window=int(window)
    lag=recipe['factor_lag'];frame=pd.DataFrame(index=bars.index)
    for side in ('ce','pe'):
        volume=p[f'{side}_contract_cumulative_volume' if recipe['volume_kind']=='contract_cumulative' else f'{side}_native_volume']
        if recipe['volume_kind']=='contract_session_mean':volume=contract_session_mean(p,side)
        frame[f'{side}_native_volume_lagged']=p[f'{side}_native_volume'].shift(lag)
        frame[f'{side}_input_volume_lagged']=volume.shift(lag)
        frame[f'{side}_smoothed_volume_lagged']=volume.rolling(recipe['volume_short'],min_periods=recipe['volume_short']).mean().shift(lag)
        denominator=volume.rolling(recipe['volume_baseline'],min_periods=int(np.ceil(.8*recipe['volume_baseline']))).mean()
        if recipe['volume_kind']=='native_over_session_mean':denominator=contract_session_mean(p,side)
        if recipe['volume_kind'] in CONTRACT_VOLUME_KINDS:frame[f'{side}_session_mean_volume_lagged']=contract_session_mean(p,side).shift(lag)
        ratio=volume.rolling(recipe['volume_short'],min_periods=recipe['volume_short']).mean()/denominator.where(denominator>0)
        ratios.append(ratio);frame[f'{side}_volume_ratio_lagged']=ratio.shift(lag)
        values=p[f'{side}_return']
        if kind=='log_return':values=np.log1p(values)
        elif kind=='price_std':values=p[f'{side}_ltp']
        elif kind=='price_difference_std':values=p[f'{side}_ltp']*values/(1+values).where(1+values>0)
        elif kind!='same_return':raise ValueError('Unsupported component volatility')
        vol=values.rolling(window,min_periods=int(np.ceil(.8*window))).std()
        vols.append(vol);frame[f'{side}_volatility_lagged']=vol.shift(lag)
    multiplier=(ratios[0]+ratios[1])/2
    if recipe['volume_kind']=='harmonic_ratios':
        denominator=ratios[0]+ratios[1]
        multiplier=2*ratios[0]*ratios[1]/denominator.where(denominator>0)
    elif recipe['volume_kind']=='geometric_ratios':multiplier=np.sqrt(ratios[0]*ratios[1])
    elif recipe['volume_kind']=='minimum_ratios':multiplier=np.minimum(ratios[0],ratios[1])
    elif recipe['volume_kind']=='total_ratio':
        total=p.ce_native_volume+p.pe_native_volume
        denominator=total.rolling(recipe['volume_baseline'],min_periods=int(np.ceil(.8*recipe['volume_baseline']))).mean()
        multiplier=total.rolling(recipe['volume_short'],min_periods=recipe['volume_short']).mean()/denominator.where(denominator>0)
    elif recipe['volume_kind'] in CROSS_VOLUME_KINDS:
        multiplier=cross_volume_multiplier(p.ce_native_volume,p.pe_native_volume,recipe['volume_kind'],recipe['volume_short'],recipe['volume_baseline'])
    frame['volume_ratio_lagged']=multiplier.shift(lag)
    frame['atm_volatility_lagged']=(vols[0]+vols[1]).shift(lag)
    frame['price_change']=price_change_series(bars,alpha_recipe)
    frame['raw2']=frame.price_change*frame.volume_ratio_lagged/frame.atm_volatility_lagged.where(lambda s:s>0)
    frame['alpha2']=rank(frame.raw2,recipe['rank_window'],.9)
    return frame


def exponential_sample_std(values, window=150, minimum=120):
    """Finite-slot exponentially weighted sample STD; gaps retain their ages.

    Matches the uniform rolling STD's availability policy: a missing current
    return may be omitted when enough historical returns remain. No quote or
    volume is filled. Reliability-weight sample correction is W - sum(w²)/W.
    Centering and scaling avoid cancellation and overflow in squared returns.
    """
    if window < 2 or not 2 <= minimum <= window:
        raise ValueError('Weighted STD requires 2 <= minimum <= window')
    clean=pd.to_numeric(values,errors='coerce').astype(float)
    clean=clean.where(np.isfinite(clean))
    decay=(window-1)/(window+1)
    weights=decay**np.arange(window-1,-1,-1,dtype=float)
    def estimate(sample):
        finite=np.isfinite(sample)
        if finite.sum()<minimum:return np.nan
        x=sample[finite];w=weights[-len(sample):][finite]
        scale=np.max(np.abs(x))
        if scale==0:return 0.
        x=x/scale;total=w.sum();correction=total-np.dot(w,w)/total
        mean=np.dot(w,x)/total
        result=np.sqrt(np.dot(w,(x-mean)**2)/correction)*scale
        return float(result) if np.isfinite(result) else np.nan
    return clean.rolling(window,min_periods=minimum).apply(estimate,raw=True)


def weighted_volatility_components(bars,p,recipe,alpha_recipe):
    """Matched continuous-near experiment changing only STD150 weighting."""
    expected={'context':'continuous_near','volume_kind':'geometric_ratios','volume_short':1,
        'volume_baseline':10,'volatility':'log_return_150','factor_lag':5,'rank_window':300,
        'atm_reference':'last_completed_bar_open','profit_target_mode':'disabled'}
    if any(recipe.get(key)!=value for key,value in expected.items()):
        raise ValueError('Weighted experiment requires the exact saved reference recipe')
    frame=continuous_native_components(bars,p,recipe,alpha_recipe).copy()
    vols=[]
    for side in ('ce','pe'):
        with np.errstate(divide='ignore',invalid='ignore'):
            values=np.log1p(p[f'{side}_return'])
        vol=exponential_sample_std(values).shift(5)
        frame[f'{side}_volatility_lagged']=vol;vols.append(vol)
    frame['atm_volatility_lagged']=vols[0]+vols[1]
    frame['raw2']=frame.price_change*frame.volume_ratio_lagged/frame.atm_volatility_lagged.where(lambda s:s>0)
    frame['alpha2']=rank(frame.raw2,300,.9)
    return frame


def volatility_definition_panel(panel,window):
    """Explicit trailing volatility definitions; no future rows or filling."""
    if not isinstance(window,int) or window<2:raise ValueError('Invalid volatility window')
    minimum=int(np.ceil(.8*window));logs=[];prices=[]
    for side in ('ce','pe'):
        returns=panel[f'{side}_return']
        logs.append(np.log1p(returns.where(np.isfinite(returns)&returns.gt(-1))))
        price=panel[f'{side}_ltp'];prices.append(price.where(np.isfinite(price)&price.gt(0)))
    std=[s.rolling(window,min_periods=minimum).std(ddof=1) for s in logs]
    variance=[s.rolling(window,min_periods=minimum).var(ddof=1) for s in logs]
    rms=[np.sqrt(s.pow(2).rolling(window,min_periods=minimum).mean()) for s in logs]
    absolute=[s.abs().rolling(window,min_periods=minimum).mean() for s in logs]
    level_std=[p.rolling(window,min_periods=minimum).std(ddof=1) for p in prices]
    level_mean=[p.rolling(window,min_periods=minimum).mean() for p in prices]
    log_std=[np.log(p).rolling(window,min_periods=minimum).std(ddof=1) for p in prices]
    return {'return_std_sum':std[0]+std[1],
        'return_variance_sum':variance[0]+variance[1],
        'root_sum_return_variances':np.sqrt(variance[0]+variance[1]),
        'return_rms_sum':rms[0]+rms[1],
        'return_mean_abs_sum':absolute[0]+absolute[1],
        'price_std_sum':level_std[0]+level_std[1],
        'price_cv_sum':level_std[0]/level_mean[0]+level_std[1]/level_mean[1],
        'log_price_std_sum':log_std[0]+log_std[1]}


def volatility_definition_screen(weighted_alpha=False):
    """Matched finite volatility conventions on opening ATM inputs."""
    from backtest.provider_price_bounds import calendar_support_rank
    root=OUTPUT/'replication_trials';reference_id='95fefedfcf057448'
    seed=json.loads((root/'bulk'/f'full_autonomous_{reference_id}_ledger'/'report.json').read_text())['candidate']
    bars,_,_=context();panel=factor_contexts(bars,opening=True)['continuous_near'][0]
    parts=continuous_native_components(bars,panel,seed['recipe'],seed['alpha_recipe'])
    original_alpha=load_alpha(root)[seed['alpha']]
    if weighted_alpha:
        from backtest.provider_price_bounds import weighted_observation_rank
        alphas={'exponential_half_life800':weighted_observation_rank(parts.price_change,800,'exponential',800,800)}
        with np.load(root/'weighted_rank_pairs'/'candidate_5346fa75f4d90520.npz') as stored:
            np.testing.assert_array_equal(alphas['exponential_half_life800'].to_numpy(),stored['alpha'])
            np.testing.assert_array_equal(parts.alpha2.to_numpy(),stored['alpha2'])
    else:
        alphas={'trading_observations':original_alpha,
            'calendar_closed_zero_full':calendar_support_rank(parts.price_change,800,True)}
    multipliers={5:parts.volume_ratio_lagged}
    # Lag0 is rebuilt from unshifted factors, never recovered using future data.
    ratios=[panel[f'{side}_native_volume'].rolling(1,min_periods=1).mean()/
        panel[f'{side}_native_volume'].rolling(10,min_periods=8).mean().where(lambda v:v>0) for side in ('ce','pe')]
    multipliers[0]=np.sqrt(ratios[0]*ratios[1])
    minutes=bars.index.as_unit('ns').asi8
    with np.load(root/'bulk'/f'candidate_{reference_id}.npz',allow_pickle=False) as control:
        for key,actual in (('minutes',minutes),('alpha',original_alpha.to_numpy()),('alpha2',parts.alpha2.to_numpy())):
            if not np.array_equal(actual,control[key],equal_nan=True):raise ValueError(f'Reference differs: {key}')
    scorer=Scorer(bars.index);directory=root/('weighted_alpha_volatility_definitions' if weighted_alpha else 'volatility_definitions');directory.mkdir(exist_ok=True)
    records=[];frontier=[];retained={};control_id=None
    for window in (150,300):
        for kind,scale in volatility_definition_panel(panel,window).items():
            for lag in (0,5):
                raw=parts.price_change*multipliers[lag]/scale.shift(lag).where(lambda v:v>0)
                beta=rank(raw,300,.9)
                for support,alpha in alphas.items():
                    recipe={**seed['recipe'],'volatility_definition':kind,'volatility_definition_window':window,
                        'factor_lag':lag,'alpha_rank_support':support,'matched_reference_candidate':reference_id}
                    cid=hashlib.sha256(json.dumps({'alpha':seed['alpha'],'recipe':recipe},sort_keys=True).encode()).hexdigest()[:16]
                    metrics,_=scorer.score(alpha,beta)
                    candidate={'candidate_id':cid,'alpha':seed['alpha'],'alpha_recipe':seed['alpha_recipe'],
                        'recipe':recipe,'metrics':metrics,
                        'objective':[metrics['fit_first_exact'],metrics['fit_direction_matches'],-metrics['fit_signal_episodes']]}
                    records.append({'candidate_id':cid,'definition':kind,'window':window,'factor_lag':lag,'alpha_support':support,**metrics})
                    frontier.append(candidate)
                    # Bound retained rank arrays rather than saving every trial file.
                    retained[cid]=(alpha.to_numpy(),beta.to_numpy())
                    frontier.sort(key=lambda c:(tuple(c['objective']),c['candidate_id']),reverse=True)
                    keep={c['candidate_id'] for c in frontier[:8]}
                    if kind=='return_std_sum' and window==150 and lag==5 and support in ('trading_observations','exponential_half_life800'):
                        control_id=cid
                        np.testing.assert_array_equal(beta.to_numpy(),parts.alpha2.to_numpy())
                    if control_id:keep.add(control_id)
                    retained={k:v for k,v in retained.items() if k in keep}
    selected=frontier[:8]
    if control_id not in {c['candidate_id'] for c in selected}:selected.append(next(c for c in frontier if c['candidate_id']==control_id))
    for cid,(alpha,beta) in retained.items():
        np.savez_compressed(directory/f'candidate_{cid}.npz',minutes=minutes,alpha=alpha,alpha2=beta)
    (directory/'frontier.json').write_text(json.dumps(selected,indent=2))
    pd.DataFrame(records).to_csv(directory/'screen.csv',index=False)
    (directory/'search_design.json').write_text(json.dumps({'pairs':len(records),'control_candidate':control_id,
        'reference_candidate':reference_id,'volatility_windows':[150,300],'factor_lags':[0,5],
        'minimum_volatility_observations':'ceil(80% of window)',
        'fixed':'Geometric volume1/10, near opening ATM, five-bar underlying return, alpha2 rank300/min270, strict .8/.2, no-target execution.',
        'selection':'Eight conditional fit leaders and exact control; autonomous fit replay required. No later-period selection.',
        'price_levels':'Price-based definitions use the selected ATM price path, including strike changes; return-based definitions use same-contract one-minute returns.',
        'alpha_kernel':'Exponential observation-age rank800, half-life800, min800' if weighted_alpha else 'Original observed/calendar controls',
        'matched_weighted_control':'5346fa75f4d90520' if weighted_alpha else None,
        'production_change':False},indent=2))
    print(json.dumps({'tested':len(records),'selected':selected[0],'control':control_id},indent=2),flush=True)
    return selected


def weighted_volatility_screen():
    """Two offline, matched candidates; the uniform control must roundtrip exactly."""
    root=OUTPUT/'replication_trials';reference_id='95fefedfcf057448'
    report_path=root/'bulk'/f'full_autonomous_{reference_id}_ledger'/'report.json'
    stored_path=root/'bulk'/f'candidate_{reference_id}.npz'
    seed=json.loads(report_path.read_text())['candidate']
    bars,_,_=context();bank=load_alpha(root)
    panel=factor_contexts(bars,opening=True)['continuous_near'][0]
    uniform=continuous_native_components(bars,panel,seed['recipe'],seed['alpha_recipe'])
    alpha=bank[seed['alpha']].to_numpy();minutes=bars.index.as_unit('ns').asi8
    with np.load(stored_path,allow_pickle=False) as stored:
        for key,actual in (('minutes',minutes),('alpha',alpha),('alpha2',uniform.alpha2.to_numpy())):
            expected=stored[key]
            if actual.dtype!=expected.dtype or not np.array_equal(actual,expected,equal_nan=True):
                raise ValueError(f'Unexplained reference control mismatch: {key}; no candidates saved')
    weighted=weighted_volatility_components(bars,panel,seed['recipe'],seed['alpha_recipe'])
    scorer=Scorer(bars.index);directory=root/'weighted_volatility';directory.mkdir(exist_ok=True)
    frontier=[];records=[];source=[]
    for role,components in (('weighted',weighted),('uniform_control',uniform)):
        recipe={**seed['recipe'],'volatility_weighting':role,
            'weighted_decay':149/151 if role=='weighted' else None,
            'matched_reference_candidate':reference_id}
        rid=json.dumps(recipe,sort_keys=True,separators=(',',':'))
        cid=hashlib.sha256(f'{seed["alpha"]}|{rid}'.encode()).hexdigest()[:16]
        metrics,_=scorer.score(alpha,components.alpha2)
        candidate={'candidate_id':cid,'alpha':seed['alpha'],'alpha_recipe':seed['alpha_recipe'],
            'recipe':recipe,'metrics':metrics,'objective':[metrics['fit_first_exact'],metrics['fit_direction_matches'],-metrics['fit_signal_episodes']],
            'reference_candidate_id':reference_id,'matched_role':role,
            'selection_note':'Explicit matched experiment; weighted first, uniform control second, not score sorted.'}
        frontier.append(candidate);records.append({'recipe_id':rid,'alpha':seed['alpha'],**recipe,**metrics})
        np.savez_compressed(directory/f'candidate_{cid}.npz',minutes=minutes,alpha=alpha,alpha2=components.alpha2.to_numpy())
    for position,trade in zip(scorer.entries,scorer.trades.itertuples()):
        row={'signal_id':trade.signal_id,'entry':trade.entry,'option_type':trade.option_type,'alpha':alpha[position]}
        for role,components in (('weighted',weighted),('uniform',uniform)):
            for column in ('ce_volatility_lagged','pe_volatility_lagged','atm_volatility_lagged','volume_ratio_lagged','price_change','raw2','alpha2'):
                row[f'{role}_{column}']=components[column].iloc[position]
            beta=components.alpha2.iloc[position]
            row[f'{role}_both_direction_pass']=bool((alpha[position]>.8 and beta>.8) if trade.direction==1 else (alpha[position]<.2 and beta<.2))
        source.append(row)
    pd.DataFrame(records).to_csv(directory/'formula_trials.csv',index=False)
    pd.DataFrame(source).to_csv(directory/'source_entry_diagnostics.csv',index=False)
    (directory/'frontier.json').write_text(json.dumps(frontier,indent=2))
    (directory/'search_design.json').write_text(json.dumps({'family':'weighted_volatility','pairs':2,
        'reference_candidate_id':reference_id,'reference_report':str(report_path),'reference_archive':str(stored_path),
        'reference_array_check':'Exact float64 alpha/alpha2 equality including NaNs; exact int64 clock.',
        'weighted_formula':'150 clock slots; w(age)=(149/151)^age; sample variance sum(w*(x-mean)^2)/(W-sum(w²)/W); CE+PE log-return STD; lag5.',
        'minimum_valid_returns':120,'missing_policy':'Uniform control availability preserved: current missing return may be omitted, gaps retain ages. Missing volume/quotes remain governed by original inputs; no fill.',
        'unchanged':'Opening-selected continuous-near path, geometric volume1/b10, original alpha800 and beta300/min270, strict thresholds, target disabled, execution unchanged.',
        'history_policy':'Same-contract returns sampled on selected ATM path; not own-contract rolling histories.',
        'selection':'Weighted first and uniform control second by design; conditional fit scores are not autonomous replication.',
        'archive_policy':'Exactly two candidate archives; offline preparation only.'},indent=2))
    print(json.dumps({'pairs':2,'reference_arrays_exact':True,'frontier':[(c['candidate_id'],c['objective']) for c in frontier]},indent=2),flush=True)


def prepare_cumulative_comparison(volume_kind='contract_cumulative'):
    """Retain the fit leader of the actual cumulative-input hypothesis explicitly.

    Native controls may dominate the global frontier. Selecting one continuous
    cumulative recipe independently permits a matched autonomous comparison,
    without relabeling it as the global best recipe or using later scores.
    """
    table=pd.read_csv(OUT/'formula_trials.csv')
    rows=table.loc[table.volume_kind.eq(volume_kind)&table.context.eq('continuous_near')]
    if rows.empty:return
    row=rows.sort_values(['fit_first_exact','fit_direction_matches','fit_signal_episodes'],ascending=[False,False,True],kind='stable').iloc[0]
    recipe=json.loads(row.recipe_id);alpha_recipe=json.loads((OUT/'alpha_recipes.json').read_text())[row.alpha]
    cid=hashlib.sha256(f'{row.alpha}|{row.recipe_id}'.encode()).hexdigest()[:16]
    bars,_,_=context();bank=load_alpha();p=factor_contexts(bars,opening=True,cumulative=True)['continuous_near'][0]
    components=continuous_native_components(bars,p,recipe,alpha_recipe)
    metrics,_=Scorer(bars.index).score(bank[row.alpha],components.alpha2)
    for key,value in metrics.items():
        if not np.isclose(value,row[key],equal_nan=True):raise ValueError(f'Cumulative component mismatch: {key}')
    np.savez_compressed(OUT/f'candidate_{cid}.npz',minutes=bars.index.as_unit('ns').asi8,
        alpha=bank[row.alpha].to_numpy(),alpha2=components.alpha2.to_numpy())
    frontier=json.loads((OUT/'frontier.json').read_text())
    if not any(f['candidate_id']==cid for f in frontier):
        frontier.append({'candidate_id':cid,'alpha':row.alpha,'alpha_recipe':alpha_recipe,'recipe':recipe,
            'metrics':metrics,'objective':[metrics['fit_first_exact'],metrics['fit_direction_matches'],-metrics['fit_signal_episodes']],
            'selection_note':'Continuous-near cumulative-input fit leader; native controls may have stronger scores.'})
        (OUT/'frontier.json').write_text(json.dumps(frontier,indent=2))
    design_path=OUT/'search_design.json';design=json.loads(design_path.read_text())
    if volume_kind=='contract_cumulative':design['fit_selected_continuous_cumulative_leader']=cid
    design['fit_selected_contract_volume_leaders']={**design.get('fit_selected_contract_volume_leaders',{}),volume_kind:cid}
    design_path.write_text(json.dumps(design,indent=2))
    control_id=prepare_atm_control(cid,'contract_cumulative',True)
    design=json.loads(design_path.read_text())
    design['contract_volume_control_links']={**design.get('contract_volume_control_links',{}),cid:control_id}
    design_path.write_text(json.dumps(design,indent=2))
    print('Cumulative-input fit leader:',cid,recipe,flush=True)


def prepare_atm_control(candidate_id,family='opening_atm',volume_control=False):
    """Matched close-selected ATM control for an opening-panel formula.

    This control is retained after the fit frontier and excluded from selection.
    Only the option input panel changes; alpha, ranks and execution stay fixed.
    """
    target=OUTPUT/'replication_trials'/family
    frontier=json.loads((target/'frontier.json').read_text())
    seed=next(f for f in frontier if f['candidate_id']==candidate_id)
    r=seed['recipe']
    if r.get('atm_reference')!='last_completed_bar_open' or r['context']!='continuous_near':
        raise ValueError('Matched control requires a continuous-near opening candidate')
    if volume_control and r['volume_kind']=='native':raise ValueError('Candidate already uses arithmetic volume')
    recipe={**r,'volume_kind':'native'} if volume_control else {**r,'atm_reference':'last_completed_bar_close'}
    rid=json.dumps(recipe,sort_keys=True,separators=(',',':'))
    cid=hashlib.sha256(f'{seed["alpha"]}|{rid}'.encode()).hexdigest()[:16]
    existing=next((f for f in frontier if f['candidate_id']==cid),None)
    if existing is not None:
        print('Existing matched ATM control:',cid,flush=True);return cid
    bars,_,_=context();p=factor_contexts(bars,opening=volume_control)['continuous_near'][0]
    b=continuous_native_components(bars,p,recipe,seed['alpha_recipe']).alpha2
    with np.load(target/f'candidate_{candidate_id}.npz',allow_pickle=False) as stored:
        minute=stored['minutes'];a=stored['alpha'].astype(float)
    if not np.array_equal(minute,bars.index.as_unit('ns').asi8):raise ValueError('Unaligned control input minutes')
    metrics,_=Scorer(bars.index).score(a,b,r.get('threshold_comparison','strict'))
    candidate={'candidate_id':cid,'alpha':seed['alpha'],'alpha_recipe':seed['alpha_recipe'],
        'recipe':recipe,'metrics':metrics,
        'objective':[metrics['fit_first_exact'],metrics['fit_direction_matches'],-metrics['fit_signal_episodes']],
        'control_for':candidate_id,'control_type':('volume_input' if r['volume_kind'] in CONTRACT_VOLUME_KINDS else 'volume_aggregation') if volume_control else 'atm_reference',
        'selection_note':'Matched formula control, excluded from fit candidate selection.'}
    np.savez_compressed(target/f'candidate_{cid}.npz',minutes=minute,alpha=a,alpha2=b.to_numpy())
    frontier.append(candidate);(target/'frontier.json').write_text(json.dumps(frontier,indent=2))
    path=target/'formula_trials.csv'
    row={'recipe_id':rid,'alpha':seed['alpha'],**recipe,**metrics}
    table=pd.read_csv(path)
    existing=table.loc[table.recipe_id.eq(rid)&table.alpha.eq(seed['alpha'])]
    if existing.empty:
        pd.concat([table,pd.DataFrame([row])],ignore_index=True).to_csv(path,index=False)
    else:
        for key,value in metrics.items():
            if not existing[key].eq(value).all():raise ValueError('Matched control disagrees with existing formula scores')
    design_path=target/'search_design.json';design=json.loads(design_path.read_text())
    design['matched_controls']={**design.get('matched_controls',{}),cid:candidate_id}
    design_path.write_text(json.dumps(design,indent=2))
    print('Saved matched volume control:' if volume_control else 'Saved matched ATM control:',cid,'for',candidate_id,'fit',candidate['objective'],flush=True)
    return cid


def premium_screen():
    """Finite premium-eligibility screen; choose recipes using fit scores only."""
    root=OUTPUT/'replication_trials';target=root/'eligibility';target.mkdir(exist_ok=True)
    seed_specs=[('main',None),('fine',None),('expanded',None),('boundaries',None),
        ('boundaries','0868ced4b10c99d7')]
    normal_grid=(0,20,30,40,50);expiry_grid=(0,10,18,20,30)
    seeds=[]
    for family,cid in seed_specs:
        source=root if family=='main' else root/family
        saved=json.loads((source/'frontier.json').read_text())
        seed=saved[0] if cid is None else next(f for f in saved if f['candidate_id']==cid)
        seeds.append((family,source,seed))
    design={'normal_day_min_grid':normal_grid,'expiry_day_min_grid':expiry_grid,'maximum':200,
        'seed_candidates':[{'family':family,'candidate_id':seed['candidate_id']} for family,_,seed in seeds],
        'selection':'Fit first exact, then fit direction matches, then fewer fit signal episodes. No later-period selection.',
        'source':'Provider metadata lists PREMIUM eligibility, but gives no cutoff or min/max definition. These are hypotheses.',
        'quotes':'Last completed index candle open chooses short ATM; completed option close at decision minute, same selected expiry.',
        'limitations':['Eligibility thresholds are not documented strategy rules. Source fill minima motivated the finite grid; historical LTP can differ from fills.',
            'Scoring assumes ledger opening-reference ATM; autonomous replay uses each execution style actual selected short premium.',
            'Previously inspected later periods are not untouched holdouts. Source-conditioned scores require autonomous confirmation.',
            'No reserve margin, position sizing, exit or production configuration changes.']}
    (target/'eligibility_design.json').write_text(json.dumps(design,indent=2))
    quotes=pd.read_csv(ENTRY_QUOTE_CACHE)
    quotes.index=pd.to_datetime(quotes.pop('minute'),utc=True).dt.tz_convert(IST)
    source=provider_trades();selected=quotes.reindex(source.entry_minute)
    prices=selected.pe_ltp.where(source.direction.to_numpy()==1,selected.ce_ltp).to_numpy()
    pd.DataFrame({'signal_id':source.signal_id,'entry':source.entry,'side':source.option_type,
        'source_short_strike':source.short_strike,'selected_short_strike':selected.strike.to_numpy(),
        'source_short_fill':source.short_entry,'selected_short_ltp':prices,
        'source_expiry':source.expiry,'selected_expiry':selected.expiry.to_numpy(),
        'expiry_day':source.entry.dt.date==source.expiry}).to_csv(target/'source_premium_comparison.csv',index=False)
    rows=[];candidates=[];inputs={};scorers={};cases=[]
    for family,source,seed in seeds:
        with np.load(source/f'candidate_{seed["candidate_id"]}.npz',allow_pickle=False) as data:
            minute=data['minutes'];a=data['alpha'].astype(float);b=data['alpha2'].astype(float)
        for cutoff in (.2,.8):
            a[np.isclose(a,cutoff,atol=1e-7,rtol=0)]=cutoff
            b[np.isclose(b,cutoff,atol=1e-7,rtol=0)]=cutoff
        inputs[(family,seed['candidate_id'])]=(minute,a,b)
        idx=pd.to_datetime(minute,unit='ns',utc=True).tz_convert(IST)
        key=hashlib.sha256(minute.tobytes()).hexdigest()
        if key not in scorers:scorers[key]=Scorer(idx)
        for normal in normal_grid:
            for expiry in expiry_grid:
                recipe={**seed['recipe'],'premium_gate':{'normal_day_min':normal,'expiry_day_min':expiry,'maximum':200},
                    'eligibility_seed_family':family,'eligibility_seed_candidate_id':seed['candidate_id']}
                rid=json.dumps(recipe,sort_keys=True,separators=(',',':'))
                cid=hashlib.sha256(f'{seed["alpha"]}|{rid}'.encode()).hexdigest()[:16]
                allowed=premium_eligibility(idx,{'recipe':recipe},quotes)
                metrics,_=scorers[key].score(a,b,recipe.get('threshold_comparison','strict'),allowed)
                rows.append({'recipe_id':rid,'alpha':seed['alpha'],**recipe,**metrics})
                objective=(metrics['fit_first_exact'],metrics['fit_direction_matches'],-metrics['fit_signal_episodes'])
                candidate={'candidate_id':cid,'alpha':seed['alpha'],'alpha_recipe':seed['alpha_recipe'],
                    'recipe':recipe,'metrics':metrics,'objective':list(objective)}
                candidates.append(candidate)
                if seed['candidate_id']=='0868ced4b10c99d7' and (normal,expiry) in ((0,0),(40,20)):
                    cases.append(candidate)
        print(f'Premium eligibility seed {family}/{seed["candidate_id"]}: {len(rows)} paired trials',flush=True)
    candidates.sort(key=lambda f:tuple(f['objective']),reverse=True)
    frontier=candidates[:12]
    frontier += [f for f in cases if not any(v['candidate_id']==f['candidate_id'] for v in frontier)]
    for f in frontier:
        minute,a,b=inputs[(f['recipe']['eligibility_seed_family'],f['recipe']['eligibility_seed_candidate_id'])]
        np.savez_compressed(target/f'candidate_{f["candidate_id"]}.npz',minutes=minute,alpha=a,alpha2=b)
    pd.DataFrame(rows).to_csv(target/'formula_trials.csv',index=False)
    (target/'frontier.json').write_text(json.dumps(frontier,indent=2))
    design.update({'paired_trials':len(rows),'fit_selected_leader':frontier[0]['candidate_id'],
        'case_candidates':[f['candidate_id'] for f in cases]})
    (target/'eligibility_design.json').write_text(json.dumps(design,indent=2))
    print('Premium eligibility fit frontier:',frontier[0]['objective'],frontier[0]['recipe']['premium_gate'],flush=True)


def entry_episode_audit(seeds,target):
    """Detect repeated entries within rank episodes in existing independent runs.

    Counts describe existing paths, not the altered state of a new strategy.
    Zero rejected proposals proves an episode gate would leave that path intact.
    """
    root=OUTPUT/'replication_trials';source=provider_trades();rows=[];details=[]
    source_keys={(t.entry_minute,t.option_type,t.short_strike,t.hedge_strike,str(t.expiry)) for t in source.itertuples()}
    for family,cid in seeds:
        directory=root if family=='main' else root/family
        run_dir=directory/f'full_autonomous_{cid}_ledger'
        if not (run_dir/'report.json').exists() or not json.loads((run_dir/'report.json').read_text())['result']['complete_history']:
            raise ValueError('Episode audit requires complete independent seed replay')
        seed=next(f for f in json.loads((directory/'frontier.json').read_text()) if f['candidate_id']==cid)
        cfg=threshold_config(StrategyConfig(),seed['recipe'].get('threshold_comparison','strict'))
        with np.load(directory/f'candidate_{cid}.npz',allow_pickle=False) as data:
            idx=pd.to_datetime(data['minutes'],unit='ns',utc=True).tz_convert(IST);a=data['alpha'];b=data['alpha2']
        sim=pd.read_csv(run_dir/'trades.csv');sim.entry_ts=pd.to_datetime(sim.entry_ts,utc=True).dt.tz_convert(IST)
        sim=sim.sort_values('entry_ts').reset_index(drop=True)
        matched=np.array([(t.entry_ts,t.option_type,t.sell_strike,t.buy_strike,str(t.expiry)) in source_keys for t in sim.itertuples()])
        both=np.where((a>cfg.bullish_threshold)&(b>cfg.bullish_threshold),1,
            np.where((a<cfg.bearish_threshold)&(b<cfg.bearish_threshold),-1,0))
        si=idx.get_indexer(source.entry_minute);ri=idx.get_indexer(sim.entry_ts)
        if (si<0).any() or (ri<0).any():raise ValueError('Missing entry episode observation')
        valid=both[si]==source.direction.to_numpy()
        for mode in ('joint','alpha','alpha2'):
            x=a if mode=='alpha' else b
            state=both if mode=='joint' else np.where(x>cfg.bullish_threshold,1,np.where(x<cfg.bearish_threshold,-1,0))
            episode=np.cumsum(np.r_[True,state[1:]!=state[:-1]])
            if (state[ri]==0).any():raise ValueError('Existing replay entry lacks its rank condition')
            repeated=pd.Series(episode[ri]).duplicated().to_numpy()
            published_repeat=np.zeros(len(source),dtype=bool)
            published_repeat[valid]=pd.Series(episode[si[valid]]).duplicated().to_numpy()
            rows.append({'seed_family':family,'seed_candidate_id':cid,'episode_basis':mode,
                'published_entries':len(source),'published_entry_conditions_pass':int(valid.sum()),
                'published_repeated_compatible_episodes':int(published_repeat.sum()),
                'simulated_entries':len(sim),'simulated_repeated_episodes':int(repeated.sum()),
                'matching_repeated_entries':int((repeated&matched).sum()),'extra_repeated_entries':int((repeated&~matched).sum())})
            for kind,minutes,ids,passes,duplicates,matches in (
                ('published',source.entry_minute,si,valid,published_repeat,np.ones(len(source),dtype=bool)),
                ('simulated',sim.entry_ts,ri,np.ones(len(sim),dtype=bool),repeated,matched)):
                details.extend({'seed_family':family,'seed_candidate_id':cid,'episode_basis':mode,
                    'entry_kind':kind,'minute':minute,'entry_conditions_pass':bool(passed),
                    'episode_id':int(episode[k]) if passed else None,'episode_direction':int(state[k]) if passed else None,
                    'repeated_episode':bool(duplicate),'published_entry_match':bool(match)}
                    for minute,k,passed,duplicate,match in zip(minutes,ids,passes,duplicates,matches))
    pd.DataFrame(rows).to_csv(target/'entry_episode_summary.csv',index=False)
    pd.DataFrame(details).to_csv(target/'entry_episode_every_entry.csv',index=False)
    (target/'entry_episode_design.json').write_text(json.dumps({
        'episode':'Maximal continuous run of the same directional threshold condition over completed trading observations. Clock, session and flat-position transitions do not reset it.',
        'conditions':'Joint alpha/alpha2, alpha alone or alpha2 alone; original threshold-comparison convention retained.',
        'scope':'Existing independently replayed entry paths. Published repeat counts use entries whose original paired conditions pass. Source labels only identify matches.',
        'interpretation':'If an episode gate rejects zero entries in an existing deterministic path, it cannot change that path. Nonzero rejection counts require autonomous replay to evaluate the new position path; they are not a new backtest result.'},indent=2))


def entry_crossing_screen():
    """Compare rank-crossing entry criteria, retaining unchanged level controls."""
    root=OUTPUT/'replication_trials';target=root/'crossings';target.mkdir(exist_ok=True)
    seeds=(('main','423e6e825459ca2c'),('opening_atm','c6a30e15e1bbf4e8'),
        ('opening_volume','15b3eed5b443e0cd'),('boundaries','0868ced4b10c99d7'))
    rows=[];candidates=[];inputs={};details=[]
    for family,identity in seeds:
        directory=root if family=='main' else root/family
        seed=next(f for f in json.loads((directory/'frontier.json').read_text()) if f['candidate_id']==identity)
        with np.load(directory/f'candidate_{identity}.npz',allow_pickle=False) as stored:
            minutes=stored['minutes'].copy();a=stored['alpha'].copy();b=stored['alpha2'].copy()
        idx=pd.to_datetime(minutes,unit='ns',utc=True).tz_convert(IST);scorer=Scorer(idx)
        comparison=seed['recipe'].get('threshold_comparison','strict')
        baseline_signal=scorer.score(a,b,comparison)[1]
        for mode in ('level','joint','alpha','alpha2','both'):
            recipe={**seed['recipe'],'entry_event':mode,'crossing_seed_family':family,'crossing_seed_candidate_id':identity}
            rid=json.dumps(recipe,sort_keys=True,separators=(',',':'))
            cid=hashlib.sha256(f'{seed["alpha"]}|{rid}'.encode()).hexdigest()[:16]
            allowed=entry_event_mask(a,b,mode,comparison)
            metrics,signal=scorer.score(a,b,comparison,allowed)
            if mode=='level' and metrics!=seed['metrics']:raise ValueError('Entry crossing level control changed source scores')
            f={'candidate_id':cid,'alpha':seed['alpha'],'alpha_recipe':seed['alpha_recipe'],
                'recipe':recipe,'metrics':metrics,'objective':[metrics['fit_first_exact'],metrics['fit_direction_matches'],-metrics['fit_signal_episodes']]}
            if mode=='level':f.update({'control_type':'entry_event','selection_note':'Unchanged level control, excluded from crossing-rule selection.'})
            candidates.append(f);inputs[cid]=(minutes,a,b)
            rows.append({'recipe_id':rid,'alpha':seed['alpha'],**recipe,**metrics})
            for i,t in enumerate(scorer.trades.itertuples()):
                k=scorer.entries[i];previous=k-1
                details.append({'candidate_id':cid,'seed_candidate_id':identity,'seed_family':family,
                    'entry_event':mode,'signal_id':t.signal_id,'entry':t.entry,'option_type':t.option_type,'split':t.split,
                    'alpha':a[k],'alpha2':b[k],'previous_alpha':a[previous] if previous>=0 else np.nan,
                    'previous_alpha2':b[previous] if previous>=0 else np.nan,
                    'prior_observation':idx[previous] if previous>=0 else pd.NaT,
                    'level_entry_conditions_pass':bool(baseline_signal[k]==t.direction),
                    'entry_conditions_pass':bool(signal[k]==t.direction),
                    'crossing_rejects_level_pass':bool(baseline_signal[k]==t.direction and signal[k]!=t.direction)})
        print(f'Entry crossing seed {family}/{identity}: five matched rules',flush=True)
    selected=sorted((f for f in candidates if f['recipe']['entry_event']!='level'),key=lambda f:tuple(f['objective']),reverse=True)
    controls=[f for f in candidates if f['recipe']['entry_event']=='level']
    frontier=selected+controls
    for f in frontier:
        minutes,a,b=inputs[f['candidate_id']]
        np.savez_compressed(target/f'candidate_{f["candidate_id"]}.npz',minutes=minutes,alpha=a,alpha2=b)
    pd.DataFrame(rows).to_csv(target/'formula_trials.csv',index=False)
    pd.DataFrame(details).to_csv(target/'entry_crossing_every_trade.csv',index=False)
    (target/'frontier.json').write_text(json.dumps(frontier,indent=2))
    (target/'crossing_design.json').write_text(json.dumps({'trials':len(rows),'fit_selected_crossing_leader':selected[0]['candidate_id'],
        'seeds':[{'family':f,'candidate_id':c} for f,c in seeds],
        'rules':{'level':'Both ranks meet the original directional cutoffs; unchanged control.',
            'joint':'Both meet cutoffs now, but did not both meet that directional pair in the preceding observation.',
            'alpha':'Both meet cutoffs now; alpha alone newly meets the cutoff.',
            'alpha2':'Both meet cutoffs now; alpha2 alone newly meets the cutoff.',
            'both':'Both ranks newly meet their cutoff on the same observation.'},
        'prior_observation':'Immediately preceding completed trading observation; before entry-clock eligibility. No clock/session/flat-position reset. Both prior ranks must be finite.',
        'selection':'Fit first exact, then fit direction matches, then fewer fit episodes. Level controls excluded from choosing a crossing rule, and reported explicitly.',
        'limits':'This tests a hypothesis not stated in the supplied description. Source labels and position history are comparison data, never mask inputs. Later periods already inspected; not untouched holdouts. No production change.'},indent=2))
    entry_episode_audit(seeds,target)
    print('Fit-selected crossing candidate:',selected[0]['candidate_id'],selected[0]['recipe']['entry_event'],selected[0]['objective'],flush=True)


def replay_frontier(count=4,candidate_id=None):
    """Autonomous recent-week replay; source history never supplies position state."""
    from backtest.dhan_history import DhanHistoryClient,download
    from backtest.dhan_replay import load_history,supplement_fixed_contracts,DhanReplay,mark_open_trades
    from backtest.nse_settlement import NSESettlementClient
    first,last=date(2026,9,28),date(2026,10,1)
    start,stop=date(2026,9,7),date(2026,10,2)
    client=DhanHistoryClient(offline=True);calendar=ProviderCalendar()
    download(client,start,stop)
    bars,options,conflicts=load_history(client,start,stop,calendar=calendar,expiry_resolver=expiries_for)
    options,fixed=supplement_fixed_contracts(client,bars,options,stop,calendar,expiries_for,lot_size)
    settlement=NSESettlementClient(client.cache_dir,offline=True)
    source=provider_trades();source=source.loc[(source.entry.dt.date>=first)&(source.entry.dt.date<=last)]
    frontier=json.loads((OUT/'frontier.json').read_text())
    if candidate_id is not None:
        frontier=[f for f in frontier if f['candidate_id']==candidate_id]
        if not frontier:raise ValueError('Candidate not in saved frontier')
    else:frontier=frontier[:count]
    comparison=[]
    for candidate in frontier:
        cid=candidate['candidate_id']
        with np.load(OUT/f'candidate_{cid}.npz',allow_pickle=False) as stored:
            idx=pd.to_datetime(stored['minutes'],unit='ns',utc=True).tz_convert(IST)
            indicators=pd.DataFrame({'alpha':stored['alpha'],'alpha2':stored['alpha2']},index=idx)
        # Preserve exact threshold boundaries if reading an earlier float32 cache.
        for threshold in (.2,.8):
            indicators=indicators.mask(np.isclose(indicators,threshold,atol=1e-7,rtol=0),threshold)
        for style in ('description','ledger'):
            cfg=StrategyConfig()
            if style=='ledger':
                cfg=replace(cfg,strike_reference='last_bar_open',max_short_premium=200,monday_capital_fraction=.8)
            cfg=threshold_config(cfg,candidate['recipe'].get('threshold_comparison','strict'))
            cfg=history_config(cfg)
            replay=DhanReplay(cfg,bars,options,settlement_loader=settlement.get,calendar=calendar,expiry_resolver=expiries_for,lot_resolver=lot_size)
            replay._indicator_frame=lambda:indicators
            apply_research_gates(replay,candidate)
            result=replay.run(start=datetime.combine(first,time.min,IST),entry_end=datetime.combine(last,time.max,IST),
                             reentry_after_exit=candidate['recipe'].get('reentry_after_exit',False))
            trades=result.to_frame()
            if not trades.empty:
                for column in ('sell_leg_entry','buy_leg_entry','sell_leg_exit','buy_leg_exit','scheduled_exit'):
                    trades[column]=[replay.trade_details[t].get(column) for t in trades.entry_ts]
            mark_open_trades(trades,replay,result.last_decision)
            target=OUT/f'autonomous_{cid}_{style}';target.mkdir(exist_ok=True)
            from backtest.provider_autonomous import write_trial_performance
            performance=write_trial_performance(target,trades,cfg.capital,first,last,
                metadata={'candidate_id':cid,'execution_style':style,'period':'recent-week;starts flat',
                          'missing_held_quote_minutes':len(replay.coverage_events)},source=source)
            trades.to_csv(target/'trades.csv',index=False)
            pd.DataFrame(replay.coverage_events).to_csv(target/'missing_position_quotes.csv',index=False)
            pd.DataFrame(replay.decisions).to_csv(target/'decisions.csv.gz',index=False,compression='gzip')
            exact=0;exit_exact=0;directional=0
            for t in trades.itertuples():
                matches=source.loc[(source.entry_minute==pd.Timestamp(t.entry_ts))&(source.option_type==t.option_type)&
                    (source.short_strike==t.sell_strike)&(source.hedge_strike==t.buy_strike)&(source.expiry==t.expiry)]
                exact+=int(not matches.empty)
                if not matches.empty and pd.notna(t.exit_ts):exit_exact+=int(matches.iloc[0].exit_minute==pd.Timestamp(t.exit_ts))
                directional+=int(((source.entry.dt.date==t.entry_ts.date())&(source.option_type==t.option_type)).any())
            closed=trades.loc[trades.exit_ts.notna()] if not trades.empty else trades
            pnl=float(closed.pnl.sum()) if not closed.empty else 0.
            mtm=float(trades.unrealized_pnl.sum()) if not trades.empty else 0.
            unvalued=int((trades.exit_ts.isna()&trades.unrealized_pnl.isna()).sum()) if not trades.empty else 0
            record={'candidate_id':cid,'execution_style':style,'alpha':candidate['alpha'],
                'recipe':json.dumps(candidate['recipe'],sort_keys=True),'source_trades':len(source),
                'simulated_entries':len(trades),'exact_entries_direction_strikes':exact,'exact_exits_for_exact_entries':exit_exact,
                'same_day_direction_matches':directional,'extra_entries':len(trades)-exact,'missing_source_entries':len(source)-exact,
                'closed_trades':len(closed),'open_trades':len(trades)-len(closed),'realized_pnl':pnl,'unrealized_pnl':None if unvalued else mtm,
                'total_pnl':None if unvalued else pnl+mtm,'missing_held_quote_minutes':len(replay.coverage_events),'unvalued_open_positions':unvalued}
            comparison.append(record)
            (target/'report.json').write_text(json.dumps({'result':record,'candidate':candidate,'config':asdict(cfg),
                'performance':performance['performance'],'zen_same_period_performance':performance['zen_same_period'],
                'source_reported_pnl':float(source.pnl_reported.sum()),'limitations':['No future prices, source position resets, or provider entry dates supplied to engine.',
                    'Starts flat at Sep 28; values strictly through Oct 1, costs excluded.',
                    'Minute closes approximate fills; missing original contract prices can delay exits.',
                    'Ledger execution style uses empirically observed strike/premium/allocation assumptions; description style uses latest description defaults.']},indent=2,default=str))
            value='unavailable' if unvalued else f'{pnl+mtm:.2f}'
            print(f'Autonomous {cid} {style}: entries={len(trades)}, exact={exact}/{len(source)}, extra={len(trades)-exact}, gross+MTM={value}, gaps={len(replay.coverage_events)}',flush=True)
    comparison_path=OUT/'autonomous_comparison.csv'
    frame=pd.DataFrame(comparison)
    if comparison_path.exists():
        frame=pd.concat([pd.read_csv(comparison_path),frame],ignore_index=True).drop_duplicates(
            ['candidate_id','execution_style'],keep='last')
    frame.to_csv(comparison_path,index=False)


def benchmark_rolling_cache():
    """Measure repeated rolling work on real cached panels; verify exact arrays."""
    import time as timing
    bars,_,_=context();records=[]
    for name,(p,take) in factor_contexts(bars,opening=True).items():
        if name not in ('continuous_near','expiry_near'):continue
        groups=p.groupby('expiry',sort=False).groups if take is not None else None
        def grouped(s,fn):
            if groups is None:return fn(s)
            out=pd.Series(np.nan,index=p.index)
            for ids in groups.values():out.loc[ids]=fn(s.loc[ids]).to_numpy()
            return out
        requests=[(side,w,mp) for _ in range(3) for short in (1,5,15) for baseline in (20,60,300)
            for side in ('ce','pe') for w,mp in ((short,short),(baseline,int(np.ceil(.8*baseline))))]
        digests=[];plain_seconds=0.
        for side,w,mp in requests:
            volume=p[f'{side}_native_volume'];start=timing.perf_counter()
            value=grouped(volume,lambda s:s.rolling(w,min_periods=mp).mean())
            plain_seconds+=timing.perf_counter()-start
            digests.append(hashlib.sha256(value.to_numpy().tobytes()).hexdigest())
        cache=RollingMeanCache(grouped);cached_seconds=0.
        for request,expected in zip(requests,digests):
            side,w,mp=request;volume=p[f'{side}_native_volume'];start=timing.perf_counter()
            value=cache.mean(volume,('native',side),w,mp)
            cached_seconds+=timing.perf_counter()-start
            if hashlib.sha256(value.to_numpy().tobytes()).hexdigest()!=expected:
                raise ValueError(f'Rolling cache changes output: {name}, {request}')
        record={'context':name,'rows':len(p),'requests':len(requests),
            'uncached_seconds':plain_seconds,'cached_seconds':cached_seconds,
            'component_speedup':plain_seconds/cached_seconds,'hits':cache.hits,'misses':cache.misses,
            'cached_array_bytes':cache.bytes,'all_arrays_exact':True}
        records.append(record);print(json.dumps(record),flush=True)
    path=OUT/'rolling_cache_benchmark.json'
    path.write_text(json.dumps({'scope':'Repeated volume rolling-mean calculations only; data loading, hashing, rank generation and autonomous replay excluded from timings.',
        'results':records,'warning':'Component speedup is not an end-to-end search speedup. Cache is local to one unchanged input context and bounded to 64 MiB.'},indent=2))


def attach_exact_implied_volatility(panel, fields):
    """Attach completed IV only for the same minute, expiry and ATM strike."""
    keys = ['minute', 'expiry', 'atm_strike']
    source = panel.drop(columns=['ce_iv', 'pe_iv'], errors='ignore').copy()
    source['minute'] = pd.DatetimeIndex(source.index) if 'minute' not in source else source['minute']
    source = source.reset_index(drop=True)
    right = fields[keys + ['ce_iv', 'pe_iv']].copy()
    for frame in (source, right):
        frame['minute'] = pd.to_datetime(frame['minute'], utc=True).dt.tz_convert(IST)
        frame['expiry'] = frame['expiry'].astype(str)
    joined = source.merge(right, on=keys, how='left', validate='one_to_one', sort=False)
    joined.index = panel.index
    return joined


def implied_volatility_scale(panel, kind, window=1):
    """Completed CE+PE IV scale; unknown current IV stays unknown."""
    if kind not in ('level', 'mean', 'std') or not isinstance(window, int) or window < 1:
        raise ValueError('Invalid implied-volatility transform')
    ce = panel.ce_iv.where(panel.ce_iv > 0)
    pe = panel.pe_iv.where(panel.pe_iv > 0)
    if kind == 'level':
        return ce + pe
    minimum = int(np.ceil(.8 * window))
    transform = lambda value: getattr(value.rolling(window, min_periods=minimum), kind)()
    return (transform(ce) + transform(pe)).where(ce.notna() & pe.notna())


def implied_volatility_screen(opening_complete=False):
    """Finite IV alternatives, scored on fit labels; no source-state replay."""
    family = 'implied_volatility_opening_complete' if opening_complete else 'implied_volatility'
    directory = OUTPUT/'replication_trials'/family
    directory.mkdir(exist_ok=True)
    main_directory = OUTPUT/'replication_trials'
    bars, panels, _ = context()
    bank = load_alpha(main_directory)
    alpha_recipes = json.loads((main_directory/'alpha_recipes.json').read_text())
    if opening_complete:
        from backtest.provider_fixed_factors import OPENING_FULL_FIELDS_CACHE
        field_source = OPENING_FULL_FIELDS_CACHE
        fields = pd.read_csv(field_source, usecols=['minute','expiry','atm_strike','ce_iv','pe_iv'])
    else:
        field_source = FEATURE_CACHE
        fields = pd.read_csv(field_source)
    opening = factor_contexts(bars, opening=True)['continuous_near'][0]
    opening = attach_exact_implied_volatility(opening, fields)
    if opening_complete:
        for side in ('ce','pe'):
            opening[side+'_iv']=opening[side+'_iv'].where(lambda value:np.isfinite(value)&value.gt(0))
    scorer = Scorer(bars.index)
    records = []; frontier = []; selected_inputs = {}
    alpha_inputs = [(name, bank[name], alpha_recipes[name], 'observed') for name in BULK_ALPHAS]
    if opening_complete:
        from backtest.provider_price_bounds import calendar_support_rank
        for name in ('close_old_open_h5_r800', 'close_close_old_open_h5_r800'):
            original_recipe = alpha_recipes[name]
            raw = price_change_series(bars, original_recipe)
            alpha_inputs.append((name+'_calendar_closed_zero',calendar_support_rank(raw,closed_zero=True),
                {**original_recipe,'rank_support':'calendar_closed_zero'},'calendar_closed_zero'))
    transforms = [('level', 1), ('mean', 20), ('mean', 60), ('std', 60), ('std', 300)]
    coverage = {}
    references = [('last_completed_bar_open', opening)] if opening_complete else [
        ('last_completed_bar_close', panels['near']), ('last_completed_bar_open', opening)]
    for reference, panel in references:
        valid = panel.ce_iv.gt(0) & panel.pe_iv.gt(0) & np.isfinite(panel.ce_iv) & np.isfinite(panel.pe_iv)
        coverage[reference] = {'minutes': len(panel), 'known_positive_both_iv': int(valid.sum()),
                              'source_entries_with_both_iv': int(valid.iloc[scorer.entries].sum())}
        if opening_complete:
            source_rows=[]
            for position,trade in zip(scorer.entries,scorer.trades.itertuples()):
                source_rows.append({'signal_id':trade.signal_id,'entry':trade.entry,
                    'completed_decision_minute':panel.index[position],
                    'expiry':panel.expiry.iloc[position],'opening_atm_strike':panel.atm_strike.iloc[position],
                    'ce_iv':panel.ce_iv.iloc[position],'pe_iv':panel.pe_iv.iloc[position],
                    'both_current_iv_known':bool(valid.iloc[position])})
            pd.DataFrame(source_rows).to_csv(directory/'source_entry_iv_coverage.csv',index=False)
        scales = {(kind, window): implied_volatility_scale(panel, kind, window)
                  for kind, window in transforms}
        for baseline in (10, 15, 20):
            ratios = [panel[f'{side}_native_volume'] / panel[f'{side}_native_volume'].rolling(
                baseline, min_periods=int(np.ceil(.8*baseline))).mean().where(lambda s: s > 0)
                for side in ('ce', 'pe')]
            multipliers = {'native': (ratios[0]+ratios[1])/2,
                           'geometric_ratios': np.sqrt(ratios[0]*ratios[1])}
            total = panel.ce_native_volume + panel.pe_native_volume
            multipliers['total_ratio'] = total/total.rolling(baseline,
                min_periods=int(np.ceil(.8*baseline))).mean().where(lambda s: s > 0)
            for volume_kind, multiplier in multipliers.items():
                for (kind, window), scale in scales.items():
                    for lag in (0, 5):
                        factor = multiplier.shift(lag)/scale.shift(lag).where(lambda s: s > 0)
                        for alpha_name, alpha, alpha_recipe, support in alpha_inputs:
                            raw = price_change_series(bars, alpha_recipe)*factor
                            beta = rank(raw, 300)
                            metrics, _ = scorer.score(alpha, beta)
                            recipe = {'context': 'continuous_near', 'volume_kind': volume_kind,
                                'volume_short': 1, 'volume_baseline': baseline,
                                'volatility': f'implied_{kind}_{window}', 'factor_lag': lag,
                                'rank_window': 300, 'price_change': 'same_as_alpha_v2',
                                'atm_reference': reference, 'profit_target_mode': 'disabled',
                                'input_policy': 'exact-minute-expiry-strike-IV;positive-both;current-IV-required;no-fill'}
                            if opening_complete:
                                recipe.update({'input_policy':'opening-full-exact-minute-expiry-strike-IV;finite-positive-both;current-IV-required;original-native-volumes;no-fill',
                                    'alpha_rank_support':support})
                            identity = hashlib.sha256(json.dumps({'alpha': alpha_name,
                                'recipe': recipe}, sort_keys=True).encode()).hexdigest()[:16]
                            candidate = {'candidate_id': identity, 'alpha': alpha_name,
                                'alpha_recipe': alpha_recipe, 'recipe': recipe, 'metrics': metrics,
                                'objective': [metrics['fit_first_exact'], metrics['fit_direction_matches'],
                                              -metrics['fit_signal_episodes']]}
                            records.append(candidate)
                            if len(frontier) < 12 or tuple(candidate['objective']) > tuple(frontier[-1]['objective']):
                                if opening_complete:selected_inputs[identity]=(alpha.to_numpy(),beta.to_numpy())
                                else:
                                    np.savez_compressed(directory/f'candidate_{identity}.npz',
                                        minutes=bars.index.as_unit('ns').asi8,
                                        alpha=alpha.to_numpy(), alpha2=beta.to_numpy())
                                frontier.append(candidate)
                                frontier.sort(key=lambda c: (tuple(c['objective']), c['candidate_id']), reverse=True)
                                frontier = frontier[:12]
                                if opening_complete:
                                    selected_inputs={c['candidate_id']:selected_inputs[c['candidate_id']] for c in frontier}
        print('IV screen completed reference', reference, 'pairs', len(records), flush=True)
    if opening_complete:
        for identity,(alpha,beta) in selected_inputs.items():
            np.savez_compressed(directory/f'candidate_{identity}.npz',
                minutes=bars.index.as_unit('ns').asi8,alpha=alpha,alpha2=beta)
    pd.DataFrame([{'candidate_id': c['candidate_id'], 'alpha': c['alpha'],
        'recipe': json.dumps(c['recipe'], sort_keys=True), **c['metrics']} for c in records]).to_csv(
            directory/'formula_trials.csv', index=False)
    (directory/'frontier.json').write_text(json.dumps(frontier, indent=2))
    design = {'pairs': len(records), 'coverage': coverage, 'volatility_transforms': transforms,
        'alpha_names': [name for name,_,_,_ in alpha_inputs], 'fit_cutoff': '2026-02-28',
        'causality': 'All IV and volume belong to completed candles. Lag shifts observed bars. No current forming close, future values or source position resets in replay.',
        'limitations': ['Source-exit resets occur only in conditional screening; scores cannot prove autonomous replication or safely prune all other formulas.',
            'Opening IV is available only where the full-feature cache has the exact opening-selected strike. Missing current IV is never filled.',
            'Chronological later periods were inspected previously; they are not untouched holdouts.',
            'An IV interpretation is a hypothesis, distinct from rolling option-return volatility in the supplied description.']}
    if opening_complete:
        design.update({'family':family,'field_source':str(field_source),
            'iv_join':'Only exact completed decision minute, expiry and opening-selected strike. IV-only join preserves original native volume factors.',
            'full_cache_rows':len(fields),'selected_opening_minutes':len(opening),
            'alpha_rank_supports':['Original800 observed returns','Explicit800 calendar slots with assumed zero closed-market returns'],
            'calendar_policy':'Closed-market zero returns are an explicit assumption, not observed data. Unknown regular-session returns remain unknown. No quote, IV or volume fill.',
            'current_iv_policy':'Both current IV values finite and strictly positive. Rolling IV mean/STD remains unknown when current IV absent; lag5 uses that past factor observation.',
            'rank_policy':{'alpha_observed_window':800,'alpha_observed_minimum_fraction':1.,'beta_window':300,'beta_minimum_fraction':.9,'strict_thresholds':[.8,.2]},
            'archive_policy':'Only final12 finalists written; transient leaders retained in bounded memory.',
            'source_coverage_report':'source_entry_iv_coverage.csv; allsource timestamps are diagnostic labels only',
            'limitations':['Conditional screening cannot establish autonomous replication. Later periods previously inspected.',
                'Calendar closed-zero support is a hypothesis; allsource IV availability is data coverage, not trigger proof.',
                'An IV interpretation differs from option-return rolling volatility and is not a recovered private formula.']})
    (directory/'search_design.json').write_text(json.dumps(design, indent=2))
    print('IV frontier', [(c['candidate_id'], c['objective']) for c in frontier[:3]], flush=True)


def attach_exact_opening_ohlc(panel, fields):
    """Join option OHLC only; original selected native-volume factors survive."""
    keys=['minute','expiry','atm_strike']
    columns=[f'{side}_{field}' for side in ('ce','pe') for field in ('open','high','low','close')]
    source=panel.drop(columns=columns,errors='ignore').copy()
    source['minute']=source.index if 'minute' not in source else source.minute
    source=source.reset_index(drop=True);right=fields[keys+columns].copy()
    for frame in (source,right):
        frame['minute']=pd.to_datetime(frame.minute,utc=True).dt.tz_convert(IST)
        frame['expiry']=frame.expiry.astype(str)
    joined=source.merge(right,on=keys,how='left',validate='one_to_one',sort=False)
    joined.index=panel.index
    return joined


def opening_ohlc_validity(panel, side):
    prices=panel[[f'{side}_{field}' for field in ('open','high','low','close')]]
    o,h,l,c=(prices[f'{side}_{field}'] for field in ('open','high','low','close'))
    return (np.isfinite(prices).all(axis=1)&prices.gt(0).all(axis=1)&
        l.le(o)&l.le(c)&h.ge(o)&h.ge(c)&h.ge(l))


def opening_ohlc_volatility(panel, kind, window):
    """Sum per-leg rolling volatility from completed, coherent option candles."""
    if kind not in ('intrabar_return_std','parkinson','garman_klass'):
        raise ValueError('Unknown option OHLC volatility estimator')
    if isinstance(window,bool) or not isinstance(window,int) or window<2:
        raise ValueError('Option OHLC volatility needs a window of at least2')
    minimum=int(np.ceil(.8*window));scales=[];known=[]
    for side in ('ce','pe'):
        valid=opening_ohlc_validity(panel,side);known.append(valid)
        o,h,l,c=(panel[f'{side}_{field}'].where(valid) for field in ('open','high','low','close'))
        if kind=='intrabar_return_std':
            scale=((c-o)/o).rolling(window,min_periods=minimum).std()
        else:
            squared_range=np.log(h/l).pow(2)
            variance=squared_range/(4*np.log(2)) if kind=='parkinson' else (
                .5*squared_range-(2*np.log(2)-1)*np.log(c/o).pow(2))
            # Invalid negative variances remain unknown; no synthetic zero clamp.
            variance=variance.where(np.isfinite(variance)&variance.ge(0))
            scale=np.sqrt(variance.rolling(window,min_periods=minimum).mean())
        scales.append(scale)
    return (scales[0]+scales[1]).where(known[0]&known[1])


def opening_ohlc_screen():
    """Finite selected-ATM OHLC-volatility hypotheses, not fixed-strike histories."""
    from backtest.provider_fixed_factors import OPENING_FULL_FIELDS_CACHE
    from backtest.provider_price_bounds import calendar_support_rank
    directory=OUTPUT/'replication_trials'/'opening_ohlc_volatility';directory.mkdir(exist_ok=True)
    root=OUTPUT/'replication_trials';bars,_,_=context();bank=load_alpha(root)
    alpha_recipes=json.loads((root/'alpha_recipes.json').read_text());scorer=Scorer(bars.index)
    columns=['minute','expiry','atm_strike']+[f'{side}_{field}' for side in ('ce','pe') for field in ('open','high','low','close')]
    fields=pd.read_csv(OPENING_FULL_FIELDS_CACHE,usecols=columns)
    original=factor_contexts(bars,opening=True)['continuous_near'][0]
    panel=attach_exact_opening_ohlc(original,fields)
    inputs=[(name,bank[name],alpha_recipes[name],'observed') for name in BULK_ALPHAS]
    for name in ('close_old_open_h5_r800','close_close_old_open_h5_r800'):
        recipe=alpha_recipes[name]
        inputs.append((name+'_calendar_closed_zero',calendar_support_rank(price_change_series(bars,recipe),closed_zero=True),
            {**recipe,'rank_support':'calendar_closed_zero'},'calendar_closed_zero'))
    scales={(kind,window):opening_ohlc_volatility(panel,kind,window)
        for kind in ('intrabar_return_std','parkinson','garman_klass') for window in (60,150,300)}
    valid=opening_ohlc_validity(panel,'ce')&opening_ohlc_validity(panel,'pe')
    source_rows=[]
    for position,trade in zip(scorer.entries,scorer.trades.itertuples()):
        row={'signal_id':trade.signal_id,'entry':trade.entry,'completed_decision_minute':panel.index[position],
            'expiry':panel.expiry.iloc[position],'opening_atm_strike':panel.atm_strike.iloc[position],
            'both_current_ohlc_valid':bool(valid.iloc[position])}
        row.update({f'{kind}_{window}':scale.iloc[position] for (kind,window),scale in scales.items()})
        source_rows.append(row)
    pd.DataFrame(source_rows).to_csv(directory/'source_entry_ohlc_coverage.csv',index=False)
    records=[];frontier=[];selected={}
    for baseline in (10,15,20):
        ratios=[panel[f'{side}_native_volume']/panel[f'{side}_native_volume'].rolling(
            baseline,min_periods=int(np.ceil(.8*baseline))).mean().where(lambda s:s>0) for side in ('ce','pe')]
        total=panel.ce_native_volume+panel.pe_native_volume
        multipliers={'native':(ratios[0]+ratios[1])/2,'geometric_ratios':np.sqrt(ratios[0]*ratios[1]),
            'total_ratio':total/total.rolling(baseline,min_periods=int(np.ceil(.8*baseline))).mean().where(lambda s:s>0)}
        for volume_kind,multiplier in multipliers.items():
            for (kind,window),scale in scales.items():
                for lag in (0,5):
                    factor=multiplier.shift(lag)/scale.shift(lag).where(lambda s:s>0)
                    for alpha_name,alpha,alpha_recipe,support in inputs:
                        beta=rank(price_change_series(bars,alpha_recipe)*factor,300)
                        metrics,_=scorer.score(alpha,beta)
                        recipe={'context':'continuous_near','volume_kind':volume_kind,'volume_short':1,
                            'volume_baseline':baseline,'volatility':f'opening_ohlc_{kind}_{window}','factor_lag':lag,
                            'rank_window':300,'price_change':'same_as_alpha_v2','atm_reference':'last_completed_bar_open',
                            'alpha_rank_support':support,'profit_target_mode':'disabled',
                            'input_policy':'opening-full-exact-OHLC;finite-positive-coherent-current-both;selected-ATM-history;native-volumes-preserved;vol80;rank90;no-fill'}
                        identity=hashlib.sha256(json.dumps({'alpha':alpha_name,'recipe':recipe},sort_keys=True).encode()).hexdigest()[:16]
                        candidate={'candidate_id':identity,'alpha':alpha_name,'alpha_recipe':alpha_recipe,'recipe':recipe,
                            'metrics':metrics,'objective':[metrics['fit_first_exact'],metrics['fit_direction_matches'],-metrics['fit_signal_episodes']]}
                        records.append(candidate)
                        if len(frontier)<12 or tuple(candidate['objective'])>tuple(frontier[-1]['objective']):
                            selected[identity]=(alpha.to_numpy(),beta.to_numpy());frontier.append(candidate)
                            frontier.sort(key=lambda c:(tuple(c['objective']),c['candidate_id']),reverse=True);frontier=frontier[:12]
                            selected={c['candidate_id']:selected[c['candidate_id']] for c in frontier}
    for identity,(alpha,beta) in selected.items():
        np.savez_compressed(directory/f'candidate_{identity}.npz',minutes=bars.index.as_unit('ns').asi8,alpha=alpha,alpha2=beta)
    pd.DataFrame([{'candidate_id':c['candidate_id'],'alpha':c['alpha'],'recipe':json.dumps(c['recipe'],sort_keys=True),
        **c['metrics']} for c in records]).to_csv(directory/'formula_trials.csv',index=False)
    (directory/'frontier.json').write_text(json.dumps(frontier,indent=2))
    design={'pairs':len(records),'source':str(OPENING_FULL_FIELDS_CACHE),'field_rows':len(fields),'selected_minutes':len(panel),
        'both_current_ohlc_valid':int(valid.sum()),'source_entries_both_current_ohlc_valid':int(valid.iloc[scorer.entries].sum()),
        'source_scale_coverage':{f'{kind}_{window}':int(np.isfinite(scale.iloc[scorer.entries]).sum()) for (kind,window),scale in scales.items()},
        'source_positive_denominator_coverage':{f'{kind}_{window}':int((np.isfinite(scale.iloc[scorer.entries])&scale.iloc[scorer.entries].gt(0)).sum()) for (kind,window),scale in scales.items()},
        'formulas':{'intrabar_return_std':'CE+PE sampleSTD((close-open)/open)',
            'parkinson':'CE+PE sqrt(rollingmean(log(high/low)^2)/(4ln2))',
            'garman_klass':'CE+PE sqrt(rollingmean(0.5log(high/low)^2-(2ln2-1)log(close/open)^2))'},
        'windows':[60,150,300],'minimum_volatility_fraction':.8,'beta_rank_window':300,'minimum_beta_fraction':.9,
        'alpha_names':[name for name,_,_,_ in inputs],'strict_thresholds':[.8,.2],
        'current_policy':'All CE/PE OHLC finite and strictly positive, low<=open/close<=high. Missing or invalid current candle keeps rolling scale unknown; lag5 uses that past observation.',
        'history_policy':'Each bar is an exact same-candle option return/range. Rolling estimates follow the selected opening-ATM path across strike/expiry changes; this is not own-contract history.',
        'calendar_policy':'Calendar-zero alpha1 assumes closed-market zero returns. Regular-session unknown returns and all quotes/volumes remain unknown; no fitted time/date gates.',
        'archive_policy':'Only final12 NPZ archives; bounded transient leaders in memory.',
        'source_coverage':'source_entry_ohlc_coverage.csv; source timestamps are labels only',
        'causality':'Only completed candles at raw-start+1min decision clock. No source events feed features, no fills or timestamps changed.',
        'limits':'These three denominators are new volatility hypotheses, not private-provider formulas. They cannot repair nine original observed-alpha1 failures. Conditional fit selection needs autonomous replay; later chronological periods previously inspected.'}
    (directory/'search_design.json').write_text(json.dumps(design,indent=2))
    print(json.dumps({'pairs':len(records),'coverage':design['source_scale_coverage'],'frontier':[(c['candidate_id'],c['objective']) for c in frontier[:4]]},indent=2),flush=True)


def opening_fixed_factor_screen():
    """Own-strike factors, then rank along the selected ATM factor path."""
    from backtest.provider_fixed_factors import OPENING_FIXED_CACHE
    directory = OUTPUT/'replication_trials'/'opening_fixed'; directory.mkdir(exist_ok=True)
    main_directory = OUTPUT/'replication_trials'
    bars, _, _ = context(); bank = load_alpha(main_directory); scorer = Scorer(bars.index)
    recipes = json.loads((main_directory/'alpha_recipes.json').read_text())
    contexts = factor_contexts(bars, opening=True)
    panel, take = contexts['expiry_near']
    extra = pd.read_csv(OPENING_FIXED_CACHE)
    extra.minute = pd.to_datetime(extra.minute, utc=True).dt.tz_convert(IST)
    keys = ['minute', 'expiry', 'atm_strike']
    panel = panel.merge(extra, on=keys, how='left', validate='one_to_one', sort=False)
    continuous = panel.loc[take].set_index('minute').reindex(bars.index)
    records = []; frontier = []; coverage = {}
    for context_name, values, mask in [('continuous_near', continuous, None),
                                       ('expiry_near', panel, take)]:
        groups = None if mask is None else values.groupby('expiry', sort=False).groups
        def grouped(series, fn):
            if groups is None:
                return fn(series)
            result = pd.Series(np.nan, index=series.index)
            for ids in groups.values():
                result.loc[ids] = fn(series.loc[ids]).to_numpy()
            return result
        def align(series):
            if mask is None:
                return series.reindex(bars.index)
            return pd.Series(series.loc[mask].to_numpy(),
                index=pd.DatetimeIndex(values.loc[mask, 'minute'])).reindex(bars.index)
        coverage[context_name] = {}
        for baseline in (10, 15, 20):
            for window in (150, 300):
                multiplier = values[f'fixed_volume_ratio_1_{baseline}']
                scale = values[f'fixed_log_return_{window}']
                coverage[context_name][f'baseline{baseline}_std{window}'] = int(
                    (np.isfinite(align(multiplier).iloc[scorer.entries]) &
                     np.isfinite(align(scale).iloc[scorer.entries])).sum())
                for lag in (0, 5):
                    factor = grouped(multiplier, lambda s: s.shift(lag))/grouped(
                        scale, lambda s: s.shift(lag)).where(lambda s: s > 0)
                    for alpha_name in BULK_ALPHAS:
                        raw = price_change_series(bars, recipes[alpha_name])
                        if mask is not None:
                            raw = pd.Series(raw.reindex(pd.DatetimeIndex(values.minute)).to_numpy(), index=values.index)
                        beta = align(grouped(raw*factor, lambda s: rank(s, 300)))
                        metrics, _ = scorer.score(bank[alpha_name], beta)
                        recipe = {'context': context_name, 'volume_kind': 'fixed_native',
                            'volume_short': 1, 'volume_baseline': baseline,
                            'volatility': f'fixed_log_return_{window}', 'factor_lag': lag,
                            'rank_window': 300, 'price_change': 'same_as_alpha_v2',
                            'atm_reference': 'last_completed_bar_open', 'profit_target_mode': 'disabled',
                            'input_policy': 'same-expiry-strike-own-history;min80;rank90;no-fill;rank-selected-path'}
                        cid = hashlib.sha256(json.dumps({'alpha': alpha_name,
                            'recipe': recipe}, sort_keys=True).encode()).hexdigest()[:16]
                        candidate = {'candidate_id': cid, 'alpha': alpha_name,
                            'alpha_recipe': recipes[alpha_name], 'recipe': recipe, 'metrics': metrics,
                            'objective': [metrics['fit_first_exact'], metrics['fit_direction_matches'],
                                          -metrics['fit_signal_episodes']]}
                        records.append(candidate)
                        if len(frontier) < 12 or tuple(candidate['objective']) > tuple(frontier[-1]['objective']):
                            np.savez_compressed(directory/f'candidate_{cid}.npz',
                                minutes=bars.index.as_unit('ns').asi8,
                                alpha=bank[alpha_name].to_numpy(), alpha2=beta.to_numpy())
                            frontier.append(candidate)
                            frontier.sort(key=lambda c: (tuple(c['objective']), c['candidate_id']), reverse=True)
                            frontier = frontier[:12]
        print('Opening own-strike factors screened', context_name, len(records), 'pairs', flush=True)
    pd.DataFrame([{'candidate_id': c['candidate_id'], 'alpha': c['alpha'],
        'recipe': json.dumps(c['recipe'], sort_keys=True), **c['metrics']} for c in records]).to_csv(
            directory/'formula_trials.csv', index=False)
    (directory/'frontier.json').write_text(json.dumps(frontier, indent=2))
    (directory/'search_design.json').write_text(json.dumps({'pairs': len(records), 'coverage': coverage,
        'source': str(OPENING_FIXED_CACHE), 'factor_history': 'Exact selected expiry/strike history on common observed index clock.',
        'rank_history': 'Selected ATM path, optionally separated by expiry. This is NOT a fixed-contract raw-alpha2 rank.',
        'lag': 'Shift previously selected own-strike factors by0or5 observations within context.',
        'selection': 'Fit conditional first-exact, then direction and fewer episodes. Autonomous replay required.',
        'limits': 'No source fills or position resets in execution. Unknown factors remain unknown. Later periods previously inspected; no untouched-holdout claim.'}, indent=2))
    print('Opening fixed-factor frontier', [(c['candidate_id'], c['objective']) for c in frontier[:3]], flush=True)


def opening_fixed_ohlc_screen():
    """Rank own-contract OHLC factors after selection, with expiry warmup control."""
    from backtest.provider_fixed_factors import OPENING_FIXED_OHLC_CACHE
    from backtest.provider_price_bounds import calendar_support_rank
    directory=OUTPUT/'replication_trials'/'opening_fixed_ohlc';directory.mkdir(exist_ok=True)
    root=OUTPUT/'replication_trials';bars,_,_=context();bank=load_alpha(root);scorer=Scorer(bars.index)
    recipes=json.loads((root/'alpha_recipes.json').read_text())
    keys=['minute','expiry','atm_strike']
    specifications=[]
    for kind in ('intrabar_return_std','parkinson','garman_klass'):
        for window in (150,300):
            for volume_kind in ('native','geometric_ratios','total_ratio'):
                for baseline in (10,15,20):
                    for lag in (0,5):
                        column=f'fixed_ohlc_{kind}_{window}_{volume_kind}_b{baseline}_lag{lag}'
                        specifications.append((column,kind,window,volume_kind,baseline,lag))
    fields=pd.read_csv(OPENING_FIXED_OHLC_CACHE,usecols=keys+[spec[0] for spec in specifications])
    labels=factor_contexts(bars,opening=True)['expiry_near'][0][keys].copy()
    for frame in (fields,labels):
        frame['minute']=pd.to_datetime(frame.minute,utc=True).dt.tz_convert(IST)
        frame['expiry']=frame.expiry.astype(str)
    preparation_design=OUTPUT/'opening_fixed_ohlc_design.json'
    if preparation_design.exists() and json.loads(preparation_design.read_text()).get('complete') is not True:
        raise ValueError('Fixed OHLC preparation is incomplete; finish all blocks before screening')
    missing_labels=~pd.MultiIndex.from_frame(labels[keys]).isin(pd.MultiIndex.from_frame(fields[keys]))
    if missing_labels.any():
        raise ValueError(f'Incomplete fixed OHLC preparation: {int(missing_labels.sum())} expected opening labels missing')
    panel=labels.merge(fields,on=keys,how='left',validate='one_to_one',sort=False)
    del fields,labels
    names=('close_old_open_h5_r800','close_close_old_open_h5_r800')
    changes={name:price_change_series(bars,recipes[name]) for name in names}
    alphas={name:{'observed':bank[name], 'calendar_closed_zero':calendar_support_rank(changes[name],closed_zero=True)} for name in names}
    near_by_day={day:str(expiries_for(day)[0]) for day in set(bars.index.date)}
    near_mask=np.array([expiry==near_by_day.get(minute.date()) for expiry,minute in zip(panel.expiry,panel.minute)])
    def selected_near(series):
        return pd.Series(series.loc[near_mask].to_numpy(),index=pd.DatetimeIndex(panel.loc[near_mask,'minute'])).reindex(bars.index)
    records=[];frontier=[];selected={};coverage=[];source_rows=[]
    for column,kind,window,volume_kind,baseline,lag in specifications:
        factor=panel[column].where(lambda s:np.isfinite(s)&s.ge(0));near_factor=selected_near(factor)
        for name in names:
            raw=pd.Series(changes[name].reindex(pd.DatetimeIndex(panel.minute)).to_numpy(),index=panel.index)*factor
            rank_input=panel[keys].copy();rank_input['raw']=raw
            contexts=selected_fixed_raw_ranks(rank_input,bars.index,'raw')
            for context_name,beta in contexts.items():
                coverage.append({'factor_column':column,'alpha_price_recipe':name,'context':context_name,
                    'source_known_fixed_factor':int(np.isfinite(near_factor.iloc[scorer.entries]).sum()),
                    'source_known_rank':int(np.isfinite(beta.iloc[scorer.entries]).sum())})
                for position,trade in zip(scorer.entries,scorer.trades.itertuples()):
                    observed=alphas[name]['observed'].iloc[position];calendar=alphas[name]['calendar_closed_zero'].iloc[position]
                    value=beta.iloc[position];direction=trade.direction
                    passes=lambda alpha:bool((alpha>.8 and value>.8) if direction==1 else (alpha<.2 and value<.2))
                    source_rows.append({'signal_id':trade.signal_id,'entry':trade.entry,'option_type':trade.option_type,
                        'factor_column':column,'alpha_price_recipe':name,'context':context_name,
                        'fixed_factor':near_factor.iloc[position],'alpha_observed':observed,'alpha_calendar_closed_zero':calendar,
                        'alpha2':value,'observed_both_direction_pass':passes(observed),'calendar_both_direction_pass':passes(calendar)})
                for support,alpha in alphas[name].items():
                    alpha_name=name if support=='observed' else name+'_calendar_closed_zero'
                    alpha_recipe={**recipes[name],'rank_support':support}
                    metrics,_=scorer.score(alpha,beta)
                    recipe={'context':context_name,'volume_kind':'fixed_'+volume_kind,'volume_short':1,'volume_baseline':baseline,
                        'volatility':f'fixed_ohlc_{kind}_{window}','factor_lag':lag,'rank_window':300,
                        'price_change':'same_as_alpha_v2','atm_reference':'last_completed_bar_open',
                        'alpha_rank_support':support,'fixed_factor_cache_column':column,'profit_target_mode':'disabled',
                        'input_policy':'exact-opening-label;own-contract-OHLC-volume-factor-lag-before-selection;rank-after-selection;rank90;no-fill'}
                    identity=hashlib.sha256(json.dumps({'alpha':alpha_name,'recipe':recipe},sort_keys=True).encode()).hexdigest()[:16]
                    candidate={'candidate_id':identity,'alpha':alpha_name,'alpha_recipe':alpha_recipe,'recipe':recipe,
                        'metrics':metrics,'objective':[metrics['fit_first_exact'],metrics['fit_direction_matches'],-metrics['fit_signal_episodes']]}
                    records.append(candidate)
                    if len(frontier)<12 or tuple(candidate['objective'])>tuple(frontier[-1]['objective']):
                        selected[identity]=(alpha.to_numpy(),beta.to_numpy());frontier.append(candidate)
                        frontier.sort(key=lambda c:(tuple(c['objective']),c['candidate_id']),reverse=True);frontier=frontier[:12]
                        selected={c['candidate_id']:selected[c['candidate_id']] for c in frontier}
    for identity,(alpha,beta) in selected.items():
        np.savez_compressed(directory/f'candidate_{identity}.npz',minutes=bars.index.as_unit('ns').asi8,alpha=alpha,alpha2=beta)
    pd.DataFrame([{'candidate_id':c['candidate_id'],'alpha':c['alpha'],'recipe':json.dumps(c['recipe'],sort_keys=True),
        **c['metrics']} for c in records]).to_csv(directory/'formula_trials.csv',index=False)
    pd.DataFrame(source_rows).to_csv(directory/'source_entry_diagnostics.csv',index=False)
    pd.DataFrame(coverage).to_csv(directory/'source_factor_rank_coverage.csv',index=False)
    (directory/'frontier.json').write_text(json.dumps(frontier,indent=2))
    (directory/'search_design.json').write_text(json.dumps({'pairs':len(records),'factor_columns':len(specifications),
        'source':str(OPENING_FIXED_OHLC_CACHE),'selected_factor_rows':len(panel),'contexts':['continuous_near','expiry_near'],
        'raw_price_recipes':list(names),'alpha_supports':['observed800','calendar_closed_zero800'],
        'beta_rank_window':300,'beta_minimum_count':270,'strict_thresholds':[.8,.2],
        'factor_history':'Each selected expiry/strike own OHLC and own-volume history on common clock. Lag0/5 already applied within that fixed contract BEFORE selection; never shift selected factors again.',
        'rank_history':'Raw underlying return multiplied by already lagged fixed factor. Continuous near rank stitches current near expiries. Expiry near rank retains separate expiry paths including next-expiry warmup, then selects near.',
        'join_policy':'Exact minute/expiry/opening ATM strike only; unknown quotes/factors/clock slots retained without fill.',
        'calendar_policy':'Closed-market zero-return alpha is an explicit assumption, not observed data or a fitted calendar gate. Unknown regular-session returns remain unknown.',
        'source_diagnostics':'Both source coverage tables are labels, never feature inputs. Necessary alignment is not actual execution matching.',
        'archive_policy':'Only final12 NPZ archives; transient leaders bounded in memory.',
        'causality':'Completed historical candles and fixed-contract lagged factors only; no source-state resets or future values in features.',
        'limits':'Conditional fit screening needs independent autonomous replay. Original observed alpha failures remain independent AND prerequisites. Later periods previously inspected.'},indent=2))
    print(json.dumps({'pairs':len(records),'frontier':[(c['candidate_id'],c['objective']) for c in frontier[:4]]},indent=2),flush=True)


def selected_fixed_raw_ranks(panel, index, column):
    """Rank already lagged own-contract raw values AFTER opening-ATM selection.

    continuous_near stitches current near expiries before ranking. expiry_near
    retains each expiry's selected-ATM path (including next-expiry warmup), ranks
    independently on observed decision minutes, then chooses the current near.
    """
    if index.has_duplicates or not index.is_monotonic_increasing:
        raise ValueError('Decision clock must be unique and ordered')
    p=panel[['minute','expiry',column]].copy()
    p.minute=pd.to_datetime(p.minute,utc=True).dt.tz_convert(IST)
    p.expiry=pd.to_datetime(p.expiry).dt.date
    if p.duplicated(['minute','expiry']).any():raise ValueError('Duplicate selected raw expiry/minute')
    p=p.sort_values(['expiry','minute'])
    mapping={day:expiries_for(day)[0] for day in set(index.date)}
    keep=np.array([expiry==mapping.get(minute.date()) for expiry,minute in zip(p.expiry,p.minute)])
    near=p.loc[keep].set_index('minute')[column].reindex(index)
    if near.index.has_duplicates:raise ValueError('Duplicate selected near raw minutes')
    continuous=near.rolling(300,min_periods=270).rank(pct=True)
    ranked=pd.Series(np.nan,index=p.index,dtype=float)
    for _,group in p.groupby('expiry',sort=False):
        values=group.set_index('minute')[column]
        clock=index[(index>=values.index[0])&(index<=values.index[-1])]
        rank=values.reindex(clock).rolling(300,min_periods=270).rank(pct=True)
        ranked.loc[group.index]=rank.reindex(values.index).to_numpy()
    p['rank']=ranked
    per_expiry=p.loc[keep].set_index('minute')['rank'].reindex(index)
    return {'continuous_near':continuous,'expiry_near':per_expiry}


def opening_fixed_selected_raw_screen(volatility='adjacent_log_return'):
    return opening_fixed_rank_screen(volatility,selected_raw=True)


def opening_fixed_rank_screen(volatility='adjacent_log_return',selected_raw=False):
    """Pair exact-contract alpha2 ranks with corresponding causal alpha1."""
    from backtest.provider_fixed_factors import fixed_rank_variant_paths,FIXED_RANK_TAGS,FIXED_RANK_DESCRIPTIONS
    from backtest.provider_price_bounds import calendar_support_rank
    cache, _, preparation_design = fixed_rank_variant_paths(volatility)
    suffix='' if volatility=='adjacent_log_return' else '_'+volatility
    family=f'opening_fixed_selected_raw_{volatility}' if selected_raw else f'opening_fixed_rank{suffix}'
    directory = OUTPUT/'replication_trials'/family; directory.mkdir(exist_ok=True)
    tag=FIXED_RANK_TAGS[volatility]
    volatility_recipe={'adjacent_log_return':'fixed_log_return',
        'observed_log_return':'fixed_observed_log_return','price_std':'fixed_price_std',
        'adjacent_five_minute_log_return':'fixed_adjacent_five_minute_log_return',
        'adjacent_log_rms':'fixed_adjacent_log_rms'}[volatility]
    main_directory = OUTPUT/'replication_trials'
    bars, _, _ = context(); bank = load_alpha(main_directory); scorer = Scorer(bars.index)
    recipes = json.loads((main_directory/'alpha_recipes.json').read_text())
    panel = pd.read_csv(cache)
    panel.minute = pd.to_datetime(panel.minute, utc=True).dt.tz_convert(IST)
    mapping = {day: str(expiries_for(day)[0]) for day in set(bars.index.date)}
    keep = np.array([expiry == mapping[minute.date()] for expiry, minute in zip(panel.expiry, panel.minute)])
    selected = panel.loc[keep].set_index('minute')
    if selected.index.has_duplicates:
        raise ValueError('Duplicate selected exact-contract rank minutes')
    selected = selected.reindex(bars.index)
    records = []; frontier = []; coverage = {}; selected_inputs={}
    for kind in ('close_old_open', 'close_close_old_open'):
        name = f'{kind}_h5_r800'; alpha_recipe = recipes[name]
        raw = price_change_series(bars, alpha_recipe)
        np.testing.assert_array_equal(rank(raw, 800, 1.).to_numpy(), bank[name].to_numpy())
        supports = {'trading_observations': bank[name],
                    'calendar_closed_zero_returns': calendar_support_rank(raw, closed_zero=True)}
        for baseline in (10, 15, 20):
            for window in (150, 300):
                for lag in (0, 5):
                    column = f'{"raw" if selected_raw else "rank"}_{kind}_h5_native_v1_b{baseline}_{tag}{window}_lag{lag}'
                    betas=selected_fixed_raw_ranks(panel,bars.index,column) if selected_raw else {'exact_contract_rank_before_atm_selection':selected[column]}
                    for beta_context,beta in betas.items():
                      coverage[f'{beta_context}:{column}' if selected_raw else column] = int(beta.iloc[scorer.entries].notna().sum())
                      for support, alpha in supports.items():
                        metrics, _ = scorer.score(alpha, beta)
                        recipe = {'context': 'exact_contract_rank_before_atm_selection',
                            'volume_kind': 'native', 'volume_short': 1, 'volume_baseline': baseline,
                            'volatility': f'{volatility_recipe}_{window}', 'factor_lag': lag,
                            'rank_window': 300, 'price_change': 'same_as_alpha_v2',
                            'atm_reference': 'last_completed_bar_open', 'profit_target_mode': 'disabled',
                            'alpha_rank_support': support, 'beta_cache_column': column,
                            'input_policy': 'same-contract-raw-rank-before-selection;vol80;rank90;no-quote-fill'}
                        # Preserve every original recipe byte and candidate ID.
                        if volatility!='adjacent_log_return':recipe['fixed_rank_volatility']=volatility
                        if selected_raw:
                            recipe.update({'context':beta_context,'fixed_rank_volatility':volatility,
                                'beta_rank_order':'opening_atm_selected_raw_then_rank',
                                'beta_raw_cache_column':column,
                                'input_policy':'current-contract-factor-lag-before-opening-atm-selection;selected-raw-rank-after-selection;vol80;rank90;no-quote-fill'})
                        cid = hashlib.sha256(json.dumps({'alpha': name,
                            'recipe': recipe}, sort_keys=True).encode()).hexdigest()[:16]
                        candidate = {'candidate_id': cid, 'alpha': name+'_'+support,
                            'alpha_recipe': {**alpha_recipe, 'rank_support': support},
                            'recipe': recipe, 'metrics': metrics,
                            'objective': [metrics['fit_first_exact'], metrics['fit_direction_matches'],
                                          -metrics['fit_signal_episodes']]}
                        records.append(candidate)
                        if len(frontier) < 12 or tuple(candidate['objective']) > tuple(frontier[-1]['objective']):
                            if selected_raw:selected_inputs[cid]=(alpha.to_numpy(),beta.to_numpy())
                            else:
                                np.savez_compressed(directory/f'candidate_{cid}.npz',
                                    minutes=bars.index.as_unit('ns').asi8, alpha=alpha.to_numpy(), alpha2=beta.to_numpy())
                            frontier.append(candidate)
                            frontier.sort(key=lambda c: (tuple(c['objective']), c['candidate_id']), reverse=True)
                            frontier = frontier[:12]
                            if selected_raw:
                                selected_inputs={c['candidate_id']:selected_inputs[c['candidate_id']] for c in frontier}
    if selected_raw:
        # Write only committed finalists; do not create transient unselected NPZs.
        for cid,(alpha,beta) in selected_inputs.items():
            np.savez_compressed(directory/f'candidate_{cid}.npz',
                minutes=bars.index.as_unit('ns').asi8,alpha=alpha,alpha2=beta)
    pd.DataFrame([{'candidate_id': c['candidate_id'], 'alpha': c['alpha'],
        'recipe': json.dumps(c['recipe'], sort_keys=True), **c['metrics']} for c in records]).to_csv(
            directory/'formula_trials.csv', index=False)
    (directory/'frontier.json').write_text(json.dumps(frontier, indent=2))
    (directory/'search_design.json').write_text(json.dumps({'pairs': len(records),
        'source_rank_coverage': coverage, 'source': str(cache),
        'volatility_kind':volatility,'preparation_design':str(preparation_design),
        'volatility_interpretation':FIXED_RANK_DESCRIPTIONS[volatility],
        'current_quote_policy':'Original adjacent mode retained. Alternative factor modes require known current CE and PE prices at the factor observation; lag5 uses that past factor.',
        'missing_data':'Absent contract rows, quotes and unavailable rolling ranks remain NaN. Source coverage counts finite ranks, not passing triggers; missing coverage cannot falsify a formula with better input data.',
        'rank_history': ('Raw alpha2 uses current selected contract own-history factors and lag0/5 before selection. Rank300 applied AFTER opening ATM selection; continuous_near crosses expiry changes; expiry_near uses separate expiry histories including next-expiry warmup before choosing near.' if selected_raw else 'Raw alpha2 and rank300 calculated independently for each expiry/strike BEFORE opening ATM selection.'),
        'novelty_control':('Adjacent mode lag0 may duplicate previous opening_fixed signals; no novelty claim without signal comparison. Lag5 differs from shifting the previously selected ATM factor because it uses the current selected contract own history.' if selected_raw else None),
        'alpha1_supports': ['Original800 observed-return rank', 'Explicit800 calendar slots with assumed zero closed-market returns'],
        'selection': 'Fit conditional first-exact, then direction matches and fewer episodes.',
        'limits': 'Calendar alpha1 is an assumption previously rejected with stitched beta; it is not observed closed-market data. Unknown regular-session returns and all option quotes remain unknown. Missing fixed-contract rank coverage cannot rule out a formula on better data. Autonomous replay required; later periods already inspected.'}, indent=2))
    print('Exact-contract rank frontier', [(c['candidate_id'], c['objective']) for c in frontier[:4]], flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--family',choices=('main','fine','expanded','mixed','fixed_contract','sampling','boundaries','rank_conventions','eligibility','opening_atm','opening_volume','opening_pcr','contract_cumulative','crossings','bulk','implied_volatility_opening_complete','opening_ohlc_volatility','opening_fixed_ohlc','weighted_volatility','opening_fixed_rank','opening_fixed_rank_observed_log_return','opening_fixed_rank_price_std','opening_fixed_rank_adjacent_five_minute_log_return','opening_fixed_rank_adjacent_log_rms','opening_fixed_selected_raw_adjacent_log_return','opening_fixed_selected_raw_observed_log_return','opening_fixed_selected_raw_price_std','opening_fixed_selected_raw_adjacent_five_minute_log_return','opening_fixed_selected_raw_adjacent_log_rms'),default=None,
        help='select a saved bank; sampling/boundaries are generated by provider_price_bounds, eligibility by --premium-gates')
    parser.add_argument('--alpha-only',action='store_true')
    parser.add_argument('--iv-screen',action='store_true',help='separate exact-contract implied-volatility hypothesis screen')
    parser.add_argument('--iv-opening-full-screen',action='store_true',help='separate full opening-contract IV630-pair screen')
    parser.add_argument('--opening-ohlc-screen',action='store_true',help='separate completed opening-option OHLC1134-pair screen')
    parser.add_argument('--volatility-definition-screen',action='store_true',help='Matched64-pair finite volatility-definition experiment')
    parser.add_argument('--weighted-alpha-volatility-screen',action='store_true',help='32 volatility-definition pairs with the fit-selected weighted alpha800')
    parser.add_argument('--weighted-volatility-screen',action='store_true',help='offline matched weighted STD150 experiment and exact uniform control')
    parser.add_argument('--opening-fixed-ohlc-screen',action='store_true',help='separate own-contract OHLC factor864-pair screen')
    parser.add_argument('--opening-fixed-screen',action='store_true',help='separate opening-selected own-strike factor screen')
    parser.add_argument('--opening-fixed-rank-screen',action='store_true',help='screen alpha2 ranked within each exact contract before ATM selection')
    parser.add_argument('--opening-fixed-selected-raw-screen',action='store_true',help='rank cached own-contract raw alpha2 after opening ATM selection')
    parser.add_argument('--fixed-rank-volatility',choices=('adjacent_log_return','observed_log_return','price_std','adjacent_five_minute_log_return','adjacent_log_rms'),default=None,
        help='volatility convention for --opening-fixed-rank-screen; default adjacent_log_return')
    parser.add_argument('--shard',type=int,choices=range(16),help='independent bulk grid shard, 0 through 15')
    parser.add_argument('--benchmark-cache',action='store_true',help='benchmark exact cached rolling-volume calculations on the real historical panels')
    parser.add_argument('--premium-gates',action='store_true',help='separate finite premium eligibility screen on saved fit leaders')
    parser.add_argument('--atm-control',help='create a matched close-selected ATM control for this saved opening_atm candidate')
    parser.add_argument('--volume-control',help='create a matched arithmetic-volume control for this saved opening_volume candidate')
    parser.add_argument('--limit',type=int,default=0,help='new formula recipes in this batch; zero scans remaining bank')
    parser.add_argument('--replay-top',type=int,default=0,help='autonomously replay this many fit-selected candidates on the recent week')
    parser.add_argument('--candidate',help='replay this saved candidate ID; requires --replay-top')
    parser.add_argument('--expanded',action='store_true',help='additional explicit volume-ratio definitions and current-opening alpha candidates')
    parser.add_argument('--fine',action='store_true',help='separate neighboring-window and factor-lag search around the fit-selected native-volume recipe')
    parser.add_argument('--contexts',nargs='+',choices=('continuous_near','expiry_near','continuous_next','expiry_next'),help='limit a resumable batch to selected option-history contexts')
    parser.add_argument('--mixed',action='store_true',help='separate trial: alpha2 uses five-bar close-to-close return while alpha may use an opening reference')
    parser.add_argument('--fixed-contract',action='store_true',help='separate rolling-ATM versus fixed-contract factor comparison; prepare provider_fixed_factors first')
    args=parser.parse_args()
    if args.weighted_alpha_volatility_screen:
        if any(value for key,value in vars(args).items() if key!='weighted_alpha_volatility_screen'):
            parser.error('--weighted-alpha-volatility-screen is a separate experiment')
        volatility_definition_screen(weighted_alpha=True);return
    if args.volatility_definition_screen:
        if any(value for key,value in vars(args).items() if key != 'volatility_definition_screen'):
            parser.error('--volatility-definition-screen is a separate experiment')
        volatility_definition_screen();return
    if args.fixed_rank_volatility is not None and not (args.opening_fixed_rank_screen or args.opening_fixed_selected_raw_screen):
        parser.error('--fixed-rank-volatility requires a fixed-rank screen flag')
    if args.opening_fixed_selected_raw_screen:
        if any(value for key,value in vars(args).items() if key not in ('opening_fixed_selected_raw_screen','fixed_rank_volatility')):
            parser.error('--opening-fixed-selected-raw-screen is a separate diagnostic without other flags')
        opening_fixed_selected_raw_screen(args.fixed_rank_volatility or 'adjacent_log_return');return
    if args.opening_fixed_rank_screen:
        if any(value for key, value in vars(args).items() if key not in ('opening_fixed_rank_screen','fixed_rank_volatility')):
            parser.error('--opening-fixed-rank-screen is a separate diagnostic without other flags')
        opening_fixed_rank_screen(args.fixed_rank_volatility or 'adjacent_log_return');return
    if args.opening_fixed_screen:
        if any(value for key, value in vars(args).items() if key != 'opening_fixed_screen'):
            parser.error('--opening-fixed-screen is a separate diagnostic without other flags')
        opening_fixed_factor_screen();return
    if args.iv_screen:
        if any(value for key, value in vars(args).items() if key != 'iv_screen'):
            parser.error('--iv-screen is a separate diagnostic without other flags')
        implied_volatility_screen();return
    if args.iv_opening_full_screen:
        if any(value for key,value in vars(args).items() if key != 'iv_opening_full_screen'):
            parser.error('--iv-opening-full-screen is a separate diagnostic without other flags')
        implied_volatility_screen(opening_complete=True);return
    if args.opening_ohlc_screen:
        if any(value for key,value in vars(args).items() if key != 'opening_ohlc_screen'):
            parser.error('--opening-ohlc-screen is a separate diagnostic without other flags')
        opening_ohlc_screen();return
    if args.weighted_volatility_screen:
        if any(value for key,value in vars(args).items() if key != 'weighted_volatility_screen'):
            parser.error('--weighted-volatility-screen is a separate diagnostic without other flags')
        weighted_volatility_screen();return
    if args.opening_fixed_ohlc_screen:
        if any(value for key,value in vars(args).items() if key != 'opening_fixed_ohlc_screen'):
            parser.error('--opening-fixed-ohlc-screen is a separate diagnostic without other flags')
        opening_fixed_ohlc_screen();return
    if args.limit<0:parser.error('--limit must be nonnegative')
    if args.shard is not None and args.family!='bulk':parser.error('--shard requires --family bulk')
    if args.family=='bulk' and not args.replay_top and args.shard is None:parser.error('Bulk scanning requires --shard')
    if args.family=='bulk' and any((args.contexts,args.alpha_only,args.premium_gates,args.atm_control,args.volume_control,args.fine,args.expanded,args.mixed,args.fixed_contract,args.benchmark_cache)):
        parser.error('Bulk grid parameters are fixed; select only --shard and --limit')
    if args.replay_top and args.shard is not None:parser.error('Replay merged bulk finalists without --shard')
    if args.benchmark_cache:
        if any((args.family,args.replay_top,args.candidate,args.limit,args.alpha_only,args.premium_gates,args.atm_control,args.volume_control,args.fine,args.expanded,args.mixed,args.fixed_contract,args.contexts)):
            parser.error('--benchmark-cache is a separate diagnostic')
        benchmark_rolling_cache();return
    if args.atm_control or args.volume_control:
        if (args.atm_control and args.volume_control) or args.family not in (None,'opening_atm','opening_volume','opening_pcr','contract_cumulative') or any((args.replay_top,args.candidate,args.premium_gates,args.alpha_only,args.fine,args.expanded,args.mixed,args.fixed_contract)):
            parser.error('Choose one matched control without replay/search flags')
        family=args.family or ('opening_volume' if args.volume_control else 'opening_atm')
        prepare_atm_control(args.volume_control or args.atm_control,family,bool(args.volume_control));return
    if args.premium_gates:
        if args.replay_top or args.candidate or args.alpha_only or args.family not in (None,'eligibility') or any((args.fine,args.expanded,args.mixed,args.fixed_contract)):
            parser.error('--premium-gates generates its own eligibility bank; replay it separately')
        premium_screen();return
    if args.candidate and not args.replay_top:parser.error('--candidate requires --replay-top')
    legacy=[name for name,enabled in (('fine',args.fine),('expanded',args.expanded),('mixed',args.mixed),('fixed_contract',args.fixed_contract)) if enabled]
    if len(legacy)>1 or (args.family is not None and legacy and args.family!=legacy[0]):
        parser.error('Choose one trial family per worker')
    family=args.family or (legacy[0] if legacy else 'main')
    if family in ('implied_volatility_opening_complete','opening_ohlc_volatility','opening_fixed_ohlc','weighted_volatility','sampling','boundaries','rank_conventions','eligibility','opening_fixed_rank','opening_fixed_rank_observed_log_return','opening_fixed_rank_price_std','opening_fixed_rank_adjacent_five_minute_log_return','opening_fixed_rank_adjacent_log_rms','opening_fixed_selected_raw_adjacent_log_return','opening_fixed_selected_raw_observed_log_return','opening_fixed_selected_raw_price_std','opening_fixed_selected_raw_adjacent_five_minute_log_return','opening_fixed_selected_raw_adjacent_log_rms') and not args.replay_top:
        parser.error('Generate fixed-rank banks with --opening-fixed-rank-screen, eligibility with --premium-gates, or sampling/boundaries with provider_price_bounds; use --replay-top here')
    if family!='main':
        global OUT
        import shutil
        source=OUT;OUT=source/family;OUT.mkdir(exist_ok=True)
        if family=='bulk' and args.shard is not None:
            OUT=OUT/f'shard_{args.shard:02d}';OUT.mkdir(exist_ok=True)
        # These families have their own saved candidate inputs.
        if family not in ('implied_volatility_opening_complete','opening_ohlc_volatility','opening_fixed_ohlc','weighted_volatility','sampling','boundaries','rank_conventions','eligibility','crossings','bulk','opening_fixed_rank','opening_fixed_rank_observed_log_return','opening_fixed_rank_price_std','opening_fixed_rank_adjacent_five_minute_log_return','opening_fixed_rank_adjacent_log_rms','opening_fixed_selected_raw_adjacent_log_return','opening_fixed_selected_raw_observed_log_return','opening_fixed_selected_raw_price_std','opening_fixed_selected_raw_adjacent_five_minute_log_return','opening_fixed_selected_raw_adjacent_log_rms'):
            for name in ('alpha_bank.npz','alpha_recipes.json','alpha_trials.csv'):
                shutil.copyfile(source/name,OUT/name)
    if args.replay_top:replay_frontier(args.replay_top,args.candidate)
    elif args.alpha_only:prepare_alpha()
    elif family=='crossings':entry_crossing_screen()
    else:scan(args.limit,family=='expanded',family in ('fine','mixed','opening_atm','opening_volume','opening_pcr','contract_cumulative'),args.contexts,family=='mixed',family=='fixed_contract',family in ('opening_atm','opening_volume','opening_pcr','contract_cumulative'),family=='opening_volume',family=='opening_pcr',family=='contract_cumulative',args.shard)


if __name__=='__main__':main()
