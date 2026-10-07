"""Finite, causal hypothesis bank and trade-timing diagnostics (no order placement)."""
from __future__ import annotations
import json
import argparse
import numpy as np
import pandas as pd
from backtest.provider_research import BAR_CACHE, FEATURE_CACHE, ENTRY_QUOTE_CACHE, OUTPUT, provider_trades, split_name
from backtest.provider_calendar import expiries_for


def rank(s, w, fraction=1):
    return s.rolling(w, min_periods=int(np.ceil(w*fraction))).rank(pct=True)


def analyze_signals(premium_only=False,open_only=False):
    bars = pd.read_csv(BAR_CACHE, index_col=0, parse_dates=True)
    bars.index = pd.to_datetime(bars.index, utc=True).tz_convert('Asia/Kolkata') + pd.Timedelta(minutes=1)
    p = pd.read_csv(FEATURE_CACHE)
    p['minute'] = pd.to_datetime(p.minute, utc=True).dt.tz_convert('Asia/Kolkata')
    p = p.sort_values(['expiry', 'minute']).reset_index(drop=True)
    p['expiry'] = pd.to_datetime(p.expiry).dt.date
    idx = bars.index
    days = idx.date
    nearest = {d: expiries_for(d)[0] for d in set(days)}
    take = np.array([e == nearest[t.date()] for e, t in zip(p.expiry, p.minute)])
    groups = p.groupby('expiry', sort=False).groups
    def grouped(s, fn):
        out = pd.Series(np.nan, index=p.index)
        for indices in groups.values():
            out.loc[indices] = fn(s.loc[indices]).to_numpy()
        return out
    def align(s):
        return pd.Series(s.loc[take].to_numpy(), index=pd.DatetimeIndex(p.loc[take, 'minute'])).reindex(idx)
    def on_panel(s):
        return pd.Series(s.reindex(pd.DatetimeIndex(p.minute)).to_numpy(), index=p.index)
    trades = provider_trades()
    entry_quotes=pd.read_csv(ENTRY_QUOTE_CACHE)
    entry_quotes.index=pd.to_datetime(entry_quotes.pop('minute'),utc=True).dt.tz_convert('Asia/Kolkata')
    if entry_quotes.index.duplicated().any():
        raise ValueError('Duplicate entry-reference quotes')
    entry_quotes=entry_quotes.reindex(idx)
    eligible = (idx.hour*60+idx.minute >= 615) & (idx.hour*60+idx.minute <= 855)
    eligible &= idx >= trades.entry_minute.min()
    flat = np.ones(len(idx), dtype=bool)
    for t in trades.itertuples():
        flat[(idx > t.entry_minute) & (idx <= t.exit_minute)] = False
    entryloc = idx.get_indexer(trades.entry_minute)
    if (entryloc < 0).any():
        raise ValueError('Missing index candle at an actual entry')
    starts = np.array([np.searchsorted(idx, trades.entry_minute.min())] +
                      [np.searchsorted(idx, t + pd.Timedelta(minutes=1)) for t in trades.exit_minute[:-1]])
    minute_split = np.array([split_name(d) for d in days])
    values = trades[['signal_id', 'entry', 'option_type', 'split']].to_dict('list')
    results, detail = [], []
    def score(name, a, b=None, save=True, premium_cap=None, premium_reference='open'):
        av = np.asarray(a)
        bv = av if b is None else np.asarray(b)
        signal = np.where((av>.8)&(bv>.8), 1, np.where((av<.2)&(bv<.2), -1, 0))
        if premium_cap is not None and premium_reference=='open':
            ce_price,pe_price=entry_quotes.ce_ltp.to_numpy(),entry_quotes.pe_ltp.to_numpy()
        else:
            ce_price, pe_price = align(p.ce_ltp).to_numpy(), align(p.pe_ltp).to_numpy()
        actual_short_px=np.where(trades.direction.to_numpy()==1,pe_price[entryloc],ce_price[entryloc])
        if premium_cap is not None:
            short_px=np.where(signal==1,pe_price,ce_price)
            signal[~np.isfinite(short_px) | (short_px>premium_cap)] = 0
        signal[~eligible] = 0
        known = np.isfinite(av[entryloc]) & np.isfinite(bv[entryloc])
        if premium_cap is not None:
            known &= np.isfinite(actual_short_px)
        matched = signal[entryloc] == trades.direction.to_numpy()
        first_ok, first_near, first_times, first_dirs = [], [], [], []
        for j, (lo, hi) in enumerate(zip(starts, entryloc)):
            found = np.flatnonzero(signal[lo:hi+1]) + lo
            first = found[0] if len(found) else -1
            first_ok.append(first == hi and matched[j])
            first_near.append(first >= 0 and abs((idx[first]-idx[hi]).total_seconds()) <= 120 and signal[first] == trades.direction.iloc[j])
            first_times.append(str(idx[first]) if first >= 0 else '')
            first_dirs.append(int(signal[first]) if first >= 0 else 0)
        episodes = (signal != 0) & flat & ((np.r_[0, signal[:-1]] != signal) | ~np.r_[False, flat[:-1]] | np.r_[True, days[1:] != days[:-1]])
        row = {'candidate':name}
        for split in ('fit','validation','evaluation','case_study'):
            mask = trades.split.eq(split).to_numpy()
            row.update({f'{split}_trades':int(mask.sum()), f'{split}_available':int(known[mask].sum()),
                        f'{split}_direction_matches':int(matched[mask].sum()),
                        f'{split}_first_exact':int(np.asarray(first_ok)[mask].sum()),
                        f'{split}_first_within_two_minutes':int(np.asarray(first_near)[mask].sum()),
                        f'{split}_flat_signal_minutes':int(((signal!=0)&flat&(minute_split==split)).sum()),
                        f'{split}_flat_signal_episodes':int((episodes&(minute_split==split)).sum())})
        results.append(row)
        if save:
            values[name] = av[entryloc] if b is None else bv[entryloc]
        if name in ('baseline', 'selected_fit', 'premium_cap_200'):
            for j,t in trades.iterrows():
                detail.append({'candidate':name,'signal_id':t.signal_id,'alpha':av[entryloc[j]],'alpha2':bv[entryloc[j]],
                    'available':known[j],'direction_matches':matched[j],'first_exact':first_ok[j],
                    'first_candidate_since_previous_exit':first_times[j],'first_direction':first_dirs[j],
                    'short_premium_at_actual_direction':actual_short_px[j],
                    'premium_cap_pass':bool(np.isfinite(actual_short_px[j]) and actual_short_px[j]<=200)})
            pd.DataFrame({'minute':idx,'alpha':av,'alpha2':bv,'signal':signal,'provider_flat':flat}).to_csv(
                OUTPUT/f'{name}_minute_signals.csv.gz',index=False,compression='gzip')
        return row
    def append_results():
        old=pd.read_csv(OUTPUT/'signal_candidates.csv')
        names=[r['candidate'] for r in results]
        pd.concat([old[~old.candidate.isin(names)],pd.DataFrame(results)],ignore_index=True).to_csv(OUTPUT/'signal_candidates.csv',index=False)
        old=pd.read_csv(OUTPUT/'entry_diagnostics.csv')
        if detail:
            pd.concat([old[~old.candidate.isin(names)],pd.DataFrame(detail)],ignore_index=True).to_csv(OUTPUT/'entry_diagnostics.csv',index=False)
        old=pd.read_csv(OUTPUT/'entry_parameters.csv').copy()
        new={k:v for k,v in values.items() if k not in ('signal_id','entry','option_type','split')}
        pd.concat([old.drop(columns=list(new),errors='ignore'),pd.DataFrame(new)],axis=1).to_csv(OUTPUT/'entry_parameters.csv',index=False)

    def open_screen():
        vols={}
        for kind in ('same_contract','with_overnight'):
            suffix='return' if kind=='same_contract' else 'return_with_overnight'
            vols[kind]=(grouped(p[f'ce_{suffix}'],lambda v:v.rolling(300,min_periods=240).std())+
                        grouped(p[f'pe_{suffix}'],lambda v:v.rolling(300,min_periods=240).std()))
        for native in (False,True):
            suffix='native_volume' if native else 'volume'
            vr=(grouped(p[f'ce_{suffix}'],lambda v:v.rolling(5).mean()/v.rolling(300,min_periods=240).mean().replace(0,np.nan))+
                grouped(p[f'pe_{suffix}'],lambda v:v.rolling(5).mean()/v.rolling(300,min_periods=240).mean().replace(0,np.nan)))/2
            for horizon in (1,3,5,10,15,30):
                for price in ('open_to_open','close_to_open'):
                    previous=bars.open.shift(horizon) if price=='open_to_open' else bars.close.shift(horizon)
                    change=(bars.open-previous)/bars.open.shift(horizon)
                    a=rank(change,800)
                    for kind,vol in vols.items():
                        b=align(grouped(on_panel(change)*vr/vol.where(vol>0),lambda v:rank(v,300,.9)))
                        score(f'{price}_h{horizon}_{suffix}_{kind}',a,b)

    if open_only:
        open_screen()
        append_results()
        print(pd.DataFrame(results).sort_values(['fit_first_exact','fit_direction_matches'],ascending=False).head(6).to_string(index=False),flush=True)
        return
    if premium_only:
        previous=pd.read_csv(OUTPUT/'baseline_minute_signals.csv.gz',index_col=0)
        previous.index=pd.to_datetime(previous.index,utc=True).tz_convert('Asia/Kolkata')
        score('premium_cap_200',previous.alpha.reindex(idx),previous.alpha2.reindex(idx),premium_cap=200)
        score('premium_cap_200_close_atm',previous.alpha.reindex(idx),previous.alpha2.reindex(idx),premium_cap=200,premium_reference='close')
        append_results()
        print(json.dumps(results[0],indent=2),flush=True)
        return
    # Alpha screen: ranks of actual observable price moves, not future changes.
    alpha = {}
    for h in (1,3,5,10,15,30):
        for norm in ('lag_open','close_return'):
            pc = ((bars.close-bars.close.shift(h))/bars.open.shift(h) if norm=='lag_open' else bars.close.pct_change(h, fill_method=None))
            for w in (300,800,1600):
                name=f'spot_{norm}_h{h}_r{w}'
                alpha[name] = rank(pc,w)
                score(name,alpha[name])
    baseline_alpha = alpha['spot_lag_open_h5_r800']
    pc = on_panel((bars.close-bars.close.shift(5))/bars.open.shift(5))
    synthetic = p.atm_strike+p.ce_ltp-p.pe_ltp
    for h in (1,3,5,10,15,30):
        changes = grouped(synthetic,lambda s:s.pct_change(h,fill_method=None))
        for w in (300,800,1600):
            name=f'parity_forward_h{h}_r{w}'
            alpha[name]=align(grouped(changes,lambda s:rank(s,w)))
            score(name,alpha[name])
    for h in (1,5,15):
        changes=grouped(p.ce_return-p.pe_return,lambda s:s.rolling(h).sum())
        for w in (300,800,1600):
            name=f'option_return_difference_h{h}_r{w}'
            alpha[name]=align(grouped(changes,lambda s:rank(s,w)))
            score(name,alpha[name])
    # Session context is diagnostic; it is not assumed to be the missing filter.
    opening = bars.open.groupby(days).transform('first')
    for name,s in {'from_open':bars.close/opening-1,
                   'opening_gap':opening/bars.close.groupby(days).last().shift().reindex(days).set_axis(idx)-1,
                   'spot':bars.close}.items():
        values[name]=s.iloc[entryloc].to_numpy()
    volatilities={}
    for kind in ('same_contract','with_overnight','rolling_atm','price_level','iv'):
        if kind=='iv':
            volatilities[kind]=p.ce_iv+p.pe_iv
            continue
        for window in (60,300):
            sides=[]
            for side in ('ce','pe'):
                s = p[f'{side}_return'] if kind=='same_contract' else p[f'{side}_return_with_overnight'] if kind=='with_overnight' else p[f'{side}_ltp']
                if kind=='rolling_atm':
                    s=grouped(s,lambda v:v.pct_change(fill_method=None))
                sides.append(grouped(s,lambda v:v.rolling(window,min_periods=int(.8*window)).std()))
            volatilities[f'{kind}{window}']=sides[0]+sides[1]
    best=None
    # All alpha2 candidates use the documented five-minute price change.
    # Search is selected on fit only; later periods are reported independently.
    for native in (False,True):
        ce=p['ce_native_volume' if native else 'ce_volume']
        pe=p['pe_native_volume' if native else 'pe_volume']
        for short,base in ((1,300),(5,300),(5,60),(5,20),(20,300)):
            def ratio(s):
                return grouped(s,lambda v:v.rolling(short,min_periods=short).mean()/v.rolling(base,min_periods=int(.8*base)).mean().replace(0,np.nan))
            vr=(ratio(ce)+ratio(pe))/2
            for volname,vol in volatilities.items():
                raw=pc*vr/vol.where(vol>0)
                for window in (150,300,600):
                    name=f'a2_{"native" if native else "masked"}_v{short}_{base}_{volname}_r{window}'
                    a2=align(grouped(raw,lambda v:rank(v,window,.9)))
                    row=score(name,baseline_alpha,a2)
                    objective=(row['fit_first_exact'],row['fit_direction_matches'],-row['fit_flat_signal_episodes'])
                    if best is None or objective>best[0]:
                        best=(objective,name,a2.copy())
                    if not native and (short,base,volname,window)==(5,300,'same_contract300',300):
                        baseline_a2=a2.copy()
                        event_panel=p.copy()
                        event_panel['price_change']=pc
                        event_panel['volume_ratio']=vr
                        event_panel['atm_volatility']=vol
                        event_panel['alpha2_raw']=raw
                        event_panel['alpha2']=grouped(raw,lambda v:rank(v,window,.9))
                        event_panel['alpha']=on_panel(baseline_alpha)
                        event_panel=event_panel.set_index(['minute','expiry'])
                        events=[]
                        for kind in ('entry','exit'):
                            keys=pd.MultiIndex.from_arrays([trades[f'{kind}_minute'],trades.expiry],names=event_panel.index.names)
                            ev=event_panel.reindex(keys).reset_index()
                            ev.insert(0,'signal_id',trades.signal_id.to_numpy())
                            ev.insert(1,'event',kind)
                            ev['recorded_timestamp']=trades[kind].to_numpy()
                            events.append(ev)
                        pd.concat(events,ignore_index=True).to_csv(OUTPUT/'event_parameters.csv',index=False)
                        score('baseline',baseline_alpha,a2)
            print(f'Screened volume {native=} {short}/{base}',flush=True)
    for name,multiplier in {
        'combined_volume':(p.ce_native_volume+p.pe_native_volume),
        'put_call_volume':p.pe_native_volume/p.ce_native_volume.replace(0,np.nan),
        'put_call_oi':p.pe_oi/p.ce_oi.replace(0,np.nan),
    }.items():
        if name=='combined_volume':
            multiplier=grouped(multiplier,lambda v:v.rolling(5).mean()/v.rolling(300,min_periods=240).mean().replace(0,np.nan))
        a2=align(grouped(pc*multiplier/volatilities['same_contract300'].replace(0,np.nan),lambda v:rank(v,300,.9)))
        score('a2_'+name,baseline_alpha,a2)
    score('selected_fit',baseline_alpha,best[2])
    # Exploratory structural rule from the published short-leg fills.
    score('premium_cap_200',baseline_alpha,baseline_a2,premium_cap=200)
    score('premium_cap_200_close_atm',baseline_alpha,baseline_a2,premium_cap=200,premium_reference='close')
    # Timing/confirmation diagnostics are declared separately from the formula screen.
    # The next-candle value is unavailable at the recorded entry; never deploy it.
    for delay in (-1,1,2,3,5):
        name='NONCAUSAL_containing_candle' if delay==-1 else f'baseline_delayed_{delay}m'
        score(name,baseline_alpha.shift(delay),baseline_a2.shift(delay))
    for n in (2,3):
        a=baseline_alpha.copy(); b=baseline_a2.copy()
        long=((a>.8)&(b>.8)).rolling(n).sum().eq(n)
        short=((a<.2)&(b<.2)).rolling(n).sum().eq(n)
        confirmed=a.where(long|short,.5)
        score(f'baseline_confirm_{n}',confirmed,b)
    for h in (1,3,5,10,15,30):
        pc_body=(bars.close-bars.open.shift(h-1))/bars.open.shift(h-1)
        body_alpha=rank(pc_body,800)
        vr=(grouped(p.ce_volume,lambda v:v.rolling(5).mean()/v.rolling(300,min_periods=240).mean().replace(0,np.nan))+
            grouped(p.pe_volume,lambda v:v.rolling(5).mean()/v.rolling(300,min_periods=240).mean().replace(0,np.nan)))/2
        body_a2=align(grouped(on_panel(pc_body)*vr/volatilities['same_contract300'].replace(0,np.nan),lambda v:rank(v,300,.9)))
        score(f'bar_body_h{h}',body_alpha,body_a2)
    # A small alpha x alpha2 cross-check, alpha finalists chosen on fit entries only.
    alpha_scores=[r for r in results if r['candidate'] in alpha]
    finalists=sorted(alpha_scores,key=lambda r:(r['fit_first_exact'],r['fit_direction_matches'],-r['fit_flat_signal_episodes']),reverse=True)[:5]
    for row in finalists:
        score('paired_'+row['candidate'],alpha[row['candidate']],best[2],save=False)
    open_screen()
    pd.DataFrame(results).to_csv(OUTPUT/'signal_candidates.csv',index=False)
    pd.DataFrame(values).to_csv(OUTPUT/'entry_parameters.csv',index=False)
    pd.DataFrame(detail).to_csv(OUTPUT/'entry_diagnostics.csv',index=False)
    (OUTPUT/'selected_hypothesis.json').write_text(json.dumps({'candidate':best[1], 'fit_objective':best[0],
        'status':'research only; not automatically promoted to live defaults',
        'timing_metric':'first eligible signal since previous provider exit, conditional on actual provider position history; not autonomous backtest'},indent=2))
    print('Selected on fit:',best[1],best[0],flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--premium-only',action='store_true',help='append the premium-limit test to an existing completed signal screen')
    parser.add_argument('--open-only',action='store_true',help='append exploratory opening-price signal variants')
    args=parser.parse_args()
    analyze_signals(args.premium_only,args.open_only)
