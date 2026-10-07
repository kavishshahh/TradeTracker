"""Discover entry-variable hypotheses against actual entries AND flat-market controls.

Read-only research. No clock, weekday, date, absolute index level, trade ID,
published P&L or future candle is a predictor. Formula and tree outputs are
hypotheses; they do not change trading defaults automatically.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from backtest.provider_research import BAR_CACHE, FEATURE_CACHE, ENTRY_QUOTE_CACHE, OUTPUT, provider_trades, split_name
from backtest.provider_calendar import expiries_for

OUT=OUTPUT/'triggers'
CACHE=FEATURE_CACHE.parent/'provider_trigger_variables.npz'
SPLITS=('fit','validation','evaluation','case_study')


def safe_ratio(a,b):
    return a/b.where(b.abs()>1e-12)


def rolling_rank(s,window):
    return s.rolling(window,min_periods=int(np.ceil(.9*window))).rank(pct=True)


def context():
    bars=pd.read_csv(BAR_CACHE,index_col=0)
    bars.index=pd.to_datetime(bars.index,utc=True).tz_convert('Asia/Kolkata')+pd.Timedelta(minutes=1)
    panels=pd.read_csv(FEATURE_CACHE)
    panels.minute=pd.to_datetime(panels.minute,utc=True).dt.tz_convert('Asia/Kolkata')
    mapping={d:expiries_for(d) for d in set(bars.index.date)}
    selected={}
    for number,name in ((0,'near'),(1,'next')):
        mask=np.array([e==str(mapping[t.date()][number]) for e,t in zip(panels.expiry,panels.minute)])
        selected[name]=panels.loc[mask].set_index('minute').reindex(bars.index)
    quotes=pd.read_csv(ENTRY_QUOTE_CACHE)
    quotes.index=pd.to_datetime(quotes.pop('minute'),utc=True).dt.tz_convert('Asia/Kolkata')
    return bars,selected,quotes.reindex(bars.index)


def build_variables(bars,panels):
    """Trailing windows only. Features describe either signed direction or unsigned strength."""
    features,definitions,kinds={},{},{}
    def add(name,series,formula,kind='signed'):
        features[name]=np.asarray(series.replace([np.inf,-np.inf],np.nan),dtype=np.float32)
        definitions[name]=formula
        kinds[name]=kind
    day=bars.index.date
    close=bars.close
    logret=np.log(close).diff()
    intraday_logret=logret.where(pd.Series(day,index=bars.index)==pd.Series(day,index=bars.index).shift())
    previous_close=close.groupby(day).last().shift()
    previous_close=pd.Series(previous_close.reindex(day).to_numpy(),index=bars.index)
    session_open=bars.open.groupby(day).transform('first')
    session_high=bars.high.groupby(day).cummax()
    session_low=bars.low.groupby(day).cummin()
    tr=pd.concat([bars.high-bars.low,(bars.high-close.shift()).abs(),(bars.low-close.shift()).abs()],axis=1).max(axis=1)
    changes={}
    for h in (1,2,3,5,10,15,30,60):
        for price in ('close','open'):
            series=bars[price].pct_change(h,fill_method=None)
            changes[(price,h)]=series
            add(f'{price}_return_{h}',series,f'{price}[t]/{price}[t-{h}]-1')
        add(f'body_{h}',safe_ratio(close-bars.open.shift(h-1),bars.open.shift(h-1)),f'(close[t]-open[t-{h-1}])/open[t-{h-1}]')
        add(f'acceleration_{h}',changes[('close',h)]-changes[('close',h)].shift(1),f'close_return_{h}[t]-close_return_{h}[t-1]')
    pc=(close-close.shift(5))/bars.open.shift(5)
    add('documented_price_change',pc,'(close[t]-close[t-5])/open[t-5]')
    for h in (3,5,10,15):
        for window in (60,150,300,800,1600):
            add(f'price_rank_h{h}_w{window}',rolling_rank(changes[('close',h)],window),f'trailing percentile rank(close_return_{h},{window})','rank')
    for w in (5,15,20,60,150,300,800):
        rv=logret.rolling(w,min_periods=int(np.ceil(.8*w))).std()
        add(f'spot_realized_vol_{w}',rv,f'std(log(close/previous close),{w})','unsigned')
        if w in (15,60,300,800):
            iv=intraday_logret.rolling(w,min_periods=int(np.ceil(.8*w))).std()
            add(f'spot_intraday_vol_{w}',iv,f'std(log(close/previous close),{w}), first candle of each session excluded','unsigned')
            add(f'normalized_move5_intraday_vol{w}',safe_ratio(pc,iv*np.sqrt(5)),f'documented_price_change/(spot_intraday_vol_{w}*sqrt(5))')
        add(f'atr_pct_{w}',safe_ratio(tr.rolling(w,min_periods=int(np.ceil(.8*w))).mean(),close),f'mean(true range,{w})/close','unsigned')
        add(f'normalized_move5_vol{w}',safe_ratio(pc,rv*np.sqrt(5)),f'documented_price_change/(spot_realized_vol_{w}*sqrt(5))')
        mean=close.rolling(w,min_periods=int(np.ceil(.8*w))).mean()
        std=close.rolling(w,min_periods=int(np.ceil(.8*w))).std()
        add(f'price_zscore_{w}',safe_ratio(close-mean,std),f'(close-mean(close,{w}))/std(close,{w})')
        high=bars.high.rolling(w,min_periods=int(np.ceil(.8*w))).max()
        low=bars.low.rolling(w,min_periods=int(np.ceil(.8*w))).min()
        add(f'stochastic_{w}',safe_ratio(close-low,high-low),f'(close-min(low,{w}))/(max(high,{w})-min(low,{w}))','rank')
        add(f'move5_range_{w}',safe_ratio(close-close.shift(5),high-low),f'(close-close[t-5])/(max(high,{w})-min(low,{w}))')
        if w in (5,15,60,300):
            up=close.diff().clip(lower=0).rolling(w,min_periods=w).mean()
            down=(-close.diff().clip(upper=0)).rolling(w,min_periods=w).mean()
            add(f'rsi_{w}',safe_ratio(up,up+down),f'mean(up move,{w})/(mean(up,{w})+mean(down,{w}))','rank')
    add('session_return',safe_ratio(close-session_open,session_open),'(close-session opening price)/session opening price')
    add('previous_close_return',safe_ratio(close-previous_close,previous_close),'(close-previous session close)/previous session close')
    add('session_range_position',safe_ratio(close-session_low,session_high-session_low),'(close-session low so far)/(session high so far-session low so far)','rank')
    add('candle_body_fraction',safe_ratio(close-bars.open,bars.high-bars.low),'(close-open)/(high-low)')
    add('candle_close_position',safe_ratio(close-bars.low,bars.high-bars.low),'(close-low)/(high-low)','rank')
    add('candle_range_pct',safe_ratio(bars.high-bars.low,close),'(high-low)/close','unsigned')
    for prefix,p in panels.items():
        ce,pe=p.ce_ltp,p.pe_ltp
        straddle=ce+pe
        parity=p.atm_strike+ce-pe
        add(f'{prefix}_option_price_imbalance',safe_ratio(ce-pe,straddle),'(CE-PE)/(CE+PE)')
        add(f'{prefix}_straddle_pct',safe_ratio(straddle,close),'(CE+PE)/NIFTY close','unsigned')
        add(f'{prefix}_parity_basis',safe_ratio(parity-close,close),'(strike+CE-PE-NIFTY close)/NIFTY close')
        add(f'{prefix}_iv_sum',p.ce_iv+p.pe_iv,'CE IV+PE IV','unsigned')
        add(f'{prefix}_iv_skew',safe_ratio(p.pe_iv-p.ce_iv,p.pe_iv+p.ce_iv),'(PE IV-CE IV)/(PE IV+CE IV)')
        add(f'{prefix}_oi_imbalance',safe_ratio(p.pe_oi-p.ce_oi,p.pe_oi+p.ce_oi),'(PE OI-CE OI)/(PE OI+CE OI)')
        add(f'{prefix}_volume_imbalance',safe_ratio(p.pe_native_volume-p.ce_native_volume,p.pe_native_volume+p.ce_native_volume),'(PE volume-CE volume)/(PE volume+CE volume)')
        for h in (1,3,5,10,15):
            add(f'{prefix}_parity_return_{h}',parity.pct_change(h,fill_method=None),f'(strike+CE-PE) pct change over {h} rows; continuous nearest/next expiry')
            add(f'{prefix}_straddle_return_{h}',straddle.pct_change(h,fill_method=None),f'(CE+PE) pct change over {h} rows','unsigned')
            add(f'{prefix}_return_difference_{h}',(p.ce_return-p.pe_return).rolling(h,min_periods=h).sum(),f'sum(CE same-contract return-PE same-contract return,{h})')
            same=(p.atm_strike==p.atm_strike.shift(h))&(p.expiry==p.expiry.shift(h))
            for side in ('ce','pe'):
                add(f'{prefix}_{side}_oi_change_{h}',p[f'{side}_oi'].pct_change(h,fill_method=None).where(same),f'{side} OI pct change({h}), only if same observed ATM strike/expiry at endpoints','unsigned')
            add(f'{prefix}_iv_skew_change_{h}',(p.pe_iv-p.ce_iv).diff(h),f'change(PE IV-CE IV,{h})')
        mults={}
        for short,base in ((1,300),(3,300),(5,300),(5,60),(5,20),(15,300),(20,300)):
            def ratio(v):
                return safe_ratio(v.rolling(short,min_periods=short).mean(),v.rolling(base,min_periods=int(np.ceil(.8*base))).mean())
            vr=(ratio(p.ce_native_volume)+ratio(p.pe_native_volume))/2
            name=f'{prefix}_volume_ratio_{short}_{base}'
            add(name,vr,f'mean(CE mean volume {short}/{base}, PE mean volume {short}/{base}), continuous {prefix} expiry','unsigned')
            if (short,base) in ((1,300),(5,300),(5,60)):
                mults[f'vr{short}_{base}']=vr
                mults[f'inverse_vr{short}_{base}']=safe_ratio(pd.Series(1.,index=bars.index),vr)
        cevol,pevol=p.ce_native_volume,p.pe_native_volume
        mults['symmetric_pcr']=(safe_ratio(cevol,pevol)+safe_ratio(pevol,cevol))/2
        mults['volume_sum_ratio']=safe_ratio((cevol+pevol).rolling(5).mean(),(cevol+pevol).rolling(300,min_periods=240).mean())
        for name,series in mults.items():
            if name not in ('vr1_300','vr5_300','vr5_60'):
                add(f'{prefix}_{name}',series,f'continuous {prefix} volume multiplier {name}','unsigned')
        vols={}
        for w in (20,60,300):
            for mode in ('same_contract','overnight','rolling_atm','price_level'):
                if mode=='same_contract':
                    c,r=p.ce_return,p.pe_return
                elif mode=='overnight':
                    c,r=p.ce_return_with_overnight,p.pe_return_with_overnight
                elif mode=='rolling_atm':
                    c,r=ce.pct_change(fill_method=None),pe.pct_change(fill_method=None)
                else:
                    c,r=ce,pe
                v=c.rolling(w,min_periods=int(np.ceil(.8*w))).std()+r.rolling(w,min_periods=int(np.ceil(.8*w))).std()
                add(f'{prefix}_{mode}_vol{w}',v,f'CE std+PE std over {w} continuous {prefix} rows; mode={mode}','unsigned')
                if w==300 or (w==60 and mode=='same_contract'):
                    vols[f'{mode}{w}']=v
        vols['iv_sum']=p.ce_iv+p.pe_iv
        vols['spot_vol300']=logret.rolling(300,min_periods=240).std()
        # Candidate alpha2 formula bank: explicit variations of the public formula.
        # Rank itself is computed AFTER selecting the nearest expiry at each time.
        for mname,m in mults.items():
            for vname,v in vols.items():
                raw=safe_ratio(pc*m,v)
                add(f'{prefix}_raw2_{mname}_{vname}',raw,f'documented_price_change*{mname}/{vname}, continuous {prefix} expiry')
                for w in (300,600):
                    name=f'{prefix}_alpha2_{mname}_{vname}_r{w}'
                    add(name,rolling_rank(raw,w),f'trailing percentile rank({prefix}_raw2_{mname}_{vname},{w})','rank')
        print(f'Built {prefix} variables; total={len(features)}',flush=True)
    frame=pd.DataFrame(features,index=bars.index)
    return frame,definitions,kinds


def prepare():
    OUT.mkdir(parents=True,exist_ok=True)
    bars,panels,_=context()
    frame,definitions,kinds=build_variables(bars,panels)
    np.savez_compressed(CACHE,minutes=frame.index.as_unit('ns').asi8,names=np.asarray(frame.columns,dtype=str),values=frame.to_numpy(dtype=np.float32))
    (OUT/'variable_definitions.json').write_text(json.dumps({'definitions':definitions,'kinds':kinds,
        'causality':'minute m uses only completed candles beginning at or before m-1; rolling windows include current completed candle',
        'predictors_excluded':['clock time','weekday','date','signal id','reported fills','future candles','realized P&L'],
        'discovery_status':'expanded hypotheses designed after previous full-ledger inspection; chronological checks are not an untouched holdout'},indent=2))
    trades=provider_trades()
    events=frame.reindex(trades.entry_minute).reset_index(names='minute')
    events.insert(0,'signal_id',trades.signal_id.to_numpy())
    events.insert(1,'direction',trades.direction.to_numpy())
    events.to_csv(OUT/'every_trade_variables.csv',index=False)
    print(f'Saved {len(frame):,} rows x {len(frame.columns)} variables',flush=True)


def load_variables():
    meta=json.loads((OUT/'variable_definitions.json').read_text())
    with np.load(CACHE,allow_pickle=False) as data:
        stamps=data['minutes']
        unit='us' if stamps.max()<10**17 else 'ns'
        idx=pd.to_datetime(stamps,unit=unit,utc=True).tz_convert('Asia/Kolkata')
        frame=pd.DataFrame(data['values'],columns=list(meta['definitions']),index=idx)
    return frame,meta


def samples(frame):
    """Two directional hypotheses at each eligible minute, with actual entries as labels."""
    trades=provider_trades();idx=frame.index
    eligible=(idx>=trades.entry_minute.min())&((idx.hour*60+idx.minute>=615)&(idx.hour*60+idx.minute<=855))
    flat=np.ones(len(idx),dtype=bool)
    for t in trades.itertuples():
        flat[(idx>t.entry_minute)&(idx<=t.exit_minute)]=False
    positions=idx.get_indexer(trades.entry_minute)
    if (positions<0).any():
        raise ValueError('Actual entry timestamps missing from feature cache')
    allowed=eligible&flat
    allowed[positions]=True
    minutes=np.flatnonzero(allowed)
    rows=np.repeat(minutes,2)
    directions=np.tile([1,-1],len(minutes))
    targets=np.zeros(len(rows),dtype=np.int8)
    lookup={(int(row),int(direction)):i for i,(row,direction) in enumerate(zip(rows,directions))}
    for pos,d in zip(positions,trades.direction):
        targets[lookup[(int(pos),int(d))]]=1
    splits=np.array([split_name(t.date()) for t in idx[rows]])
    return trades,rows,directions,targets,splits,eligible,flat


def directional_matrix(frame,meta,rows,directions):
    values=frame.to_numpy(dtype=np.float32)[rows].copy()
    for j,name in enumerate(frame.columns):
        kind=meta['kinds'][name]
        if kind=='signed':
            values[:,j]*=directions
        elif kind=='rank':
            values[:,j]=np.where(directions==1,values[:,j],1-values[:,j])
    return values


def auc_score(x,y):
    valid=np.isfinite(x);n1=int(y[valid].sum());n0=int(valid.sum()-n1)
    if n1<1 or n0<1:return np.nan
    r=pd.Series(x[valid]).rank(method='average').to_numpy()
    return float((r[y[valid]==1].sum()-n1*(n1+1)/2)/(n1*n0))


def score_predictions(prediction,targets,splits):
    result={}
    for split in SPLITS:
        m=splits==split;y=targets[m];p=prediction[m]
        tp=int((p&(y==1)).sum());fp=int((p&(y==0)).sum());n=int(y.sum())
        result.update({f'{split}_trades':n,f'{split}_captured':tp,f'{split}_extra_signal_minutes':fp,
                       f'{split}_precision':tp/(tp+fp) if tp+fp else 0.,f'{split}_recall':tp/n if n else 0.})
    return result


def screen():
    frame,meta=load_variables()
    trades,rows,directions,y,splits,eligible,flat=samples(frame)
    x=directional_matrix(frame,meta,rows,directions)
    fit=splits=='fit';results=[]
    for j,name in enumerate(frame.columns):
        vals=x[fit,j];labels=y[fit];valid=np.isfinite(vals)
        count=int(((labels==1)&valid).sum())
        if count<.8*int(labels.sum()):continue
        auc=auc_score(vals,labels)
        if not np.isfinite(auc):continue
        orient=1 if auc>=.5 else -1
        oriented=vals*orient
        thresholds=np.unique(np.nanquantile(oriented[labels==1],np.linspace(.05,.8,16)))
        best=None
        for threshold in thresholds:
            p=oriented>=threshold
            recall=(p&(labels==1)).sum()/max(1,labels.sum())
            false=(p&(labels==0)).sum()/max(1,(labels==0).sum())
            objective=recall-false
            if best is None or objective>best[0]:best=(objective,float(threshold),float(recall),float(false))
        pred=(x[:,j]*orient)>=best[1]
        row={'variable':name,'fit_auc':auc,'direction_transform':meta['kinds'][name],
             'condition':'>=' if orient==1 else '<=','threshold':best[1]*orient,
             'fit_positive_available':count,'fit_balanced_score':best[0],**score_predictions(pred,y,splits)}
        results.append(row)
    table=pd.DataFrame(results).sort_values('fit_balanced_score',ascending=False)
    table.to_csv(OUT/'single_variable_conditions.csv',index=False)
    # Explicit alpha/alpha2 trigger pairs using the documented percentile cutoffs.
    price_names=[n for n in frame if n.startswith('price_rank_h5_')]
    second_names=[n for n in frame if '_alpha2_' in n]
    formulas=[]
    for aname in price_names:
        aj=frame.columns.get_loc(aname)
        for bname in second_names:
            bj=frame.columns.get_loc(bname)
            pred=(x[:,aj]>.8)&(x[:,bj]>.8)
            formulas.append({'alpha':aname,'alpha2':bname,'cutoff':.8,**score_predictions(pred,y,splits)})
    pd.DataFrame(formulas).to_csv(OUT/'alpha_pairs.csv',index=False)
    print(f'Flat controls: {int((y==0).sum()):,}; entries: {int(y.sum())}; screened {len(table)} variables and {len(formulas)} alpha pairs',flush=True)
    print(table[['variable','condition','threshold','fit_captured','fit_extra_signal_minutes','validation_captured','validation_extra_signal_minutes','evaluation_captured','evaluation_extra_signal_minutes']].head(10).to_string(index=False),flush=True)
    fit_tree(frame,meta,x,y,splits,rows,directions,table)
    nearby_analysis(frame,meta,trades,rows,directions,y,splits,eligible,flat,table)


def nearby_analysis(frame,meta,trades,rows,directions,y,splits,eligible,flat,table):
    """Match each entry to its own preceding eligible flat minutes, same direction.

    No future or held-position minute is a negative. Windows with no preceding
    eligible minute remain in the full screen but cannot enter the paired screen.
    """
    positive_rows=[];negative_rows=[];negative_directions=[];negative_trade=[]
    matched_trades=[];events=[]
    for i,t in enumerate(trades.itertuples()):
        pos=frame.index.get_loc(t.entry_minute)
        controls=[]
        for lag in range(1,11):
            minute=t.entry_minute-pd.Timedelta(minutes=lag)
            c=frame.index.get_indexer([minute])[0]
            if c<0 or not eligible[c] or not flat[c]:continue
            if ((trades.entry_minute==minute)&(trades.direction==t.direction)).any():continue
            controls.append(c)
        if controls:
            matched_trades.append(i);positive_rows.append(pos)
            for c in controls:
                negative_rows.append(c);negative_directions.append(t.direction);negative_trade.append(i)
        for lag in (0,1,2,3,5,10):
            minute=t.entry_minute-pd.Timedelta(minutes=lag)
            c=frame.index.get_indexer([minute])[0]
            if c<0:continue
            events.append({'signal_id':t.signal_id,'entry_minute':str(t.entry_minute),'lag_minutes':lag,
                'minute':str(minute),'direction':t.direction,'eligible_flat_control':bool(lag and eligible[c] and flat[c]),
                **frame.iloc[c].to_dict()})
    pd.DataFrame(events).to_csv(OUT/'entry_and_preceding_minutes.csv',index=False)
    dirs=trades.direction.to_numpy()[matched_trades]
    p=directional_matrix(frame,meta,np.array(positive_rows),dirs)
    n=directional_matrix(frame,meta,np.array(negative_rows),np.array(negative_directions))
    ps=trades['split'].to_numpy()[matched_trades]
    ns=trades['split'].to_numpy()[negative_trade]
    counts=pd.Series(negative_trade).value_counts()
    nw=np.array([1/counts[i] for i in negative_trade])
    fullx=directional_matrix(frame,meta,rows,directions)
    results=[]
    fitp=ps=='fit';fitn=ns=='fit'
    # Also test one- and three-minute changes of each causal variable, explicitly
    # separating levels from fresh changes that could trigger an entry.
    derived={}
    for lag in (0,1,3):
        if lag:
            changed=frame-frame.shift(lag)
            # Rank differences are signed changes, so orient them by direction.
            delta_meta={'kinds':{name:'signed' if meta['kinds'][name]=='rank' else meta['kinds'][name] for name in frame}}
            pp=directional_matrix(changed,delta_meta,np.array(positive_rows),dirs)
            nn=directional_matrix(changed,delta_meta,np.array(negative_rows),np.array(negative_directions))
            xx=directional_matrix(changed,delta_meta,rows,directions)
        else:pp,nn,xx=p,n,fullx
        for j,name in enumerate(frame.columns):
            pv,nv=pp[:,j],nn[:,j]
            if np.isfinite(pv[fitp]).sum()<.8*fitp.sum():continue
            # Weighted comparison: each trade contributes total weight one,
            # regardless of how many preceding flat minutes it supplies.
            comparisons=[]
            for value in pv[fitp]:
                if not np.isfinite(value):continue
                valid=fitn&np.isfinite(nv)
                comparisons.append(np.average((nv[valid]<value)+.5*(nv[valid]==value),weights=nw[valid]))
            if not comparisons:continue
            auc=float(np.mean(comparisons));orient=1 if auc>=.5 else -1
            thresholds=np.unique(np.nanquantile(pv[fitp]*orient,np.linspace(.05,.8,16)))
            best=None
            for threshold in thresholds:
                recall=((pv[fitp]*orient)>=threshold).mean()
                fp=np.average((nv[fitn]*orient)>=threshold,weights=nw[fitn])
                score=recall-fp
                if best is None or score>best[0]:best=(score,float(threshold))
            key=f'{name}__change{lag}' if lag else name
            pred=xx[:,j]*orient>=best[1]
            result={'variable':key,'base_variable':name,'change_minutes':lag,'condition':'>=' if orient==1 else '<=',
                'threshold':best[1]*orient,'fit_matched_auc':auc,'fit_matched_balanced_score':best[0],
                **score_predictions(pred,y,splits)}
            for split in SPLITS:
                mp,mn=ps==split,ns==split
                result[f'{split}_paired_entries']=int(mp.sum())
                result[f'{split}_paired_recall']=float(((pv[mp]*orient)>=best[1]).mean()) if mp.any() else None
                result[f'{split}_paired_control_rate']=float(np.average((nv[mn]*orient)>=best[1],weights=nw[mn])) if mn.any() else None
            results.append(result)
            derived[key]=(j,lag,orient,best[1])
        print(f'Paired screen finished changes={lag}',flush=True)
    ranked=pd.DataFrame(results).sort_values('fit_matched_balanced_score',ascending=False)
    ranked.to_csv(OUT/'nearby_variable_conditions.csv',index=False)
    # Pair independently fitted numeric conditions. Include trend, volume and
    # option-state clauses even when their standalone balanced score is lower.
    chosen=ranked.head(60).copy()
    complementary=['price_zscore_60','price_zscore_300','price_zscore_800','close_return_60',
        'session_return','previous_close_return','rsi_60','rsi_300','near_iv_skew','near_oi_imbalance',
        'near_volume_ratio_5_300','near_volume_imbalance','candle_body_fraction','candle_range_pct']
    chosen=pd.concat([chosen,ranked.loc[ranked.variable.isin(complementary)]]).drop_duplicates('variable')
    full_conditions=[];pos_conditions=[];neg_conditions=[]
    for condition in chosen.itertuples():
        name=condition.base_variable;lag=condition.change_minutes
        v=frame[name] if lag==0 else frame[name]-frame[name].shift(lag)
        kind=meta['kinds'][name]
        if lag and kind=='rank':kind='signed'
        def values(rr,dd):
            value=v.to_numpy()[rr]
            if kind=='signed':return value*dd
            if kind=='rank':return np.where(dd==1,value,1-value)
            return value
        def hit(value):
            return np.isfinite(value)&((value>=condition.threshold) if condition.condition=='>=' else (value<=condition.threshold))
        pos_conditions.append(hit(values(np.array(positive_rows),dirs)))
        neg_conditions.append(hit(values(np.array(negative_rows),np.array(negative_directions))))
        full_conditions.append(hit(values(rows,directions)))
    pairs=[];best_pair=None
    for a in range(len(chosen)):
        for b in range(a+1,len(chosen)):
            pp=pos_conditions[a]&pos_conditions[b];nn=neg_conditions[a]&neg_conditions[b]
            score=float(pp[fitp].mean()-np.average(nn[fitn],weights=nw[fitn]))
            pred=full_conditions[a]&full_conditions[b]
            record={'condition1':chosen.iloc[a].variable,'operator1':chosen.iloc[a].condition,'threshold1':chosen.iloc[a].threshold,
                'condition2':chosen.iloc[b].variable,'operator2':chosen.iloc[b].condition,'threshold2':chosen.iloc[b].threshold,
                'fit_matched_balanced_score':score,**score_predictions(pred,y,splits)}
            for s in SPLITS:
                mp,mn=ps==s,ns==s
                record[f'{s}_paired_recall']=float(pp[mp].mean()) if mp.any() else None
                record[f'{s}_paired_control_rate']=float(np.average(nn[mn],weights=nw[mn])) if mn.any() else None
            pairs.append(record)
            if best_pair is None or score>best_pair[0]:best_pair=(score,a,b)
    pd.DataFrame(pairs).sort_values('fit_matched_balanced_score',ascending=False).to_csv(OUT/'paired_combination_conditions.csv',index=False)
    _,a,b=best_pair
    clauses=chosen.iloc[[a,b]].to_dict('records')
    (OUT/'matched_combination.json').write_text(json.dumps({'clauses':clauses,'selection':'highest fit-period paired balanced score only'},indent=2))
    print(ranked[['variable','condition','threshold','fit_paired_recall','fit_paired_control_rate','validation_paired_recall','validation_paired_control_rate']].head(12).to_string(index=False),flush=True)
    (OUT/'matched_design.json').write_text(json.dumps({'matched_entries':len(matched_trades),
        'unmatched_entries':len(trades)-len(matched_trades),'controls':len(negative_rows),
        'control_definition':'same direction, preceding 1..10 minutes, provider flat, published entry window, no actual same-direction entry',
        'weight':'controls for each trade sum to one; each actual entry weight one',
        'source_note':'published overlapping and same-minute reentry records retained; exact minute labels cannot recover intra-minute signal sequencing'},indent=2))


def fit_tree(frame,meta,x,y,splits,rows,directions,table):
    """Small weighted CART tree implemented with NumPy; selection uses fit only."""
    fit=np.flatnonzero(splits=='fit')
    # At most 40 variables, selected solely on the fit period.
    chosen=table.variable.head(40).tolist()
    cols=[frame.columns.get_loc(n) for n in chosen]
    weights=np.where(y==1,1/max(1,int(y[fit].sum())),1/max(1,int((y[fit]==0).sum())))
    def impurity(indices):
        total=weights[indices].sum()
        p=weights[indices][y[indices]==1].sum()/total if total else 0
        return total*2*p*(1-p)
    def grow(indices,depth):
        positives=int(y[indices].sum());negatives=len(indices)-positives
        total=weights[indices].sum()
        rate=weights[indices][y[indices]==1].sum()/total if total else 0.
        node={'fit_entries':positives,'fit_controls':negatives,'balanced_probability':float(rate),
              'empirical_precision':positives/len(indices) if len(indices) else 0}
        if depth==0 or positives<8 or negatives<80:
            node['leaf']=True;return node
        parent=impurity(indices);best=None
        for col in cols:
            values=x[indices,col]
            valid=values[np.isfinite(values)]
            if len(valid)<.9*len(values):continue
            thresholds=np.unique(np.quantile(valid,np.linspace(.05,.95,19)))
            for threshold in thresholds:
                m=np.isfinite(values)&(values<=threshold)
                left,right=indices[m],indices[~m]
                if min(len(left),len(right))<50:continue
                gain=parent-impurity(left)-impurity(right)
                if best is None or gain>best[0]:best=(gain,col,float(threshold),left,right)
        if best is None or best[0]<.002:
            node['leaf']=True;return node
        _,col,threshold,left,right=best
        node.update({'leaf':False,'variable':frame.columns[col],'threshold':threshold,
                     'missing_to':'right','left':grow(left,depth-1),'right':grow(right,depth-1)})
        return node
    def predict(node,indices,out):
        if node['leaf']:
            out[indices]=node['balanced_probability'];return
        col=frame.columns.get_loc(node['variable']);v=x[indices,col]
        m=np.isfinite(v)&(v<=node['threshold'])
        predict(node['left'],indices[m],out);predict(node['right'],indices[~m],out)
    rules=[]
    for depth in (2,3,4):
        tree=grow(fit,depth)
        probability=np.zeros(len(y));predict(tree,np.arange(len(y)),probability)
        (OUT/f'tree_depth{depth}.json').write_text(json.dumps({'tree':tree,'variables':chosen,
           'warning':'descriptive candidate, class-balanced probabilities are not calibrated trade probabilities; missing values take the right branch'},indent=2))
        for cutoff in (.5,.6,.7,.8):
            rules.append({'model':f'tree_depth{depth}','cutoff':cutoff,**score_predictions(probability>=cutoff,y,splits)})
        np.savez_compressed(OUT/f'tree_depth{depth}_predictions.npz',rows=rows,directions=directions,targets=y,probability=probability,splits=splits)
    pd.DataFrame(rules).to_csv(OUT/'combined_rules.csv',index=False)
    print(pd.DataFrame(rules).to_string(index=False),flush=True)


def report():
    frame,meta=load_variables()
    trades,rows,directions,y,splits,eligible,flat=samples(frame)
    x=directional_matrix(frame,meta,rows,directions)
    matched=pd.read_csv(OUT/'nearby_variable_conditions.csv')
    matched_move=matched.loc[matched.variable=='normalized_move5_vol60'].iloc[0]
    threshold=float(matched_move.threshold)
    normalized=frame.normalized_move5_vol60.to_numpy()
    baseline=pd.read_csv(OUTPUT/'baseline_minute_signals.csv.gz')
    baseline.index=pd.to_datetime(baseline.pop('minute'),utc=True).dt.tz_convert('Asia/Kolkata')
    baseline=baseline.reindex(frame.index)
    base=np.column_stack([((baseline.alpha>.8)&(baseline.alpha2>.8)).to_numpy(),
                          ((baseline.alpha<.2)&(baseline.alpha2<.2)).to_numpy()])
    ar=frame.price_rank_h5_w800.to_numpy()
    br=frame.next_alpha2_symmetric_pcr_iv_sum_r300.to_numpy()
    nr=frame.near_alpha2_vr5_300_same_contract300_r300.to_numpy()
    move=np.column_stack([normalized>=threshold,normalized<=-threshold])
    pair=np.column_stack([(ar>.8)&(br>.8),(ar<.2)&(br<.2)])
    continuous=np.column_stack([(ar>.8)&(nr>.8),(ar<.2)&(nr<.2)])
    models={'previous_baseline':base,'normalized_spot_move':move,
            'alpha800_next_pcr_iv_rank300':pair,'alpha800_continuous_near_documented':continuous,
            'normalized_spot_and_next_pcr_iv':move&pair}
    # The top overall flat-control condition is included as a separate hypothesis.
    single=pd.read_csv(OUT/'single_variable_conditions.csv').iloc[0]
    raw=frame[single.variable].to_numpy();cut=float(single.threshold)
    models['raw_inverse_volume_option_vol60']=np.column_stack([raw>=cut,raw<=-cut])
    if (OUT/'matched_combination.json').exists():
        compound=np.ones((len(frame),2),dtype=bool)
        for clause in json.loads((OUT/'matched_combination.json').read_text())['clauses']:
            v=frame[clause['base_variable']]
            lag=clause['change_minutes']
            if lag:v=v-v.shift(lag)
            kind=meta['kinds'][clause['base_variable']]
            if lag and kind=='rank':kind='signed'
            for col,d in ((0,1),(1,-1)):
                value=v.to_numpy()
                if kind=='signed':value=value*d
                elif kind=='rank' and d==-1:value=1-value
                compound[:,col]&=np.isfinite(value)&((value>=clause['threshold']) if clause['condition']=='>=' else (value<=clause['threshold']))
        models['fit_selected_matched_combination']=compound
    if 'normalized_move5_intraday_vol60' in frame:
        intraday=matched.loc[matched.variable=='normalized_move5_intraday_vol60'].iloc[0]
        v=frame.normalized_move5_intraday_vol60.to_numpy(); c=float(intraday.threshold)
        models['normalized_spot_excluding_overnight']=np.column_stack([v>=c,v<=-c])
    quotes=pd.read_csv(ENTRY_QUOTE_CACHE)
    quotes.index=pd.to_datetime(quotes.pop('minute'),utc=True).dt.tz_convert('Asia/Kolkata')
    quotes=quotes.reindex(frame.index)
    premium_gate=np.column_stack([(quotes.pe_ltp<=200).to_numpy(),(quotes.ce_ltp<=200).to_numpy()])
    for name,pred in list(models.items()):
        models[name+'_premium200']=pred&premium_gate
    stats=[];pertrade=[]
    for name,pred in models.items():
        prediction=pred[rows,(directions==-1).astype(int)]
        result={'model':name,**score_predictions(prediction,y,splits)}
        available=eligible&flat
        available[frame.index.get_indexer(trades.entry_minute)]=True
        for split in SPLITS:
            splitmask=np.array([split_name(t.date())==split for t in frame.index])
            episodes=0
            for col in (0,1):
                hit=available&splitmask&pred[:,col]
                contiguous=np.r_[False,(np.diff(frame.index.as_unit('ns').asi8)==60*10**9)]
                episodes+=int((hit&~(np.r_[False,hit[:-1]]&contiguous)).sum())
            result[f'{split}_signal_episodes']=episodes
        first_exact={s:0 for s in SPLITS};first_near={s:0 for s in SPLITS}
        for i,t in enumerate(trades.itertuples()):
            pos=frame.index.get_loc(t.entry_minute);col=0 if t.direction==1 else 1
            start=trades.iloc[i-1].exit_minute if i else trades.entry_minute.min()
            window=available&(frame.index>=start)&(frame.index<=t.entry_minute)
            hits=np.flatnonzero(window&pred.any(axis=1))
            first=hits[0] if len(hits) else None
            first_correct=bool(first is not None and pred[first,col])
            ambiguous=bool(i and start>=t.entry_minute)
            exact=bool(not ambiguous and first_correct and first==pos)
            near=bool(not ambiguous and first_correct and 0<=(t.entry_minute-frame.index[first]).total_seconds()<=120)
            first_exact[t.split]+=int(exact);first_near[t.split]+=int(near)
            controls=[]
            for lag in range(1,11):
                c=frame.index.get_indexer([t.entry_minute-pd.Timedelta(minutes=lag)])[0]
                if c>=0 and eligible[c] and flat[c]:controls.append(c)
            previous=frame.index.get_indexer([t.entry_minute-pd.Timedelta(minutes=1)])[0]
            pertrade.append({'signal_id':t.signal_id,'entry':str(t.entry),'direction':t.direction,'option_type':t.option_type,
                'split':t.split,'model':name,'condition_met_at_entry':bool(pred[pos,col]),
                'condition_met_previous_minute':bool(pred[previous,col]) if previous>=0 else None,
                'fresh_cross_at_entry':bool(pred[pos,col] and previous>=0 and not pred[previous,col]),
                'preceding_eligible_controls':len(controls),
                'preceding_controls_condition_met':int(pred[controls,col].sum()) if controls else 0,
                'first_signal_since_previous_published_exit':str(frame.index[first]) if first is not None else None,
                'first_signal_direction':int(1 if pred[first,0] else -1) if first is not None else None,
                'first_signal_matches_actual_entry':exact,
                'ambiguous_previous_exit_sequence':ambiguous,
                'documented_price_change':float(frame.documented_price_change.iloc[pos]),
                'normalized_move5_vol60':float(normalized[pos]),'price_rank800':float(ar[pos]),
                'next_pcr_iv_alpha2':float(br[pos]),'near_continuous_documented_alpha2':float(nr[pos]),
                'old_baseline_alpha':float(baseline.alpha.iloc[pos]),'old_baseline_alpha2':float(baseline.alpha2.iloc[pos]),
                'next_raw2_vr5_60_same_contract300':float(frame.next_raw2_vr5_60_same_contract300.iloc[pos]),
                'next_volume_ratio_5_60':float(frame.next_volume_ratio_5_60.iloc[pos]),
                'next_same_contract_vol300':float(frame.next_same_contract_vol300.iloc[pos]),
                'normalized_move5_intraday_vol60':float(frame.normalized_move5_intraday_vol60.iloc[pos]),
                'raw_inverse_volume_option_vol60':float(raw[pos])})
        for s in SPLITS:
            result[f'{s}_first_signal_exact']=first_exact[s]
            result[f'{s}_first_signal_within_2m']=first_near[s]
        stats.append(result)
    stats=pd.DataFrame(stats);pertrade=pd.DataFrame(pertrade)
    stats.to_csv(OUT/'trigger_rule_comparison.csv',index=False)
    pertrade.to_csv(OUT/'every_trade_trigger_diagnosis.csv',index=False)
    # All candidate values are retained; concise report distinguishes levels,
    # crossings, and first actionable signals rather than pretending direction
    # agreement alone recovers the entry rule.
    raw_result=stats.loc[stats.model=='raw_inverse_volume_option_vol60'].iloc[0]
    raw_capture=sum(int(raw_result[f'{s}_captured']) for s in SPLITS)
    raw_extra=sum(int(raw_result[f'{s}_extra_signal_minutes']) for s in SPLITS)
    lines=['# Entry trigger research', '',
      'Calculated from cached Dhan one-minute NIFTY and option data for all 210 published entries. '
      'Only completed candles are used. No clock, weekday, absolute index level, provider fills or P&L is a predictor.', '',
      '## Concrete candidate', '',
      f'Let R5 = (last completed close − close five bars earlier) / open five bars earlier. '
      f'Let V60 = standard deviation of one-bar NIFTY log returns over the last 60 observed bars, including the overnight return when it falls inside that window. '
      f'Z = R5 / (sqrt(5) × V60). Bullish condition: Z ≥ {threshold:.6f}; bearish: Z ≤ −{threshold:.6f}.', '',
      'This cutoff was chosen using the first 120 trades and their preceding flat minutes. '
      'The feature bank was designed after prior inspection of the complete ledger: the later periods are chronological '
      'checks, not a pristine unseen holdout. The threshold is a fitted hypothesis, not a known provider constant.', '',
      '## Entry agreement versus extra signals', '',
      '| Condition | At actual entry / 210 | First signal exact / 210 | Extra flat signal minutes | Signal episodes |',
      '|---|---:|---:|---:|---:|']
    for r in stats.to_dict('records'):
        captured=sum(r[f'{s}_captured'] for s in SPLITS)
        first=sum(r[f'{s}_first_signal_exact'] for s in SPLITS)
        extra=sum(r[f'{s}_extra_signal_minutes'] for s in SPLITS)
        episodes=sum(r[f'{s}_signal_episodes'] for s in SPLITS)
        lines.append(f"| {r['model']} | {captured} | {first} | {extra:,} | {episodes:,} |")
    lines+=['', 'Extra signal minutes are eligible flat observations (including wrong direction at an actual entry); '
      'episodes group consecutive same-direction minutes. Neither is an autonomous backtest trade count. '
      'The `_premium200` rows additionally require the previous completed quote of the open-selected short contract ≤200; missing quotes fail the gate. '
      'Three actual published fills are ≤200 although that prior quote is >200, so this candle-based gate can miss genuine fills. '
      'First signal checks begin after each previous published exit, so they remain conditional on provider position history. '
      'Exact matches exclude cases whose preceding exit is in the same minute as, or later than, the entry; those records remain in the entry-value counts.', '',
      '## Nearby comparisons', '',
      '175 entries have a preceding eligible flat control in the prior ten minutes; 870 controls. '
      'Each entry and its control set receive equal total weight. The other 35 entries remain in the full analysis. '
      f'The paired screen includes all base variables and one-/three-bar changes ({len(frame.columns)*3:,} hypotheses before availability filtering).', '',
      '| Split | Paired entries | Z condition at entry | Z condition in preceding flat controls |',
      '|---|---:|---:|---:|']
    top=matched_move
    for s in SPLITS:
        lines.append(f"| {s} | {int(top[f'{s}_paired_entries'])} | {top[f'{s}_paired_recall']:.1%} | {top[f'{s}_paired_control_rate']:.1%} |")
    lines+=['', '## Combined numeric criteria', '',
      'Tested 2,701 AND pairs of fitted numeric conditions, including price strength, trend, RSI, IV, OI and volume. '
      'The pair with the strongest fit-period separation between entries and their preceding controls requires BOTH:', '',
      f'1. Direction-adjusted Z ≥ {threshold:.6f}.',
      '2. Direction-adjusted [R5 × average CE/PE volume ratio (5/60) / summed CE/PE same-contract return volatility (300)] '
      'on continuous next-expiry ATM options ≥ 0.008168.', '',
      'Bullish trades use direction +1; bearish trades use −1. The raw second condition is not a percentile rank. '
      'This combination agrees with 144/210 entries, but its first eligible signal matches only 49/210. '
      'It still produces 4,206 extra flat signal minutes before applying the premium gate. '
      'The fit matched-entry rate is 72.3% versus 26.8% in preceding controls; later paired-control checks still fail to isolate the trigger. '
      'It is a concrete, falsifiable pair of criteria, not an established provider rule.', '']
    lines+=['', '## Alpha and alpha2 candidates', '',
      'Tested 1,120 explicit alpha/alpha2 pairs at directional 0.8/0.2 cutoffs. '
      'Alpha uses 5-bar price-return ranks over 60/150/300/800/1600 observations. Alpha2 variants cover '
      'native per-leg volume ratios, inverse volume ratios, symmetric put/call volume ratios, return or price-level option volatility, '
      'IV and spot volatility, ranks over 300/600 observations, and continuous nearest or next-expiry series.', '',
      'The strongest fit-period pair uses alpha = 800- or 1600-observation rank of NIFTY 5-bar return; '
      'alpha2 = 300-observation rank of [R5 × ((CE volume/PE volume + PE volume/CE volume)/2) / (CE IV + PE IV)] '
      'on next-expiry ATM options. The 800 variant agrees with 165/210 entry directions, but produces thousands of extra signal minutes. '
      'It does not identify the missing entry gate.', '',
      '## The two disputed trades', '',
      '| Date | Z at incorrect bullish entry 10:15 | Z at provider bearish entry | First bearish Z signal | Published entry |',
      '|---|---:|---:|---|---|',
      '| 2026-09-28 | +0.2720 | −1.3632 | 10:18 | 10:18 |',
      '| 2026-09-30 | +0.6387 | −1.6337 | 10:31 | 10:33 |', '',
      'Z rejects both erroneous bullish 10:15 entries and reproduces the Sep 28 entry minute. '
      'It fires two minutes early on Sep 30 and misses other provider entries. '
      'A shared trigger cannot be concluded from these two successful directional comparisons. '
      'Removing overnight returns makes Sep 28 10:15 Z = +0.8914, which passes the same bullish cutoff. '
      'Thus the rejection on Sep 28 depends on the overnight gap being inside the 60-bar volatility window; it is not a robust match.', '',
      '## Conclusion', '',
      'Evidence supports a short-term directional impulse with strength/volatility scaling. '
      'The expanded variables still do not isolate a condition that fires reliably at the actual entry and stays off before it. '
      f'The strongest single flat-control rule agrees with {raw_capture}/210 entries but has {raw_extra:,} extra signal minutes; '
      'its much higher entry recall does not recover the strategy. Shallow rule combinations also fail the negative controls. '
      'No new discovered condition has been installed as the production alpha or alpha2.', '',
      '## Files', '',
      f'- `every_trade_variables.csv`: {len(frame.columns)} market variables at every actual entry.',
      '- `entry_and_preceding_minutes.csv`: the same variables at entry and 1/2/3/5/10 minutes earlier, with eligible-control flags.',
      '- `every_trade_trigger_diagnosis.csv`: each trade, candidate and premium-gated rules, condition values, previous-minute state, fresh crossings and first signal.',
      '- `nearby_variable_conditions.csv`: fitted level/change thresholds and chronological paired-control results.',
      '- `paired_combination_conditions.csv`, `matched_combination.json`: numeric AND conditions, their paired-control results and the fit-selected pair.',
      '- `single_variable_conditions.csv`, `alpha_pairs.csv`, `combined_rules.csv`: complete candidate results.',
      '- `variable_definitions.json`: every formula and direction transform.', '',
      'Source quality: overlapping provider records, same-minute reentries and after-expiry records remain flagged in the main research report. '
      'One-minute data cannot resolve intra-minute decisions or prove a proprietary formula uniquely.']
    (OUT/'entry_trigger_report.md').write_text('\n'.join(lines),encoding='utf-8')
    print(stats[['model']+[f'{s}_captured' for s in SPLITS]+[f'{s}_first_signal_exact' for s in SPLITS]].to_string(index=False),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare',action='store_true')
    parser.add_argument('--screen',action='store_true')
    parser.add_argument('--report',action='store_true')
    args=parser.parse_args()
    if args.prepare or not CACHE.exists():prepare()
    if args.screen or (not args.prepare and not args.report):screen()
    if args.report or args.screen:report()


if __name__=='__main__':main()
