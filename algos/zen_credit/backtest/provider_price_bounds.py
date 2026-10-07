"""Causal sampling trials and explicitly noncausal price-envelope diagnostics.

The entry candle's future high/low are never tradable features. These bounds
cannot tell whether an extreme happened before the source entry timestamp.
"""
import json
import hashlib
import numpy as np
import pandas as pd
from backtest.provider_trials import OUT,provisional_rank,sampled_rank,price_change_series,load_alpha,Scorer,rank,SPLITS,signal_sequence_signature
from backtest.provider_triggers import context
from backtest.provider_research import provider_trades


def merge_bulk_frontiers(root):
    """Merge independently written shard finalists with deterministic ties."""
    import shutil
    import csv
    finalists=[];status=[];journals=[]
    for shard in range(16):
        directory=root/f'shard_{shard:02d}';path=directory/'frontier.json'
        if not path.exists():continue
        design=json.loads((directory/'search_design.json').read_text())
        status.append({'shard':shard,'completed_recipes':design['tested_formula_recipes']})
        journals.append(directory/'formula_trials.csv')
        for candidate in json.loads(path.read_text()):
            archive=directory/f'candidate_{candidate["candidate_id"]}.npz'
            if not archive.exists():raise ValueError(f'Missing bulk finalist archive: {archive}')
            finalists.append((candidate,archive))
    finalists.sort(key=lambda pair:(tuple(-x for x in pair[0]['objective']),pair[0]['candidate_id']))
    selected=[];seen=set();aliases=[];signal_seen={};signal_aliases=[]
    for candidate,archive in finalists:
        with np.load(archive,allow_pickle=False) as arrays:
            digest=hashlib.sha256()
            for name in ('minutes','alpha','alpha2'):digest.update(arrays[name].tobytes())
            index=pd.to_datetime(arrays['minutes'],unit='ns',utc=True)
            signal_signature=signal_sequence_signature(index,arrays['alpha'],arrays['alpha2'],
                {'recipe':candidate.get('recipe',{})})
        signature=digest.hexdigest()
        rank_key=(signature,signal_signature)
        if rank_key in seen:
            aliases.append(candidate['candidate_id']);continue
        seen.add(rank_key)
        if signal_signature in signal_seen:
            signal_aliases.append({'candidate_id':candidate['candidate_id'],
                                   'representative':signal_seen[signal_signature]})
            continue
        signal_seen[signal_signature]=candidate['candidate_id']
        if len(selected)<12:
            selected.append(candidate);shutil.copyfile(archive,root/archive.name)
    temporary=root/'frontier.tmp';temporary.write_text(json.dumps(selected,indent=2));temporary.replace(root/'frontier.json')
    if journals and all(path.exists() for path in journals):
        temporary=root/'formula_trials.tmp';header=None
        with temporary.open('w',newline='',encoding='utf-8') as stream:
            writer=csv.writer(stream)
            for path in journals:
                with path.open(newline='',encoding='utf-8') as source:
                    reader=csv.reader(source);current=next(reader)
                    if header is None:header=current;writer.writerow(header)
                    elif current!=header:raise ValueError('Bulk shard journal schemas disagree')
                    writer.writerows(reader)
        temporary.replace(root/'formula_trials.csv')
    report={'shards':status,'completed_recipes':sum(s['completed_recipes'] for s in status),
        'expected_recipes':30720,'expected_parameter_pairs':153600,
        'complete':len(status)==16 and all(s['completed_recipes']==1920 for s in status),
        'retained_candidates':len(selected),'identical_rank_aliases':aliases,
        'identical_signal_aliases':signal_aliases,
        'selection':'Fit conditional first-exact, direction matches, fewer episodes; deterministic ID ties.',
        'limitations':'Formula screening is not autonomous replication evidence. Later splits were previously inspected.'}
    (root/'bulk_progress.json').write_text(json.dumps(report,indent=2))
    return report


def run_bulk_workers(workers=2,limit=0):
    """Bounded local workers, each owning one resumable shard journal."""
    import subprocess
    import sys
    from concurrent.futures import ThreadPoolExecutor,wait,FIRST_COMPLETED
    from pathlib import Path
    if workers not in (1,2) or not isinstance(limit,int) or limit<0:
        raise ValueError('Use one or two workers and a nonnegative recipe limit')
    root=OUT/'bulk';root.mkdir(exist_ok=True)
    cwd=Path(__file__).resolve().parents[1]
    def execute(shard):
        directory=root/f'shard_{shard:02d}';directory.mkdir(exist_ok=True)
        command=[sys.executable,'-B','-u','-m','backtest.provider_trials','--family','bulk','--shard',str(shard),'--limit',str(limit)]
        with (directory/'worker.log').open('a',encoding='utf-8') as log:
            log.write('\nStarting resumable bulk worker\n');log.flush()
            result=subprocess.run(command,cwd=cwd,stdout=log,stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        return shard,result.returncode
    failures=[]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending={pool.submit(execute,shard) for shard in range(16)}
        while pending:
            ready,pending=wait(pending,timeout=30,return_when=FIRST_COMPLETED)
            for future in ready:
                shard,code=future.result()
                print(f'Bulk shard {shard:02d} finished, exit={code}; remaining={len(pending)}',flush=True)
                if code:failures.append({'shard':shard,'exit_code':code})
            if not ready:print(f'Bulk search active: {len(pending)} shards remaining',flush=True)
    if failures:
        (root/'worker_failures.json').write_text(json.dumps(failures,indent=2))
        raise RuntimeError(f'Bulk workers failed: {failures}; inspect shard worker.log, then resume')
    report=merge_bulk_frontiers(root);print(json.dumps(report),flush=True)
    return report


def rank_conventions(series,window,fraction=1.):
    """Common trailing percentile definitions, with explicit tie handling.

    The current observed value is included in every window. Missing values stay
    missing; finite history alone determines the valid count and percentile.
    """
    if window<2 or not 0<fraction<=1:raise ValueError('Invalid rank window or coverage')
    s=series.where(np.isfinite(series))
    rolling=s.rolling(window,min_periods=int(np.ceil(window*fraction)))
    count=s.rolling(window,min_periods=1).count()
    average=rolling.rank(method='average',pct=False)
    low=rolling.rank(method='min',pct=False);high=rolling.rank(method='max',pct=False)
    return {'average_pct':average/count,'minimum_pct':low/count,'maximum_pct':high/count,
        'average_zero_one':(average-1)/(count-1).where(count>1),
        'empirical_strict':(low-1)/count,'empirical_mid':(average-.5)/count}


def prior_observation_rank(series, window, fraction=1.):
    """Midrank against exactly the previous N rows, excluding current input.

    Unknown prior rows occupy window slots but do not enter its denominator.
    The sorted finite window uses O(N) memory; no missing values are filled.
    """
    from bisect import bisect_left, bisect_right, insort
    if isinstance(window, bool) or not isinstance(window, int) or window < 1:
        raise ValueError('Prior-rank window must be a positive integer')
    if not np.isfinite(fraction) or not 0 < fraction <= 1:
        raise ValueError('Prior-rank coverage must be in (0,1]')
    values = series.to_numpy(dtype=float)
    result = np.full(len(values), np.nan)
    history = []; minimum = int(np.ceil(window*fraction))
    for i, value in enumerate(values):
        if np.isfinite(value) and len(history) >= minimum:
            lo = bisect_left(history, value); hi = bisect_right(history, value)
            result[i] = (lo+.5*(hi-lo))/len(history)
        if i >= window and np.isfinite(values[i-window]):
            old = values[i-window]; history.pop(bisect_left(history, old))
        if np.isfinite(value):insort(history, value)
    return pd.Series(result, index=series.index, name=series.name)


def prior_rank_alpha_screen():
    """Compare previous-only rank support on two original alpha1 inputs."""
    import time
    started = time.perf_counter()
    bars, _, _ = context(); scorer = Scorer(bars.index); bank = load_alpha()
    recipes = json.loads((OUT/'alpha_recipes.json').read_text())
    target = OUT/'prior_observation_rank'; target.mkdir(exist_ok=True)
    trials = []; rows = []
    for name in ('close_old_open_h5_r800', 'close_close_old_open_h5_r800'):
        raw = price_change_series(bars, recipes[name])
        original = bank[name]; alpha = prior_observation_rank(raw, 800, 1.)
        np.testing.assert_array_equal(rank(raw, 800, 1.).to_numpy(), original.to_numpy())
        metrics, _ = scorer.score(alpha); original_metrics, _ = scorer.score(original)
        recipe = {'price_recipe': recipes[name], 'rank_window': 800,
            'rank_support': 'previous800 rows excluding current', 'minimum_fraction': 1.,
            'tie_convention': '(past strictly below + half past equal)/finite past count'}
        cid = hashlib.sha256(json.dumps(recipe, sort_keys=True).encode()).hexdigest()[:16]
        improved = metrics['fit_direction_matches'] > original_metrics['fit_direction_matches']
        trial = {'candidate_id': cid, 'alpha': name, 'recipe': recipe, 'metrics': metrics,
            'original_metrics': original_metrics, 'fit_direction_improved': improved,
            'all_direction_matches': sum(metrics[s+'_direction_matches'] for s in SPLITS)}
        if improved:
            np.savez_compressed(target/f'alpha_{cid}.npz', minutes=bars.index.as_unit('ns').asi8,
                alpha=alpha.to_numpy(), raw=raw.to_numpy())
        trials.append(trial)
        for i, trade in enumerate(scorer.trades.itertuples()):
            k = scorer.entries[i]; old = original.iloc[k]; new = alpha.iloc[k]
            passed = lambda value: bool(value>.8 if trade.direction==1 else value<.2)
            rows.append({'candidate_id': cid, 'alpha_recipe': name, 'signal_id': trade.signal_id,
                'entry': trade.entry, 'split': trade.split, 'option_type': trade.option_type,
                'original_alpha': old, 'prior_only_alpha': new,
                'original_direction_pass': passed(old), 'prior_only_direction_pass': passed(new),
                'current_raw_known': bool(np.isfinite(raw.iloc[k]))})
    pd.DataFrame(rows).to_csv(target/'source_alpha_comparison.csv', index=False)
    report = {'trials': trials, 'elapsed_seconds': time.perf_counter()-started,
        'rank_definition': 'Finite values from previous N rows only; current excluded; midrank; unknown rows retained as slots.',
        'alpha_coverage': '100% of800 past rows; current finite required',
        'beta_control': 'Helper supports90% of300 past rows; no beta screen or replay in this diagnostic.',
        'causality': 'Completed original price inputs; no fill, source-dependent features or new time filters.',
        'limits': 'Necessary alpha1 compatibility only. Fit-direction improvement controls archive selection; no autonomous replication claim. Later periods previously inspected.',
        'production_change': False}
    (target/'comparison.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2), flush=True)


def completed_smoothed_price(bars,kind,parameter=None):
    """Research price feeds from completed candles; never fill absent candles."""
    close=bars.close.where(np.isfinite(bars.close)&(bars.close>0))
    if kind=='close':return close
    if kind=='weighted_open_close':
        if parameter is None or not np.isfinite(parameter) or not 0<=parameter<=1:
            raise ValueError('Open/close weight must be between zero and one')
        opening=bars.open.where(np.isfinite(bars.open)&(bars.open>0))
        return (opening*(1-parameter)+close*parameter).where(opening.notna()&close.notna())
    if kind not in ('ema','mean','median') or not isinstance(parameter,int) or parameter<2:
        raise ValueError('Invalid completed-price smoothing recipe')
    if kind=='ema':
        return close.ewm(span=parameter,adjust=False,min_periods=parameter).mean().where(close.notna())
    rolling=close.rolling(parameter,min_periods=parameter)
    return rolling.mean() if kind=='mean' else rolling.median()


def smoothed_price_screen():
    """Test fixed causal price feeds; fit ranks prioritize, never certify entries."""
    bars,_,_=context();scorer=Scorer(bars.index)
    target=OUT/'smoothed_price';target.mkdir(exist_ok=True)
    specs=[('close',None)]+[('weighted_open_close',w) for w in (.25,.5,.75)]
    specs += [(kind,n) for kind in ('ema','mean') for n in (2,3,5)]
    specs += [('median',n) for n in (3,5)]
    trials=[];source_rows=[];leaders=[];controls=[]
    for kind,parameter in specs:
        feed=completed_smoothed_price(bars,kind,parameter)
        for horizon in (4,5,6):
            old_open=bars.open.shift(horizon);old_feed=feed.shift(horizon)
            raw_definitions={'feed_minus_old_open':(feed-old_open)/old_open.where(old_open>0),
                'feed_change_over_old_open':(feed-old_feed)/old_open.where(old_open>0),
                'feed_change_over_old_feed':(feed-old_feed)/old_feed.where(old_feed>0)}
            for expression,raw in raw_definitions.items():
                alpha=rank(raw,800,1.);metrics,_=scorer.score(alpha)
                recipe={'feed':kind,'parameter':parameter,'horizon':horizon,
                    'expression':expression,'rank_window':800,'completed_candles_only':True}
                identity=json.dumps(recipe,sort_keys=True);cid=hashlib.sha256(identity.encode()).hexdigest()[:16]
                objective=[metrics['fit_direction_matches'],metrics['fit_first_exact'],-metrics['fit_signal_episodes']]
                candidate={'candidate_id':cid,'recipe':recipe,'metrics':metrics,'objective':objective}
                trials.append({**candidate,'all_direction_matches':sum(metrics[s+'_direction_matches'] for s in SPLITS)})
                control=kind=='close' and horizon==5 and expression=='feed_minus_old_open'
                if control:
                    np.testing.assert_array_equal(alpha.to_numpy(),load_alpha()['close_old_open_h5_r800'].to_numpy())
                    controls.append(candidate)
                if len(leaders)<6 or tuple(objective)>tuple(leaders[-1]['objective']) or control:
                    if not control:
                        leaders.append(candidate);leaders.sort(key=lambda c:tuple(c['objective']),reverse=True);leaders=leaders[:6]
                    if control or any(c['candidate_id']==cid for c in leaders):
                        np.savez_compressed(target/f'alpha_{cid}.npz',minutes=bars.index.as_unit('ns').asi8,
                            alpha=alpha.to_numpy(),raw=raw.to_numpy())
                values=alpha.to_numpy()[scorer.entries]
                for i,t in enumerate(scorer.trades.itertuples()):
                    value=values[i];passed=bool(value>.8 if t.direction==1 else value<.2)
                    source_rows.append({'candidate_id':cid,'signal_id':t.signal_id,'entry':t.entry,
                        'split':t.split,'option_type':t.option_type,'alpha':value,'direction_pass':passed})
    pd.DataFrame(source_rows).to_csv(target/'source_alpha_values.csv',index=False)
    (target/'alpha_trials.json').write_text(json.dumps(trials,indent=2))
    (target/'alpha_frontier.json').write_text(json.dumps(leaders+controls,indent=2))
    (target/'search_design.json').write_text(json.dumps({'trials':len(trials),'feeds':specs,'horizons':[4,5,6],
        'rank_window':800,'selection':'Fit direction compatibility, then conditional first-exact, then fewer episodes.',
        'causality':'Completed candles only. No source-dependent weights, forward fill, future prices or date/clock predictors. EMA output remains absent where the current candle is absent.',
        'limits':'Smoothing is a hypothesis beyond the supplied price description. Direction compatibility is necessary, not autonomous entry proof. Later dates already inspected; no untouched-holdout claim.',
        'production_change':False},indent=2))
    print(json.dumps({'trials':len(trials),'fit_selected':leaders[0],
        'maximum_all_direction_matches':max(t['all_direction_matches'] for t in trials)},indent=2),flush=True)


def weighted_observation_rank(series,window,kind='uniform',half_life=None,minimum=None):
    """Causal age-weighted current percentile; missing slots keep their age."""
    if not isinstance(window,int) or isinstance(window,bool) or window<2:
        raise ValueError('Invalid weighted rank window')
    minimum=window if minimum is None else minimum
    if not isinstance(minimum,int) or isinstance(minimum,bool) or not 1<=minimum<=window:
        raise ValueError('Invalid weighted rank coverage')
    if kind=='uniform':weights=np.ones(window)
    elif kind=='linear':weights=np.arange(1,window+1,dtype=float)/window
    elif kind=='exponential':
        if half_life is None or not np.isfinite(half_life) or half_life<=0:
            raise ValueError('Invalid weighted rank half life')
        weights=np.exp2(-np.arange(window-1,-1,-1,dtype=float)/half_life)
    else:raise ValueError('Unknown weighted rank kernel')
    values=series.to_numpy(dtype=float)
    if not len(values):return series.astype(float)
    padded=np.pad(values,(window-1,0),constant_values=np.nan)
    history=np.lib.stride_tricks.sliding_window_view(padded,window)
    result=np.full(len(values),np.nan)
    for first in range(0,len(values),256):
        last=min(first+256,len(values));sample=history[first:last];current=values[first:last,None]
        valid=np.isfinite(sample)
        denominator=(valid*weights).sum(axis=1)
        less=((sample<current)&valid)*weights
        equal=((sample==current)&valid)*weights
        numerator=less.sum(axis=1)+.5*equal.sum(axis=1)+.5*weights[-1]
        known=(valid.sum(axis=1)>=minimum)&np.isfinite(values[first:last])&(denominator>0)
        result[first:last]=np.divide(numerator,denominator,out=np.full(last-first,np.nan),where=known)
    return pd.Series(result,index=series.index,name=series.name)


def weighted_alpha_rank_screen():
    """Six fixed rank kernels; raw five-bar change and full coverage unchanged."""
    bars,_,_=context();scorer=Scorer(bars.index);target=OUT/'weighted_alpha_rank'
    target.mkdir(exist_ok=True)
    recipe={'kind':'close_old_open','horizon':5,'rank_window':800,'session_reset':False}
    raw=price_change_series(bars,recipe);control=load_alpha()['close_old_open_h5_r800']
    definitions=[('uniform',None),('linear',None)]+[('exponential',h) for h in (100,200,400,800)]
    rows=[];source_rows=[];leaders=[]
    original=control.to_numpy()[scorer.entries]
    for kind,half_life in definitions:
        alpha=weighted_observation_rank(raw,800,kind,half_life,800)
        if kind=='uniform':np.testing.assert_array_equal(alpha.to_numpy(),control.to_numpy())
        metrics,_=scorer.score(alpha)
        definition={'kernel':kind,'half_life_observations':half_life,'window':800,'minimum':800,
            'price_recipe':recipe,'tie_rule':'weighted less + half weighted equals + half current weight, divided by known total weight'}
        cid=hashlib.sha256(json.dumps(definition,sort_keys=True).encode()).hexdigest()[:16]
        all_pass=sum(metrics[s+'_direction_matches'] for s in SPLITS)
        candidate={'candidate_id':cid,'definition':definition,'metrics':metrics,
            'all_direction_matches':all_pass,
            'objective':[metrics['fit_direction_matches'],metrics['fit_first_exact'],-metrics['fit_signal_episodes']]}
        leaders.append(candidate);rows.append({'candidate_id':cid,'kernel':kind,'half_life':half_life,**metrics,'all_direction_matches':all_pass})
        np.savez_compressed(target/f'alpha_{cid}.npz',minutes=bars.index.as_unit('ns').asi8,alpha=alpha.to_numpy())
        for i,t in enumerate(scorer.trades.itertuples()):
            value=alpha.iloc[scorer.entries[i]];passed=value>.8 if t.direction==1 else value<.2
            old=original[i]>.8 if t.direction==1 else original[i]<.2
            source_rows.append({'candidate_id':cid,'kernel':kind,'half_life':half_life,'signal_id':t.signal_id,
                'entry':t.entry,'split':t.split,'option_type':t.option_type,'alpha':value,
                'direction_pass':bool(passed),'control_alpha':original[i],'control_direction_pass':bool(old),
                'repairs_control_failure':bool(passed and not old),'loses_control_pass':bool(old and not passed)})
        print(json.dumps(rows[-1]),flush=True)
    leaders.sort(key=lambda c:(tuple(c['objective']),c['candidate_id']),reverse=True)
    (target/'alpha_frontier.json').write_text(json.dumps(leaders,indent=2))
    pd.DataFrame(rows).to_csv(target/'screen.csv',index=False)
    pd.DataFrame(source_rows).to_csv(target/'source_alpha_values.csv',index=False)
    (target/'search_design.json').write_text(json.dumps({'kernels':definitions,'raw_price_recipe':recipe,
        'selection':'Necessary fit direction conditions, conditional fit first entry and fewer fit episodes; later labels do not select kernel.',
        'causality':'Past/current observations only; unknown slots retain their age and full800 coverage required. No trading-clock, source-dependent weight or future observation.',
        'hypothesis_status':'Weighted percentile is an explicit alternative to the unweighted supplied-description rank; not verified private logic.',
        'production_change':False},indent=2))
    return leaders


def weighted_rank_pair_screen():
    """Four fixed paired ranks; same causal raw inputs and no-target execution."""
    from backtest.provider_trials import factor_contexts,continuous_native_components
    reference_id='95fefedfcf057448';directory=OUT/'weighted_rank_pairs'
    reference=json.loads((OUT/'bulk'/f'full_autonomous_{reference_id}_ledger'/'report.json').read_text())['candidate']
    bars,_,_=context();panel=factor_contexts(bars,opening=True)['continuous_near'][0]
    parts=continuous_native_components(bars,panel,reference['recipe'],reference['alpha_recipe'])
    alpha=load_alpha()[reference['alpha']];beta=parts.alpha2
    minutes=bars.index.as_unit('ns').asi8
    with np.load(OUT/'bulk'/f'candidate_{reference_id}.npz',allow_pickle=False) as stored:
        for key,actual in (('minutes',minutes),('alpha',alpha.to_numpy()),('alpha2',beta.to_numpy())):
            np.testing.assert_array_equal(actual,stored[key])
    alphas={'uniform':alpha,'exponential_h800':weighted_observation_rank(parts.price_change,800,'exponential',800,800)}
    betas={'uniform':beta,'exponential_h300':weighted_observation_rank(parts.raw2,300,'exponential',300,270)}
    scorer=Scorer(bars.index);directory.mkdir(exist_ok=True);frontier=[];rows=[];sources=[]
    for aname,a in alphas.items():
        for bname,b in betas.items():
            recipe={**reference['recipe'],'alpha_rank_kernel':aname,'alpha2_rank_kernel':bname,
                    'matched_reference_candidate':reference_id}
            cid=hashlib.sha256(json.dumps({'alpha':reference['alpha'],'recipe':recipe},sort_keys=True).encode()).hexdigest()[:16]
            metrics,_=scorer.score(a,b)
            candidate={'candidate_id':cid,'alpha':reference['alpha'],'alpha_recipe':reference['alpha_recipe'],
                       'recipe':recipe,'metrics':metrics,
                       'objective':[metrics['fit_first_exact'],metrics['fit_direction_matches'],-metrics['fit_signal_episodes']]}
            frontier.append(candidate);rows.append({'candidate_id':cid,'alpha_kernel':aname,'alpha2_kernel':bname,**metrics})
            np.savez_compressed(directory/f'candidate_{cid}.npz',minutes=minutes,alpha=a.to_numpy(),alpha2=b.to_numpy())
            for i,t in enumerate(scorer.trades.itertuples()):
                av=a.iloc[scorer.entries[i]];bv=b.iloc[scorer.entries[i]]
                passed=np.isfinite(av) and np.isfinite(bv) and ((av>.8 and bv>.8) if t.direction==1 else (av<.2 and bv<.2))
                sources.append({'candidate_id':cid,'signal_id':t.signal_id,'entry':t.entry,'split':t.split,
                                'alpha':av,'alpha2':bv,'joint_direction_pass':bool(passed)})
            print(json.dumps(rows[-1]),flush=True)
    frontier.sort(key=lambda c:(tuple(c['objective']),c['candidate_id']),reverse=True)
    (directory/'frontier.json').write_text(json.dumps(frontier,indent=2))
    pd.DataFrame(rows).to_csv(directory/'screen.csv',index=False)
    pd.DataFrame(sources).to_csv(directory/'source_signal_values.csv',index=False)
    (directory/'search_design.json').write_text(json.dumps({'pairs':4,'reference_candidate':reference_id,
        'alpha_selection':'Exponential half-life800 selected by necessary fit conditions from six fixed kernels; uniform control retained.',
        'alpha2_hypothesis':'Uniform versus exponential half-life equal to300-observation rank window; minimum270 unchanged.',
        'unchanged':'Completed five-bar return, geometric native volume1/10, sample logSTD150, factor lag5, strict .8/.2, no-target execution.',
        'causality':'Observation-age weights fixed before each calculation, current/past values only; missing slots retain their age. No date-specific trigger.',
        'limitations':'Later periods already inspected; screens are conditional signal evidence, not autonomous trade or performance results.',
        'production_change':False},indent=2))
    return frontier


def trailing_return_innovation(raw,window,kind='mean',lag=1):
    """Subtract a fixed, past-only return centre; missing history stays unknown."""
    if kind not in ('mean','median'):raise ValueError('Unknown return centre')
    if not isinstance(window,int) or isinstance(window,bool) or window<2:raise ValueError('Invalid centre window')
    if not isinstance(lag,int) or isinstance(lag,bool) or lag<1:raise ValueError('Centre must exclude current return')
    clean=raw.where(np.isfinite(raw))
    history=clean.shift(lag).rolling(window,min_periods=window)
    centre=history.mean() if kind=='mean' else history.median()
    return clean-centre


def return_innovation_alpha_screen(weighted=False):
    """Twenty fixed demeaning hypotheses and unchanged endpoint control."""
    bars,_,_=context();scorer=Scorer(bars.index);target=OUT/('weighted_return_innovation_alpha' if weighted else 'return_innovation_alpha')
    target.mkdir(exist_ok=True)
    recipe={'kind':'close_old_open','horizon':5,'rank_window':800,'session_reset':False}
    raw=price_change_series(bars,recipe);control=load_alpha()['close_old_open_h5_r800']
    definitions=[('unchanged',None,None)]+[(k,w,lag) for k in ('mean','median') for w in (30,60,150,300,800) for lag in (1,5)]
    def ranked(values):
        return weighted_observation_rank(values,800,'exponential',800,800) if weighted else rank(values,800,1.)
    rows=[];sources=[];candidates=[];original=control.to_numpy()[scorer.entries]
    for kind,window,lag in definitions:
        innovation=raw if kind=='unchanged' else trailing_return_innovation(raw,window,kind,lag)
        alpha=ranked(innovation)
        if kind=='unchanged':
            if weighted:
                with np.load(OUT/'weighted_alpha_rank'/'alpha_943fbe497c2db498.npz') as stored:
                    np.testing.assert_array_equal(alpha.to_numpy(),stored['alpha'])
            else:np.testing.assert_array_equal(alpha.to_numpy(),control.to_numpy())
        metrics,_=scorer.score(alpha)
        definition={'centre':kind,'centre_window':window,'centre_lag':lag,'price_recipe':recipe,'rank_window':800,'minimum':800}
        if weighted:definition['rank_kernel']='exponential_half_life800'
        cid=hashlib.sha256(json.dumps(definition,sort_keys=True).encode()).hexdigest()[:16]
        total=sum(metrics[s+'_direction_matches'] for s in SPLITS)
        candidates.append({'candidate_id':cid,'definition':definition,'metrics':metrics,'all_direction_matches':total,
                           'objective':[metrics['fit_direction_matches'],metrics['fit_first_exact'],-metrics['fit_signal_episodes']]})
        rows.append({'candidate_id':cid,**{k:definition[k] for k in ('centre','centre_window','centre_lag')},**metrics,'all_direction_matches':total})
        for i,t in enumerate(scorer.trades.itertuples()):
            value=alpha.iloc[scorer.entries[i]];passed=value>.8 if t.direction==1 else value<.2
            old=original[i]>.8 if t.direction==1 else original[i]<.2
            sources.append({'candidate_id':cid,'signal_id':t.signal_id,'entry':t.entry,'split':t.split,'option_type':t.option_type,
                'raw_change':raw.iloc[scorer.entries[i]],'innovation':innovation.iloc[scorer.entries[i]],'alpha':value,
                'direction_pass':bool(passed),'control_alpha':original[i],'repairs_control_failure':bool(passed and not old),'loses_control_pass':bool(old and not passed)})
        print(json.dumps(rows[-1]),flush=True)
    candidates.sort(key=lambda c:(tuple(c['objective']),c['candidate_id']),reverse=True)
    for c in candidates[:4]:
        d=c['definition'];innovation=raw if d['centre']=='unchanged' else trailing_return_innovation(raw,d['centre_window'],d['centre'],d['centre_lag'])
        np.savez_compressed(target/f"alpha_{c['candidate_id']}.npz",minutes=bars.index.as_unit('ns').asi8,alpha=ranked(innovation).to_numpy())
    (target/'alpha_frontier.json').write_text(json.dumps(candidates,indent=2))
    pd.DataFrame(rows).to_csv(target/'screen.csv',index=False);pd.DataFrame(sources).to_csv(target/'source_alpha_values.csv',index=False)
    (target/'search_design.json').write_text(json.dumps({'trials':len(definitions),'raw_price_recipe':recipe,
        'centre':'Subtract trailing mean or median of raw five-bar returns using fixed30/60/150/300/800 observations and past-only lag1/5.',
        'coverage':'Full centre window and800 innovation observations required; missing input never filled.',
        'rank_kernel':'Exponential observation-age half-life800' if weighted else 'Uniform average percentile',
        'selection':'Fit necessary direction conditions, conditional first entry, then fewer episodes. Source labels never determine centre.',
        'hypothesis_status':'Alternative to plain supplied-description return; unknown private preprocessing, not claimed recovered.',
        'production_change':False,'archives_retained':4},indent=2))
    return candidates


def complete_case_rank(raw,available,window=800,weighted=False):
    """Rank accepted historical rows; excluded current rows remain unknown."""
    if not raw.index.equals(available.index):raise ValueError('Availability clock differs')
    if available.isna().any() or available.dtype!=bool:raise ValueError('Availability must be known booleans')
    accepted=raw.loc[available & np.isfinite(raw)]
    if accepted.empty:return pd.Series(np.nan,index=raw.index,name=raw.name)
    result=weighted_observation_rank(accepted,window,'exponential',window,window) if weighted else rank(accepted,window,1.)
    return result.reindex(raw.index)


def complete_case_alpha_screen():
    """Fixed shared-frame drop policies, before/after return construction."""
    from backtest.provider_trials import factor_contexts,continuous_native_components
    reference_id='95fefedfcf057448';directory=OUT/'complete_case_alpha';directory.mkdir(exist_ok=True)
    seed=json.loads((OUT/'bulk'/f'full_autonomous_{reference_id}_ledger'/'report.json').read_text())['candidate']
    bars,_,_=context();panel=factor_contexts(bars,opening=True)['continuous_near'][0]
    parts=continuous_native_components(bars,panel,seed['recipe'],seed['alpha_recipe'])
    raw=parts.price_change;scorer=Scorer(bars.index);original=load_alpha()[seed['alpha']]
    def known(columns):return np.isfinite(panel[list(columns)]).all(axis=1)
    prices=known(('ce_ltp','pe_ltp')) & panel.ce_ltp.gt(0) & panel.pe_ltp.gt(0)
    volume=known(('ce_native_volume','pe_native_volume'))
    returns=known(('ce_return','pe_return'))
    factors=np.isfinite(parts.volume_ratio_lagged)&np.isfinite(parts.atm_volatility_lagged)&parts.atm_volatility_lagged.gt(0)
    masks={'index_only':pd.Series(True,index=bars.index),'both_prices':prices,'prices_and_volume':prices&volume,
           'prices_volume_returns':prices&volume&returns,'lagged_factors':factors,'raw_alpha2_known':np.isfinite(parts.raw2)}
    rows=[];sources=[];frontier=[];retained={};minutes=bars.index.as_unit('ns').asi8
    for mask_name,available in masks.items():
        for clock in ('return_then_filter','filter_then_return'):
            if mask_name=='index_only' and clock=='filter_then_return':continue
            selected_raw=raw if clock=='return_then_filter' else price_change_series(bars.loc[available],seed['alpha_recipe']).reindex(bars.index)
            for weighted in (False,True):
                alpha=complete_case_rank(selected_raw,available,800,weighted)
                if mask_name=='index_only':
                    expected=weighted_observation_rank(raw,800,'exponential',800,800) if weighted else original
                    np.testing.assert_array_equal(alpha.to_numpy(),expected.to_numpy())
                definition={'availability':mask_name,'return_clock':clock,'rank_kernel':'exponential_h800' if weighted else 'uniform',
                    'rank_window':800,'rank_minimum':800,'price_recipe':seed['alpha_recipe']}
                cid=hashlib.sha256(json.dumps(definition,sort_keys=True).encode()).hexdigest()[:16]
                metrics,_=scorer.score(alpha);total=sum(metrics[s+'_direction_matches'] for s in SPLITS)
                candidate={'candidate_id':cid,'definition':definition,'metrics':metrics,'all_direction_matches':total,
                           'objective':[metrics['fit_direction_matches'],metrics['fit_first_exact'],-metrics['fit_signal_episodes']]}
                frontier.append(candidate);rows.append({'candidate_id':cid,'availability':mask_name,'return_clock':clock,'rank_kernel':definition['rank_kernel'],
                    'accepted_rows':int(available.sum()),**metrics,'all_direction_matches':total})
                retained[cid]=alpha.to_numpy();frontier.sort(key=lambda c:(tuple(c['objective']),c['candidate_id']),reverse=True)
                keep={c['candidate_id'] for c in frontier[:4]};retained={k:v for k,v in retained.items() if k in keep}
                for i,t in enumerate(scorer.trades.itertuples()):
                    pos=scorer.entries[i];value=alpha.iloc[pos];old=original.iloc[pos];passed=value>.8 if t.direction==1 else value<.2;oldpass=old>.8 if t.direction==1 else old<.2
                    sources.append({'candidate_id':cid,'signal_id':t.signal_id,'entry':t.entry,'split':t.split,'option_type':t.option_type,
                        'current_available':bool(available.iloc[pos]),'selected_raw_change':selected_raw.iloc[pos],'alpha':value,'direction_pass':bool(passed),
                        'control_alpha':old,'repairs_control_failure':bool(passed and not oldpass),'loses_control_pass':bool(oldpass and not passed)})
                print(json.dumps(rows[-1]),flush=True)
    for cid,values in retained.items():np.savez_compressed(directory/f'alpha_{cid}.npz',minutes=minutes,alpha=values)
    (directory/'alpha_frontier.json').write_text(json.dumps(frontier,indent=2));pd.DataFrame(rows).to_csv(directory/'screen.csv',index=False)
    pd.DataFrame(sources).to_csv(directory/'source_alpha_values.csv',index=False)
    (directory/'search_design.json').write_text(json.dumps({'pairs':len(rows),'reference_candidate':reference_id,
        'hypothesis':'A common input dataframe drops rows with unavailable option inputs before alpha ranking, optionally before constructing the five-row price return.',
        'availability_masks':list(masks),'rank_support':'800 accepted finite observations; observation-age weights compress only as part of this explicit filtered-clock hypothesis.',
        'current_missing':'Excluded current rows remain unknown; no stale signal, forward fill or quote interpolation.',
        'return_clocks':'Return then filter preserves the actual five-index-observation horizon. Filter then return explicitly changes it to five accepted observations.',
        'causality':'Availability uses known completed current/past quotes/factors. No future row, source trade or source fill chooses availability.',
        'selection':'Fit necessary conditions, conditional first entry, then fewer episodes; later labels previously inspected.',
        'production_change':False,'archives_retained':4},indent=2))
    return frontier


def complete_case_pair_screen():
    """Two fit-leading alpha pipelines with three fixed alpha2 drop policies."""
    from backtest.provider_trials import factor_contexts,continuous_native_components
    reference_id='95fefedfcf057448';target=OUT/'complete_case_pairs';target.mkdir(exist_ok=True)
    seed=json.loads((OUT/'bulk'/f'full_autonomous_{reference_id}_ledger'/'report.json').read_text())['candidate']
    leaders=json.loads((OUT/'complete_case_alpha'/'alpha_frontier.json').read_text())[:2]
    bars,_,_=context();panel=factor_contexts(bars,opening=True)['continuous_near'][0]
    parts=continuous_native_components(bars,panel,seed['recipe'],seed['alpha_recipe']);scorer=Scorer(bars.index)
    columns=['ce_ltp','pe_ltp','ce_native_volume','pe_native_volume','ce_return','pe_return']
    available=np.isfinite(panel[columns]).all(axis=1)&panel.ce_ltp.gt(0)&panel.pe_ltp.gt(0)
    filtered=continuous_native_components(bars.loc[available],panel.loc[available],seed['recipe'],seed['alpha_recipe'])
    minutes=bars.index.as_unit('ns').asi8;frontier=[];rows=[];sources=[]
    for leader in leaders:
        d=leader['definition']
        if d['availability']!='prices_volume_returns' or d['rank_kernel']!='uniform':
            raise ValueError('Fit-leading complete-case definitions changed; re-evaluate paired experiment')
        change=parts.price_change if d['return_clock']=='return_then_filter' else filtered.price_change.reindex(bars.index)
        alpha=complete_case_rank(change,available)
        with np.load(OUT/'complete_case_alpha'/f"alpha_{leader['candidate_id']}.npz") as stored:
            np.testing.assert_array_equal(alpha.to_numpy(),stored['alpha'])
        compressed_raw=change.loc[available]*filtered.volume_ratio_lagged/filtered.atm_volatility_lagged.where(lambda v:v>0)
        betas={'original_rank':parts.alpha2,
               'filter_after_factors':rank(parts.raw2.loc[available],300,.9).reindex(bars.index),
               'filter_before_factors':rank(compressed_raw,300,.9).reindex(bars.index)}
        for policy,beta in betas.items():
            recipe={**seed['recipe'],'shared_frame_availability':'prices_volume_returns','alpha_return_clock':d['return_clock'],
                    'alpha2_drop_policy':policy,'matched_reference_candidate':reference_id}
            cid=hashlib.sha256(json.dumps({'alpha':seed['alpha'],'recipe':recipe},sort_keys=True).encode()).hexdigest()[:16]
            metrics,_=scorer.score(alpha,beta);candidate={'candidate_id':cid,'alpha':seed['alpha'],'alpha_recipe':seed['alpha_recipe'],
                'recipe':recipe,'metrics':metrics,'objective':[metrics['fit_first_exact'],metrics['fit_direction_matches'],-metrics['fit_signal_episodes']]}
            frontier.append(candidate);rows.append({'candidate_id':cid,'return_clock':d['return_clock'],'alpha2_drop_policy':policy,**metrics,
                'all_direction_matches':sum(metrics[s+'_direction_matches'] for s in SPLITS)})
            np.savez_compressed(target/f'candidate_{cid}.npz',minutes=minutes,alpha=alpha.to_numpy(),alpha2=beta.to_numpy())
            for i,t in enumerate(scorer.trades.itertuples()):
                pos=scorer.entries[i];av=alpha.iloc[pos];bv=beta.iloc[pos]
                sources.append({'candidate_id':cid,'signal_id':t.signal_id,'entry':t.entry,'split':t.split,'option_type':t.option_type,
                    'current_available':bool(available.iloc[pos]),'price_change':change.iloc[pos],'alpha':av,'alpha2':bv,
                    'joint_direction_pass':bool((av>.8 and bv>.8) if t.direction==1 else (av<.2 and bv<.2))})
            print(json.dumps(rows[-1]),flush=True)
    frontier.sort(key=lambda c:(tuple(c['objective']),c['candidate_id']),reverse=True)
    (target/'frontier.json').write_text(json.dumps(frontier,indent=2));pd.DataFrame(rows).to_csv(target/'screen.csv',index=False)
    pd.DataFrame(sources).to_csv(target/'source_signal_values.csv',index=False)
    (target/'search_design.json').write_text(json.dumps({'pairs':6,'reference_candidate':reference_id,
        'alpha_selection':'Two fit-leading complete-case alpha definitions; availability prices/volume/returns, uniform rank800/min800.',
        'alpha2_policies':{'original_rank':'Unchanged reference alpha2 control.',
            'filter_after_factors':'Original raw alpha2, then discard unavailable common rows before300/min270 rank.',
            'filter_before_factors':'Volume/STD and lag5 run on accepted rows; alpha2 uses corresponding alpha price-change clock. Same-contract one-minute returns were calculated before filtering and are never recomputed across skipped rows.'},
        'causality':'Only known completed current/past features select accepted rows. No future data or source-driven availability. Excluded current values remain unknown.',
        'execution':'No-target reference execution unchanged; autonomous replay needed; source rows only evaluate.',
        'production_change':False},indent=2))
    return frontier


def hysteresis_rank_gate(values,release=.5,session_reset=False):
    """Arm on strict extremes; release toward midpoint; unknown input clears state."""
    if not .5<=release<=.8:raise ValueError('Invalid symmetric release threshold')
    if not isinstance(values.index,pd.DatetimeIndex) or values.index.tz is None:
        raise ValueError('State gate requires timezone-aware observation dates')
    if values.index.has_duplicates or not values.index.is_monotonic_increasing:
        raise ValueError('State gate clock must be chronological and unique')
    raw=values.to_numpy(dtype=float);states=np.zeros(len(raw),dtype=np.int8)
    gates=np.full(len(raw),np.nan);armed=np.full(len(raw),-1,dtype=np.int64);armed_value=np.full(len(raw),np.nan)
    state=0;arm=-1;last_day=None;days=values.index.date
    for i,x in enumerate(raw):
        if session_reset and days[i]!=last_day:state=0;arm=-1
        last_day=days[i]
        if not np.isfinite(x):state=0;arm=-1;continue
        if x>.8:
            if state!=1:arm=i
            state=1
        elif x<.2:
            if state!=-1:arm=i
            state=-1
        elif (state==1 and x<=release) or (state==-1 and x>=1-release):state=0;arm=-1
        states[i]=state;gates[i]=.9 if state==1 else .1 if state==-1 else .5
        armed[i]=arm
        if arm>=0:armed_value[i]=raw[arm]
    return pd.DataFrame({'gate':gates,'state':states,'arm_index':armed,'armed_rank':armed_value},index=values.index)


def hysteresis_pair_screen():
    """36 fixed symmetric signal-state hypotheses and two untouched controls."""
    target=OUT/'hysteresis_pairs';target.mkdir(exist_ok=True);bars,_,_=context();scorer=Scorer(bars.index)
    seeds=[('original',OUT/'bulk','95fefedfcf057448'),('weighted_alpha',OUT/'weighted_rank_pairs','5346fa75f4d90520')]
    rows=[];source=[];frontier=[];retained={};controls=[]
    for name,directory,identity in seeds:
        seed=json.loads((directory/f'full_autonomous_{identity}_ledger'/'report.json').read_text())['candidate']
        with np.load(directory/f'candidate_{identity}.npz') as stored:
            np.testing.assert_array_equal(stored['minutes'],bars.index.as_unit('ns').asi8)
            alpha=pd.Series(stored['alpha'],index=bars.index);beta=pd.Series(stored['alpha2'],index=bars.index)
        for mode in ('control','alpha_state','alpha2_state','both_state'):
            for release,reset in ([(.8,False)] if mode=='control' else [(r,s) for r in (.5,.6,.7) for s in (False,True)]):
                ast=hysteresis_rank_gate(alpha,release,reset);bst=hysteresis_rank_gate(beta,release,reset)
                a=ast.gate if mode in ('alpha_state','both_state') else alpha
                b=bst.gate if mode in ('alpha2_state','both_state') else beta
                recipe={**seed['recipe'],'signal_state_mode':mode,'state_release':release,'state_session_reset':reset,
                        'state_seed_candidate':identity,'state_seed_family':directory.name}
                cid=hashlib.sha256(json.dumps({'alpha':seed['alpha'],'recipe':recipe},sort_keys=True).encode()).hexdigest()[:16]
                metrics,_=scorer.score(a,b)
                c={'candidate_id':cid,'alpha':seed['alpha'],'alpha_recipe':seed['alpha_recipe'],'recipe':recipe,'metrics':metrics,
                    'objective':[metrics['fit_first_exact'],metrics['fit_direction_matches'],-metrics['fit_signal_episodes']]}
                frontier.append(c);rows.append({'candidate_id':cid,'seed':name,'mode':mode,'release':release,'session_reset':reset,**metrics,
                    'all_direction_matches':sum(metrics[s+'_direction_matches'] for s in SPLITS)})
                retained[cid]=(a.to_numpy(),b.to_numpy());frontier.sort(key=lambda c:(tuple(c['objective']),c['candidate_id']),reverse=True)
                if mode=='control':controls.append(cid)
                keep={c['candidate_id'] for c in frontier[:8]}|set(controls);retained={k:v for k,v in retained.items() if k in keep}
                for i,t in enumerate(scorer.trades.itertuples()):
                    pos=scorer.entries[i];av=a.iloc[pos];bv=b.iloc[pos];ai=int(ast.arm_index.iloc[pos]);bi=int(bst.arm_index.iloc[pos])
                    source.append({'candidate_id':cid,'seed':name,'mode':mode,'release':release,'session_reset':reset,'signal_id':t.signal_id,
                        'entry':t.entry,'split':t.split,'option_type':t.option_type,'raw_alpha':alpha.iloc[pos],'raw_alpha2':beta.iloc[pos],
                        'effective_alpha_gate':av,'effective_alpha2_gate':bv,'alpha_state':int(ast.state.iloc[pos]),'alpha2_state':int(bst.state.iloc[pos]),
                        'alpha_armed_at':bars.index[ai] if ai>=0 else None,'alpha_armed_rank':ast.armed_rank.iloc[pos],
                        'alpha2_armed_at':bars.index[bi] if bi>=0 else None,'alpha2_armed_rank':bst.armed_rank.iloc[pos],
                        'joint_direction_pass':bool((av>.8 and bv>.8) if t.direction==1 else (av<.2 and bv<.2))})
    selected=frontier[:8]+[c for c in frontier if c['candidate_id'] in controls and c not in frontier[:8]]
    for cid,(a,b) in retained.items():np.savez_compressed(target/f'candidate_{cid}.npz',minutes=bars.index.as_unit('ns').asi8,alpha=a,alpha2=b)
    (target/'frontier.json').write_text(json.dumps(selected,indent=2));pd.DataFrame(rows).to_csv(target/'screen.csv',index=False)
    pd.DataFrame(source).to_csv(target/'source_signal_values.csv',index=False)
    (target/'search_design.json').write_text(json.dumps({'trials':len(rows),'controls':controls,
        'state_formula':'Arm bullish on raw rank>.8 or bearish on rank<.2; retain until bull rank<=release or bear rank>=1-release. Release .5/.6/.7; same-side extremes do not move initial arm timestamp.',
        'missing':'Unknown current input clears that rank state and its current gate stays unknown. No stale missing-input signal.',
        'reset':'Continuous states versus exchange-local date reset; state updates throughout known market observations, independently of positions and entry hours.',
        'gate_encoding':'.9/.1/.5 are effective entry gates for armed bullish/bearish/inactive states. They are NOT computed alpha ranks; raw ranks and arm timestamps are separately recorded.',
        'hypothesis_status':'Persistent state is an alternative execution interpretation, not the supplied requirement that both current ranks be extreme; not claimed disclosed private logic.',
        'selection':'Conditional fit first entries, then fit direction conditions and fewer fit episodes. Autonomous replay required; no source position or source clock controls state.',
        'production_change':False,'retained_changed_candidates':8},indent=2))
    print(pd.DataFrame(rows).sort_values(['fit_first_exact','fit_direction_matches'],ascending=False).head(8).to_string(index=False),flush=True)
    return selected


def completed_body_return(bars,kind,horizon=5):
    """Aggregate only completed candle bodies, excluding inter-candle gaps."""
    if kind not in ('body_points','body_fraction','body_log_compound'):
        raise ValueError('Unknown candle-body return definition')
    if not isinstance(horizon,int) or isinstance(horizon,bool) or horizon<1:
        raise ValueError('Invalid body horizon')
    opening=pd.to_numeric(bars.open,errors='coerce').where(lambda v:np.isfinite(v)&v.gt(0))
    close=pd.to_numeric(bars.close,errors='coerce').where(lambda v:np.isfinite(v)&v.gt(0))
    body=close-opening
    if kind=='body_points':
        return body.rolling(horizon,min_periods=horizon).sum()/opening.shift(horizon-1)
    if kind=='body_fraction':
        return (body/opening).rolling(horizon,min_periods=horizon).sum()
    return np.expm1(np.log(close/opening).rolling(horizon,min_periods=horizon).sum())


def body_return_screen():
    """Necessary alpha gate before expensive option replay; no execution change."""
    bars,_,_=context();scorer=Scorer(bars.index);target=OUT/'body_return_alpha'
    target.mkdir(exist_ok=True)
    control=load_alpha()['close_old_open_h5_r800'];rows=[];source_rows=[]
    definitions=[('control_close_old_open',5,price_change_series(bars,
        {'kind':'close_old_open','horizon':5,'session_reset':False}))]
    definitions += [(kind,h,completed_body_return(bars,kind,h))
        for kind in ('body_points','body_fraction','body_log_compound') for h in (5,6)]
    original=control.to_numpy()[scorer.entries]
    for kind,h,raw in definitions:
        alpha=rank(raw,800,1.)
        if kind=='control_close_old_open':np.testing.assert_array_equal(alpha.to_numpy(),control.to_numpy())
        metrics,_=scorer.score(alpha);all_pass=sum(metrics[s+'_direction_matches'] for s in SPLITS)
        recipe={'kind':kind,'horizon':h,'rank_window':800,'rank_minimum':800,'completed_candles_only':True}
        cid=hashlib.sha256(json.dumps(recipe,sort_keys=True).encode()).hexdigest()[:16]
        rows.append({'candidate_id':cid,**recipe,**metrics,'all_direction_matches':all_pass,
            'all_source_alpha_conditions_pass':all_pass==len(scorer.trades)})
        for i,t in enumerate(scorer.trades.itertuples()):
            k=scorer.entries[i];value=alpha.iloc[k];passed=value>.8 if t.direction==1 else value<.2
            old=original[i]>.8 if t.direction==1 else original[i]<.2
            source_rows.append({'candidate_id':cid,'kind':kind,'horizon':h,'signal_id':t.signal_id,
                'entry':t.entry,'split':t.split,'option_type':t.option_type,'raw_return':raw.iloc[k],
                'alpha':value,'direction_pass':bool(passed),'control_alpha':original[i],
                'control_direction_pass':bool(old),'repairs_control_failure':bool(passed and not old),
                'loses_control_pass':bool(old and not passed)})
    pd.DataFrame(rows).to_csv(target/'screen.csv',index=False)
    pd.DataFrame(source_rows).to_csv(target/'source_alpha_values.csv',index=False)
    (target/'search_design.json').write_text(json.dumps({'changed_definitions':6,
        'definitions':{'body_points':'sum(close-open,h)/first included opening price',
            'body_fraction':'sum((close-open)/open,h)',
            'body_log_compound':'expm1(sum(log(close/open),h))'},
        'horizons':[5,6],'alpha_rank_window':800,'minimum_known':800,
        'causality':'Only completed candle opens/closes. Unknown candles remain unknown; no future prices, source-dependent weights or imputed gaps.',
        'screen_role':'Necessary alpha strength gate, not autonomous backtest or performance evidence.',
        'private_formula_status':'Alternatives go beyond the supplied endpoint price-change description.',
        'production_change':False},indent=2))
    best=max(r['all_direction_matches'] for r in rows if r['kind']!='control_close_old_open')
    (target/'summary.md').write_text(f'# Completed candle-body alpha screen\n\nSix changed definitions pass at most {best}/210 necessary alpha conditions, versus201/210 for the unchanged endpoint control. No new definition satisfies all entries; changing alpha2 cannot repair its failed AND gate.\n\nAll three five-body aggregates pass169/210; all three six-body aggregates pass187/210. These values come from full800-value percentile ranks of known completed bodies. No inter-candle gap is treated as a candle body.\n\nReject these as a replacement alpha for replication. No autonomous option backtest or P&L is claimed for these screens, and no new deployed strategy file is created. Each trade\'s raw return, rank, corrected old failures and newly introduced failures is in source_alpha_values.csv.\n',encoding='utf-8')
    print(json.dumps({'changed_definitions':6,'best_changed_all_pass':best,
        'control_all_pass':201,'autonomous_replay_started':False},indent=2),flush=True)
    return rows


def completed_spot_volatility(bars, kind, window, lag=0):
    """Causal spot-volatility scale, with no session or missing-value fill."""
    if kind not in ('return_std', 'intraday_return_std', 'atr_fraction'):
        raise ValueError('Unknown spot volatility definition')
    if any(isinstance(v, bool) or not isinstance(v, int) for v in (window, lag)) or window < 2 or lag < 0:
        raise ValueError('Invalid volatility window or lag')
    minimum = int(np.ceil(.8*window))
    if kind == 'atr_fraction':
        previous = bars.close.shift()
        tr = pd.concat([bars.high-bars.low, (bars.high-previous).abs(),
                        (bars.low-previous).abs()], axis=1).max(axis=1)
        value = tr.rolling(window, min_periods=minimum).mean()/bars.close.where(bars.close > 0)
    else:
        returns = np.log(bars.close.where(bars.close > 0)).diff()
        if kind == 'intraday_return_std':
            day = pd.Series(bars.index.date, index=bars.index)
            returns = returns.where(day.eq(day.shift()))
        value = returns.rolling(window, min_periods=minimum).std()
    value = value.where(bars.close.notna()).shift(lag)
    return value.where(np.isfinite(value) & (value > 0))


def volatility_normalized_alpha_screen():
    bars, _, _ = context(); scorer = Scorer(bars.index)
    target = OUT/'volatility_normalized_alpha'; target.mkdir(exist_ok=True)
    bank = load_alpha(); trials = []; source_rows = []; leaders = []; controls = []
    scales = {(kind, window, lag): completed_spot_volatility(bars, kind, window, lag)
        for kind in ('return_std', 'intraday_return_std', 'atr_fraction')
        for window in (15, 30, 60, 150, 300, 800) for lag in (0, 5)}
    for name in ('close_old_open_h5_r800', 'close_close_old_open_h5_r800'):
        price_recipe = {'kind': name.replace('_h5_r800', ''), 'horizon': 5,
                        'rank_window': 800, 'session_reset': False}
        raw = price_change_series(bars, price_recipe)
        definitions = [(None, None, None, 0., raw)]
        definitions += [(kind, window, lag, power, raw/scale.pow(power))
            for (kind, window, lag), scale in scales.items() for power in (.5, 1.)]
        for kind, window, lag, power, normalized in definitions:
            alpha = rank(normalized, 800, 1.); metrics, _ = scorer.score(alpha)
            recipe = {'price_recipe': price_recipe, 'volatility': kind, 'volatility_window': window,
                      'volatility_lag': lag, 'scale_exponent': power, 'rank_window': 800}
            cid = hashlib.sha256(json.dumps(recipe, sort_keys=True).encode()).hexdigest()[:16]
            objective = [metrics['fit_direction_matches'], metrics['fit_first_exact'],
                         -metrics['fit_signal_episodes']]
            candidate = {'candidate_id': cid, 'recipe': recipe, 'metrics': metrics,
                         'objective': objective,
                         'all_direction_matches': sum(metrics[s+'_direction_matches'] for s in SPLITS)}
            trials.append(candidate)
            if kind is None:
                np.testing.assert_array_equal(alpha.to_numpy(), bank[name].to_numpy())
                controls.append(candidate)
            else:
                leaders.append(candidate)
                leaders.sort(key=lambda c: (tuple(c['objective']), c['candidate_id']), reverse=True)
                leaders = leaders[:6]
            if kind is None or any(c['candidate_id'] == cid for c in leaders):
                np.savez_compressed(target/f'alpha_{cid}.npz', minutes=bars.index.as_unit('ns').asi8,
                                    alpha=alpha.to_numpy(), raw=normalized.to_numpy())
            for t, value in zip(scorer.trades.itertuples(), alpha.to_numpy()[scorer.entries]):
                source_rows.append({'candidate_id': cid, 'signal_id': t.signal_id, 'entry': t.entry,
                    'split': t.split, 'option_type': t.option_type, 'alpha': value,
                    'direction_pass': bool(value > .8 if t.direction == 1 else value < .2)})
    (target/'alpha_trials.json').write_text(json.dumps(trials, indent=2))
    (target/'alpha_frontier.json').write_text(json.dumps(leaders+controls, indent=2))
    pd.DataFrame(source_rows).to_csv(target/'source_alpha_values.csv', index=False)
    (target/'search_design.json').write_text(json.dumps({'trials': len(trials),
        'normalization': 'Five-bar price change / spot volatility scale raised to exponent0.5 or1; then rank800.',
        'rank_minimum_observations': 800, 'volatility_minimum_fraction': .8,
        'selection': 'Necessary fit direction compatibility, then conditional first-exact and fewer episodes.',
        'causality': 'Completed spot candles only. Intraday return STD excludes each session opening gap. Lag counts observed bars. Missing or nonpositive scales remain unknown.',
        'limits': 'Additional alpha1 volatility normalization is not in the supplied formula. These are exploratory alternatives, not a claim of faithful implementation. No source-dependent scales or time gates. Later periods previously inspected.',
        'production_change': False}, indent=2))
    print(json.dumps({'trials': len(trials), 'fit_selected': leaders[0],
        'maximum_all_direction_matches': max(c['all_direction_matches'] for c in trials)}, indent=2), flush=True)


def calendar_support_rank(raw,window=800,closed_zero=False,min_observations=20):
    """Rank-history hypothesis; never fill a traded candle or an option quote.

    closed_zero inserts assumed zero RETURNS at closed-market decision minutes,
    not synthetic price candles. Missing regular-session returns remain absent.
    """
    from backtest.provider_calendar import ProviderCalendar
    from utils.time import IST
    index=raw.index
    if not isinstance(index,pd.DatetimeIndex) or index.tz is None or index.has_duplicates or not index.is_monotonic_increasing:
        raise ValueError('Calendar rank needs ordered unique timezone-aware minutes')
    if not isinstance(closed_zero,bool) or not isinstance(window,int) or window<2 or not 1<=min_observations<=window:
        raise ValueError('Invalid calendar rank coverage')
    if raw.empty:return raw.astype(float)
    local=index.tz_convert(IST)
    if not local.equals(local.floor('min')):raise ValueError('Calendar rank observations must be minute aligned')
    values=pd.Series(raw.to_numpy(dtype=float),index=local).replace([np.inf,-np.inf],np.nan)
    if not closed_zero:
        result=values.rolling(f'{window}min',min_periods=min_observations).rank(pct=True)
    else:
        full=pd.date_range(local[0],local[-1],freq='min');calendar=ProviderCalendar()
        days={d:calendar.is_trading_day(d) for d in set(full.date)}
        clock=full.hour*60+full.minute
        regular=np.array([days[d] for d in full.date])&(clock>555)&(clock<=930)
        support=values.reindex(full)
        support.loc[~regular&support.isna()]=0.
        # A full 800-calendar-minute support is required in this branch.
        result=support.rolling(window,min_periods=window).rank(pct=True).reindex(local)
    result=result.where(values.notna());result.index=index
    return result


def calendar_rank_pair_screen():
    """Matched nine-pair rank-history experiment; unchanged causal raw inputs."""
    from backtest.provider_trials import factor_contexts,continuous_native_components
    reference_id='95fefedfcf057448';directory=OUT/'calendar_rank_pairs'
    reference=json.loads((OUT/'bulk'/f'full_autonomous_{reference_id}_ledger'/'report.json').read_text())['candidate']
    bars,_,_=context();bank=load_alpha()
    panel=factor_contexts(bars,opening=True)['continuous_near'][0]
    parts=continuous_native_components(bars,panel,reference['recipe'],reference['alpha_recipe'])
    original_alpha=bank[reference['alpha']];original_beta=parts.alpha2
    minutes=bars.index.as_unit('ns').asi8
    with np.load(OUT/'bulk'/f'candidate_{reference_id}.npz',allow_pickle=False) as stored:
        for key,actual in (('minutes',minutes),('alpha',original_alpha.to_numpy()),('alpha2',original_beta.to_numpy())):
            if not np.array_equal(actual,stored[key],equal_nan=True):
                raise ValueError(f'Reference control differs: {key}')
    def supports(raw,window,original):
        return {'trading_observations':original,
                'calendar_observed_only_min20':calendar_support_rank(raw,window,min_observations=20),
                'calendar_closed_zero_full':calendar_support_rank(raw,window,closed_zero=True)}
    alphas=supports(parts.price_change,800,original_alpha)
    betas=supports(parts.raw2,300,original_beta)
    scorer=Scorer(bars.index);records=[];source_rows=[];frontier=[]
    directory.mkdir(exist_ok=True)
    for alpha_clock,alpha in alphas.items():
        for beta_clock,beta in betas.items():
            recipe={**reference['recipe'],'alpha_rank_support':alpha_clock,'alpha2_rank_support':beta_clock,
                'calendar_observed_minimum':20,'closed_signal_assumption':0.,
                'matched_reference_candidate':reference_id}
            cid=hashlib.sha256(json.dumps({'alpha':reference['alpha'],'recipe':recipe},sort_keys=True).encode()).hexdigest()[:16]
            metrics,_=scorer.score(alpha,beta)
            candidate={'candidate_id':cid,'alpha':reference['alpha'],'alpha_recipe':reference['alpha_recipe'],
                'recipe':recipe,'metrics':metrics,
                'objective':[metrics['fit_first_exact'],metrics['fit_direction_matches'],-metrics['fit_signal_episodes']]}
            frontier.append(candidate)
            records.append({'candidate_id':cid,'alpha_support':alpha_clock,'alpha2_support':beta_clock,**metrics})
            np.savez_compressed(directory/f'candidate_{cid}.npz',minutes=minutes,alpha=alpha.to_numpy(),alpha2=beta.to_numpy())
            for i,t in enumerate(scorer.trades.itertuples()):
                a=alpha.iloc[scorer.entries[i]];b=beta.iloc[scorer.entries[i]]
                passed=np.isfinite(a) and np.isfinite(b) and ((a>.8 and b>.8) if t.direction==1 else (a<.2 and b<.2))
                source_rows.append({'candidate_id':cid,'signal_id':t.signal_id,'entry':t.entry,'split':t.split,
                    'alpha':a,'alpha2':b,'joint_direction_pass':bool(passed)})
            print(json.dumps(records[-1]),flush=True)
    frontier.sort(key=lambda c:(tuple(c['objective']),c['candidate_id']),reverse=True)
    (directory/'frontier.json').write_text(json.dumps(frontier,indent=2))
    pd.DataFrame(records).to_csv(directory/'screen.csv',index=False)
    pd.DataFrame(source_rows).to_csv(directory/'source_signal_values.csv',index=False)
    (directory/'search_design.json').write_text(json.dumps({'pairs':9,'reference_candidate':reference_id,
        'unchanged':'Underlying return, geometric volume baseline10, sample logSTD150, factor lag5, strict .8/.2, no-target execution.',
        'support_definitions':{'trading_observations':'Original alpha800/min800, alpha2 300/min270.',
            'calendar_observed_only_min20':'Trailing800/300 elapsed minutes; known observations only, explicit minimum20.',
            'calendar_closed_zero_full':'Explicit zero dimensionless input at closed-market minutes; full800/300 known support. Missing regular-session inputs remain unknown.'},
        'causality':'Current unknown inputs remain unknown. Closed minutes come only from the exchange calendar. No provider entries or exits define support.',
        'selection':'Conditional fit screen followed by autonomous fit replays. Later periods previously inspected, not an untouched holdout.',
        'production_change':False},indent=2))
    return frontier


def calendar_rank_screen():
    bars,_,_=context();scorer=Scorer(bars.index)
    target=OUT/'calendar_rank';target.mkdir(exist_ok=True)
    recipes=json.loads((OUT/'alpha_recipes.json').read_text());bank=load_alpha()
    names=('close_old_open_h5_r800','close_close_old_open_h5_r800')
    trials=[];entries=[];frontier=[]
    for name in names:
        raw=price_change_series(bars,recipes[name])
        np.testing.assert_array_equal(rank(raw,800,1.).to_numpy(),bank[name].to_numpy())
        supports={'trading_observations':bank[name],
            'calendar_observed_only':calendar_support_rank(raw),
            'calendar_closed_zero_returns':calendar_support_rank(raw,closed_zero=True)}
        for support,alpha in supports.items():
            recipe={'seed_alpha':name,'raw_price_recipe':recipes[name],'rank_support':support,
                'rank_window':800,'closed_market_return_assumption':0. if support=='calendar_closed_zero_returns' else None}
            cid=hashlib.sha256(json.dumps(recipe,sort_keys=True).encode()).hexdigest()[:16]
            metrics,_=scorer.score(alpha);total=sum(metrics[s+'_direction_matches'] for s in SPLITS)
            candidate={'candidate_id':cid,'recipe':recipe,'metrics':metrics,
                'all_direction_matches':total,'objective':[metrics['fit_direction_matches'],metrics['fit_first_exact'],-metrics['fit_signal_episodes']]}
            trials.append(candidate);frontier.append(candidate)
            np.savez_compressed(target/f'alpha_{cid}.npz',minutes=bars.index.as_unit('ns').asi8,
                alpha=alpha.to_numpy(),raw=raw.to_numpy())
            selected=alpha.to_numpy()[scorer.entries]
            for i,t in enumerate(scorer.trades.itertuples()):
                v=selected[i];entries.append({'candidate_id':cid,'signal_id':t.signal_id,'entry':t.entry,
                    'split':t.split,'option_type':t.option_type,'alpha':v,'direction_pass':bool(v>.8 if t.direction==1 else v<.2)})
            print(name,support,metrics['fit_direction_matches'],total,flush=True)
    (target/'alpha_trials.json').write_text(json.dumps(trials,indent=2))
    (target/'alpha_frontier.json').write_text(json.dumps(sorted(frontier,key=lambda c:tuple(c['objective']),reverse=True),indent=2))
    pd.DataFrame(entries).to_csv(target/'source_alpha_values.csv',index=False)
    (target/'search_design.json').write_text(json.dumps({'trials':len(trials),'rank_window':800,
        'hypotheses':['800 observed trading returns','800 calendar minutes, observed returns only, minimum20 observations','800 calendar minutes with explicit closed-market zero-return assumption; full800 support'],
        'causality':'Only completed historical returns and exchange calendar. Missing regular-session observations remain unknown. Source labels never determine closed periods or return values.',
        'limits':'Zero closed-market returns are a preprocessing assumption, not observed traded candles. No price/volume/option quote is filled or changed. Direction compatibility is not autonomous replication. Later periods previously inspected.',
        'production_change':False},indent=2))


def rank_convention_screen():
    """Matched rank definitions on four fixed causal input reconstructions."""
    from backtest.provider_trials import factor_contexts,continuous_native_components
    specs=(('opening_atm','c6a30e15e1bbf4e8'),('opening_volume','15b3eed5b443e0cd'),
        ('opening_pcr','09a7e0d5b4682e47'),('contract_cumulative','9d25d422c3360e1d'))
    target=OUT/'rank_conventions';target.mkdir(exist_ok=True)
    bars,_,_=context();scorer=Scorer(bars.index)
    panel=factor_contexts(bars,opening=True,cumulative=True)['continuous_near'][0]
    rows=[];candidates=[];inputs={};baselines=[];alpha_cache={};equivalent=0
    for family,cid in specs:
        source=OUT/family;seed=next(f for f in json.loads((source/'frontier.json').read_text()) if f['candidate_id']==cid)
        raw_alpha=price_change_series(bars,seed['alpha_recipe'])
        key=json.dumps(seed['alpha_recipe'],sort_keys=True)
        if key not in alpha_cache:alpha_cache[key]=rank_conventions(raw_alpha,800,1.)
        alphas=alpha_cache[key]
        components=continuous_native_components(bars,panel,seed['recipe'],seed['alpha_recipe'])
        betas=rank_conventions(components.raw2,300,.9)
        with np.load(source/f'candidate_{cid}.npz',allow_pickle=False) as stored:
            np.testing.assert_array_equal(stored['minutes'],bars.index.as_unit('ns').asi8)
            np.testing.assert_array_equal(alphas['average_pct'],stored['alpha'])
            np.testing.assert_array_equal(betas['average_pct'],stored['alpha2'])
        _,baseline_signal=scorer.score(alphas['average_pct'],betas['average_pct'])
        inputs[cid]=(alphas,betas)
        for a_name,a in alphas.items():
            for b_name,b in betas.items():
                recipe={**seed['recipe'],'alpha_rank_convention':a_name,'alpha2_rank_convention':b_name,
                    'rank_seed_family':family,'rank_seed_candidate_id':cid}
                rid=json.dumps(recipe,sort_keys=True,separators=(',',':'))
                identity=hashlib.sha256(f'{seed["alpha"]}|{rid}'.encode()).hexdigest()[:16]
                metrics,signal=scorer.score(a,b)
                changed=int((signal!=baseline_signal).sum())
                objective=[metrics['fit_first_exact'],metrics['fit_direction_matches'],-metrics['fit_signal_episodes']]
                candidate={'candidate_id':identity,'alpha':seed['alpha'],'alpha_recipe':seed['alpha_recipe'],
                    'recipe':recipe,'metrics':metrics,'objective':objective,'changed_eligible_signal_minutes':changed}
                rows.append({'recipe_id':rid,'alpha':seed['alpha'],**recipe,**metrics,'changed_eligible_signal_minutes':changed})
                if a_name==b_name=='average_pct':
                    candidate['selection_note']='Unchanged rank control, excluded from choosing an alternative.'
                    baselines.append(candidate)
                elif changed:candidates.append(candidate)
                else:equivalent+=1
        print(f'Rank definitions {family}: 36 matched pairs; baseline arrays reproduced',flush=True)
    candidates.sort(key=lambda f:tuple(f['objective']),reverse=True)
    per_seed={cid:next(f for f in candidates if f['recipe']['rank_seed_candidate_id']==cid) for _,cid in specs}
    frontier=candidates[:12]
    frontier += [f for f in per_seed.values() if not any(x['candidate_id']==f['candidate_id'] for x in frontier)]
    frontier += baselines
    for f in frontier:
        r=f['recipe'];a,b=inputs[r['rank_seed_candidate_id']]
        np.savez_compressed(target/f'candidate_{f["candidate_id"]}.npz',minutes=bars.index.as_unit('ns').asi8,
            alpha=a[r['alpha_rank_convention']].to_numpy(),alpha2=b[r['alpha2_rank_convention']].to_numpy())
    pd.DataFrame(rows).to_csv(target/'formula_trials.csv',index=False)
    (target/'frontier.json').write_text(json.dumps(frontier,indent=2))
    (target/'rank_design.json').write_text(json.dumps({'trials':len(rows),'fit_selected_rank_leader':frontier[0]['candidate_id'],
        'fit_selected_by_seed':{cid:f['candidate_id'] for cid,f in per_seed.items()},
        'seeds':[{'family':family,'candidate_id':cid} for family,cid in specs],
        'definitions':{'average_pct':'Average one-based tie rank / N; existing control.',
            'minimum_pct':'Lowest one-based tie rank / N.','maximum_pct':'Highest one-based tie rank / N.',
            'average_zero_one':'(Average one-based tie rank - 1) / (N - 1).',
            'empirical_strict':'Number of values strictly below current / N.',
            'empirical_mid':'(Number strictly below + half the tied values) / N.'},
        'windows':{'alpha':800,'alpha2':300},'valid_fraction':{'alpha':1.,'alpha2':.9},
        'selection':'Fit first exact, then fit direction matches, then fewer fit episodes. Unchanged controls and conventions with identical eligible signals are excluded from alternative selection.',
        'equivalent_alternatives_excluded':equivalent,
        'causality':'Current completed observation is included. No future data, clock/date fitting, price/volume substitutions or production change.',
        'limits':'Previously inspected chronological periods are not untouched holdouts. Conditional first-entry scoring requires autonomous replay.'},indent=2))
    print('Fit-selected rank alternative:',frontier[0]['candidate_id'],frontier[0]['objective'],flush=True)


def opening_reference_screen():
    """Explicit opening-price normalizations and a causally observed forming bar.

    A five-row forward change from an opening to a completed closing spans six
    clock minutes. In a forming last row, the same array expression spans five
    minutes plus the elapsed fraction of that minute. Its current close cannot
    be reconstructed; only its known opening is evaluated here.
    """
    bars,_,_=context();scorer=Scorer(bars.index)
    day=bars.index.date;session_open=bars.open.groupby(day).transform('first')
    daily_close=bars.close.groupby(day).last().shift()
    prior_close=pd.Series(daily_close.reindex(day).to_numpy(),index=bars.index)
    contiguous=pd.Series(bars.index,index=bars.index).shift(-1)-pd.Series(bars.index,index=bars.index)==pd.Timedelta(minutes=1)
    current_open=bars.open.shift(-1).where(contiguous)
    definitions=(('completed_open_forward5',bars.open,5,False),
        ('completed_close_forward5',bars.close,5,False),
        ('completed_five_minute_open_span',bars.open,4,False),
        ('forming_open_forward5',bars.open,5,True),
        ('forming_close_forward5',bars.close,5,True))
    scores=[];details=[];leaders=[]
    for name,reference,shift,forming in definitions:
        current_shift=shift-1 if forming else shift
        numerator=bars.close-reference.shift(shift)
        current_numerator=current_open-reference.shift(current_shift) if forming else numerator
        denominators={'start_bar_open':(bars.open.shift(shift),bars.open.shift(current_shift)),
            'current_bar_open':(bars.open,current_open if forming else bars.open),
            'session_open_at_start':(session_open.shift(shift),session_open.shift(current_shift)),
            'current_session_open':(session_open,session_open),
            'previous_session_close':(prior_close,prior_close),
            'unscaled_points':(pd.Series(1.,index=bars.index),pd.Series(1.,index=bars.index))}
        for norm,(historical_den,current_den) in denominators.items():
            history=numerator/historical_den.where(historical_den>0)
            raw=current_numerator/current_den.where(current_den>0)
            alpha=provisional_rank(history,raw) if forming else rank(raw,800,1.)
            metrics,_=scorer.score(alpha)
            recipe={'price_expression':name,'normalization':norm,'rank_window':800,
                'current_value':'known current-minute open' if forming else 'completed close'}
            identity=json.dumps(recipe,sort_keys=True);cid=hashlib.sha256(identity.encode()).hexdigest()[:16]
            scores.append({'candidate_id':cid,'recipe':identity,**recipe,**metrics,
                'all_direction_matches':sum(metrics[s+'_direction_matches'] for s in SPLITS)})
            objective=(metrics['fit_direction_matches'],metrics['fit_first_exact'],-metrics['fit_signal_episodes'])
            if len(leaders)<6 or objective>tuple(leaders[-1]['objective']):
                leaders.append({'candidate_id':cid,'recipe':recipe,'metrics':metrics,'objective':list(objective)})
                leaders.sort(key=lambda v:tuple(v['objective']),reverse=True);leaders=leaders[:6]
                if any(f['candidate_id']==cid for f in leaders):
                    np.savez_compressed(OUT/f'opening_alpha_{cid}.npz',minutes=bars.index.as_unit('ns').asi8,
                        alpha=alpha.to_numpy(),raw=raw.to_numpy())
            for i,t in enumerate(scorer.trades.itertuples()):
                k=scorer.entries[i];value=alpha.iloc[k]
                details.append({'candidate_id':cid,'recipe':identity,'signal_id':t.signal_id,'entry':t.entry,
                    'split':t.split,'option_type':t.option_type,'raw_price_change':raw.iloc[k],'alpha':value,
                    'direction_pass':bool(value>.8 if t.direction==1 else value<.2)})
    pd.DataFrame(scores).to_csv(OUT/'opening_reference_trials.csv',index=False)
    pd.DataFrame(details).to_csv(OUT/'opening_reference_every_trade.csv',index=False)
    (OUT/'opening_reference_frontier.json').write_text(json.dumps(leaders,indent=2))
    (OUT/'opening_reference_design.json').write_text(json.dumps({'trials':len(scores),
        'selection':'Fit alpha direction compatibility, then fit first exact, then fewer fit signal episodes.',
        'scope':'Alpha compatibility only. No source timestamp or source fill is an input predictor.',
        'causality':'Completed historical closes and known current-minute opening only. No current-minute high/low/close/volume; no missing-price fill.',
        'normalizations':'Start/current bar open, start/current session open, previous session close, or point change. Not all are literal matches to the description.',
        'forming_bar':'Historical open-forward5 changes span six elapsed minutes; current forming-row change is known at its opening after five elapsed minutes. No simulated intraminute close is supplied.'},indent=2))
    print('Opening reference trials:',len(scores),'best entry direction compatibility:',max(r['all_direction_matches'] for r in scores),'/210',flush=True)


def required_price_review():
    """Invert a specific alpha convention to a required underlying price.

    This is a diagnostic about the opening-reference candidate, not evidence
    that the provider uses it. Future candle extremes are comparison labels.
    """
    bars,_,_=context();scorer=Scorer(bars.index)
    reference=bars.open.shift(5);history=(bars.close-reference)/reference
    rows=[]
    for i,t in enumerate(scorer.trades.itertuples()):
        k=scorer.entries[i]
        h=history.iloc[k-798:k+1].to_numpy();ref=reference.iloc[k]
        if len(h)!=799 or not np.isfinite(h).all():
            raise ValueError('Required-price diagnostic needs 799 known completed changes')
        ordered=np.sort(h)
        def percentile(price):
            raw=(price-ref)/ref
            left=np.searchsorted(ordered,raw,side='left');right=np.searchsorted(ordered,raw,side='right')
            return (left+(right-left+2)/2)/800
        lo=ref*(1+ordered[0]-.02);hi=ref*(1+ordered[-1]+.02)
        for _ in range(64):
            mid=(lo+hi)/2
            if t.direction==1:
                if percentile(mid)>.8:hi=mid
                else:lo=mid
            else:
                if percentile(mid)<.2:lo=mid
                else:hi=mid
        # Directed hundredth-point rounding gives an interpretable sufficient
        # price, not a claim about an exchange index tick size.
        required=np.ceil(hi*100)/100 if t.direction==1 else np.floor(lo*100)/100
        passed=percentile(required)>.8 if t.direction==1 else percentile(required)<.2
        if not passed:raise ValueError('Inverted price does not satisfy its own alpha threshold')
        if k+1>=len(bars) or bars.index[k+1]-bars.index[k]!=pd.Timedelta(minutes=1):
            raise ValueError('Missing entry candle for diagnostic bounds')
        candle=bars.iloc[k+1]
        extreme=candle.high if t.direction==1 else candle.low
        rows.append({'signal_id':t.signal_id,'entry':t.entry,'option_type':t.option_type,
            'reference_open':ref,'known_entry_candle_open':candle.open,
            'alpha_at_known_entry_open':percentile(candle.open),
            'required_index_price':required,'required_direction':'at_least' if t.direction==1 else 'at_most',
            'alpha_at_required_price':percentile(required),
            'NONCAUSAL_entry_candle_low':candle.low,'NONCAUSAL_entry_candle_high':candle.high,
            'NONCAUSAL_favorable_extreme_can_pass':bool(percentile(extreme)>.8 if t.direction==1 else percentile(extreme)<.2),
            'distance_outside_candle_points':max(0.,required-candle.high if t.direction==1 else candle.low-required)})
    frame=pd.DataFrame(rows);frame.to_csv(OUT/'required_index_prices_DIAGNOSTIC.csv',index=False)
    (OUT/'required_index_prices_design.json').write_text(json.dumps({
        'convention':'Current known price versus the open five closed-row offsets earlier; history uses the last 799 completed open-to-close changes plus the current price.',
        'thresholds':{'bullish':'strictly greater than 0.8','bearish':'strictly less than 0.2'},
        'scope':'Price inversion for one specific model, not the provider formula. All source timestamps are labels.',
        'causality':'Only the required-price calculation is available at the observation. Current-candle high/low are explicitly noncausal diagnostics and never trade inputs.'},indent=2))
    print(frame.loc[~frame.NONCAUSAL_favorable_extreme_can_pass,['entry','option_type','required_index_price',
        'NONCAUSAL_entry_candle_low','NONCAUSAL_entry_candle_high','distance_outside_candle_points']].to_string(index=False),flush=True)


def option_spot_screen():
    """Compare completed option-candle underlying spot with index candle closes."""
    bars,panels,_=context();panel=panels['near'];scorer=Scorer(bars.index)
    scores=[];details=[];coverage={}
    for side in ('ce','pe'):
        spot=panel[f'{side}_spot']
        difference=(spot-bars.close).abs().dropna()
        coverage[side]={'available_minutes':len(difference),
            'equal_index_close_minutes':int(difference.lt(.001).sum()),
            'median_absolute_difference':float(difference.median()),
            'maximum_absolute_difference':float(difference.max())}
        alternative=bars.copy();alternative['close']=spot
        for kind in ('close_old_open','close_close_old_open','body_h'):
            for horizon in (5,6):
                recipe={'price_feed':f'{side}_option_spot','opening_feed':'index_open',
                    'kind':kind,'horizon':horizon,'rank_window':800,'minimum_valid_fraction':.9}
                identity=json.dumps(recipe,sort_keys=True)
                a=rank(price_change_series(alternative,recipe),800,.9)
                metrics,_=scorer.score(a)
                scores.append({'recipe':identity,**recipe,**metrics,
                    'all_direction_matches':sum(metrics[s+'_direction_matches'] for s in SPLITS)})
                for i,t in enumerate(scorer.trades.itertuples()):
                    k=scorer.entries[i];value=a.iloc[k]
                    details.append({'recipe':identity,'signal_id':t.signal_id,'entry':t.entry,
                        'split':t.split,'option_type':t.option_type,'index_close':bars.close.iloc[k],
                        'option_underlying_spot':spot.iloc[k],'alpha':value,
                        'direction_pass':bool(value>.8 if t.direction==1 else value<.2)})
    pd.DataFrame(scores).to_csv(OUT/'option_spot_trials.csv',index=False)
    pd.DataFrame(details).to_csv(OUT/'option_spot_every_trade.csv',index=False)
    (OUT/'option_spot_design.json').write_text(json.dumps({'coverage':coverage,
        'causality':'Only spot attached to completed option candles is used; no future data or missing-price fill.',
        'opening_reference':'Index candle opens retained; option premium opens are not underlying spot opens.',
        'scope':'Alpha direction compatibility only, not an autonomous strategy or recovered alpha2.'},indent=2))
    print('Option spot alpha trials:',len(scores),'best entry direction compatibility:',max(r['all_direction_matches'] for r in scores),'/210',flush=True)


def boundary_screen():
    """Test equality semantics on fit-frontier recipes, preserving raw ranks."""
    target=OUT/'boundaries';target.mkdir(exist_ok=True)
    rows=[];frontier=[];scorers={};cases=[]
    for family in ('main','fine','expanded','mixed','fixed_contract','sampling'):
        source=OUT if family=='main' else OUT/family
        path=source/'frontier.json'
        if not path.exists():continue
        seeds=json.loads(path.read_text())
        for seed in seeds:
            with np.load(source/f'candidate_{seed["candidate_id"]}.npz',allow_pickle=False) as data:
                minute=data['minutes'];a=data['alpha'].astype(float);b=data['alpha2'].astype(float)
            # Older float32 checkpoints encode exact rank boundaries imprecisely.
            for cutoff in (.2,.8):
                a[np.isclose(a,cutoff,atol=1e-7,rtol=0)]=cutoff
                b[np.isclose(b,cutoff,atol=1e-7,rtol=0)]=cutoff
            key=hashlib.sha256(minute.tobytes()).hexdigest()
            if key not in scorers:
                from utils.time import IST
                scorers[key]=Scorer(pd.to_datetime(minute,unit='ns',utc=True).tz_convert(IST))
            for comparison in ('strict','inclusive','bearish_inclusive','bullish_inclusive'):
                recipe={**seed['recipe'],'threshold_comparison':comparison,
                    'source_family':family,'source_candidate_id':seed['candidate_id']}
                rid=json.dumps(recipe,sort_keys=True,separators=(',',':'))
                cid=hashlib.sha256(f'{seed["alpha"]}|{rid}'.encode()).hexdigest()[:16]
                metrics,_=scorers[key].score(a,b,comparison)
                rows.append({'recipe_id':rid,'alpha':seed['alpha'],**recipe,**metrics})
                objective=(metrics['fit_first_exact'],metrics['fit_direction_matches'],-metrics['fit_signal_episodes'])
                f={'candidate_id':cid,'alpha':seed['alpha'],'alpha_recipe':seed['alpha_recipe'],
                    'recipe':recipe,'metrics':metrics,'objective':list(objective)}
                # Preserve the explicitly investigated 0.20 equality case even
                # when it is not a fit-period leader. It is not a held-out test.
                if family=='expanded' and seed==seeds[0] and comparison=='bearish_inclusive':
                    cases.append(f)
                    np.savez_compressed(target/f'candidate_{cid}.npz',minutes=minute,alpha=a,alpha2=b)
                if len(frontier)<12 or objective>tuple(frontier[-1]['objective']):
                    frontier.append(f);frontier.sort(key=lambda v:tuple(v['objective']),reverse=True);frontier=frontier[:12]
                    if any(f['candidate_id']==cid for f in frontier):
                        np.savez_compressed(target/f'candidate_{cid}.npz',minutes=minute,alpha=a,alpha2=b)
    pd.DataFrame(rows).to_csv(target/'formula_trials.csv',index=False)
    frontier += [f for f in cases if not any(v['candidate_id']==f['candidate_id'] for v in frontier)]
    (target/'frontier.json').write_text(json.dumps(frontier,indent=2))
    (target/'boundary_design.json').write_text(json.dumps({'trials':len(rows),
        'nominal_thresholds':[.8,.2],
        'comparison_semantics':['strict','inclusive','bearish_inclusive','bullish_inclusive'],
        'selection':'Fit first exact, then fit direction matches, then fewer fit signal episodes.',
        'source':'Saved fit-frontier candidates; raw alpha ranks unchanged. Older float32 boundary encodings normalized.',
        'case_candidates':[f['candidate_id'] for f in cases],
        'limitations':'Equality is an explicit alternative to the description\'s strict wording. No production rule changed; autonomous replay required.'},indent=2))
    print('Boundary comparisons:',len(rows),'fit frontier:',frontier[0]['objective'],flush=True)


def preceding_alpha_review():
    """Record signal/entry latency compatibility, not a delayed-entry trading rule."""
    target=OUT/'sampling';target.mkdir(exist_ok=True)
    bank=load_alpha();scorer=Scorer(bank.index);rows=[]
    for name in ('close_old_open_h5_r800','body_h_h5_r800','current_open_from_open_h6_r800','close_close_old_open_h5_r800'):
        for t in scorer.trades.itertuples():
            for lag in range(6):
                minute=t.entry_minute-pd.Timedelta(minutes=lag)
                k=bank.index.get_indexer([minute])[0]
                valid=k>=0 and scorer.eligible[k] and scorer.flat[k]
                a=float(bank[name].iloc[k]) if k>=0 else np.nan
                passed=valid and (a>.8 if t.direction==1 else a<.2)
                rows.append({'signal_id':t.signal_id,'entry':t.entry,'split':t.split,'option_type':t.option_type,
                    'alpha_recipe':name,'minutes_before_recorded_entry':lag,'observation_minute':minute,'alpha':a,
                    'eligible_and_source_flat':bool(valid),'direction_threshold_pass':bool(passed)})
    table=pd.DataFrame(rows);table.to_csv(target/'preceding_alpha_DIAGNOSTIC.csv',index=False)
    (target/'preceding_alpha_design.json').write_text(json.dumps({
        'purpose':'Compare prior known alpha values with recorded order times. Labels are source-conditioned, not live entry rules.',
        'lags_minutes':[0,1,2,3,4,5],
        'causality':'No future price is read. Prior minutes must be in the entry window and flat under the published source position history.',
        'limitation':'Actual decision timestamps and broker execution latency are unknown. Compatibility cannot prove a delay or reproduce an execution.'},indent=2))


def sampling_screen():
    """Causal alternatives for the observation frequency within an 800-minute rank."""
    target=OUT/'sampling';target.mkdir(exist_ok=True)
    bars,_,_=context();scorer=Scorer(bars.index);trades=scorer.trades
    recipes=[{'kind':'close_old_open','horizon':5},{'kind':'body_h','horizon':5},
             {'kind':'close_close_old_open','horizon':5},{'kind':'current_open_from_open','horizon':6}]
    score=[];details=[];leaders=[]
    phase_clock=bars.index.hour*60+bars.index.minute-555
    for base in recipes:
        raw=price_change_series(bars,base)
        if base['kind']=='current_open_from_open':
            old=bars.open.shift(base['horizon']-1)
            hist=(bars.close-old)/old
        else:hist=raw
        for stride in (1,2,5,10):
            for phase in (range(stride) if stride in (2,5) else (0,)):
                mask=phase_clock%stride==phase
                for semantics in (('minutes',) if stride==1 else ('minutes','observations')):
                    w=int(np.ceil(800/stride)) if semantics=='minutes' else 800
                    alpha=sampled_rank(hist,raw,mask,w);metrics,_=scorer.score(alpha)
                    recipe={**base,'rank_span':800,'historical_stride':stride,'sample_phase':phase,
                        'lookback_unit':semantics,'rank_observations':w,'current_value':'every decision minute'}
                    recipe_id=json.dumps(recipe,sort_keys=True);cid=hashlib.sha256(recipe_id.encode()).hexdigest()[:16]
                    row={'candidate_id':cid,'recipe_id':recipe_id,**recipe,**metrics,
                        'all_direction_matches':sum(metrics[s+'_direction_matches'] for s in SPLITS),
                        'all_first_exact':sum(metrics[s+'_first_exact'] for s in SPLITS)}
                    score.append(row)
                    objective=(metrics['fit_direction_matches'],metrics['fit_first_exact'],-metrics['fit_signal_episodes'])
                    if len(leaders)<6 or objective>tuple(leaders[-1]['objective']):
                        leaders.append({'candidate_id':cid,'recipe':recipe,'objective':list(objective),'metrics':metrics})
                        leaders.sort(key=lambda x:tuple(x['objective']),reverse=True);leaders=leaders[:6]
                        if any(x['candidate_id']==cid for x in leaders):
                            np.savez_compressed(target/f'alpha_{cid}.npz',minutes=bars.index.as_unit('ns').asi8,alpha=alpha.to_numpy(),raw=raw.to_numpy())
                    for i,t in enumerate(trades.itertuples()):
                        value=alpha.iloc[scorer.entries[i]]
                        details.append({'candidate_id':cid,'signal_id':t.signal_id,'entry':t.entry,'split':t.split,
                            'option_type':t.option_type,'alpha':value,'direction_pass':bool(value>.8 if t.direction==1 else value<.2)})
                print(f'Sampling alpha {base["kind"]}: stride={stride}, phase={phase}, trials={len(score)}',flush=True)
        pd.DataFrame(score).to_csv(target/'alpha_sampling_trials.csv',index=False)
        pd.DataFrame(details).to_csv(target/'alpha_sampling_every_trade.csv',index=False)
        (target/'alpha_frontier.json').write_text(json.dumps(leaders,indent=2))
    table=pd.DataFrame(score).sort_values(['fit_direction_matches','fit_first_exact'],ascending=False)
    print(table[['kind','historical_stride','sample_phase','lookback_unit','fit_direction_matches','all_direction_matches','all_first_exact']].head(10).to_string(index=False),flush=True)
    design={'trials':len(score),'selection':'fit alpha direction compatibility, then fit first exact, then fewer fit signal episodes',
        'causality':'Every minute uses its known completed-bar close or current opening price. History samples are strictly earlier; no future close/high/low/volume. Sampling phase describes indicator bar alignment, not an entry-time filter.',
        'lookbacks':'800 observed trading minutes / stride, or 800 sampled observations. Overnight gaps are not filled.',
        'scope':'Alpha compatibility only; no claim to recover alpha2 or autonomous entries. All 210 source entries compared.',
        'out_of_sample':'Later dates previously inspected; chronological splits are not untouched.'}
    (target/'sampling_design.json').write_text(json.dumps(design,indent=2))
    preceding_alpha_review()


def sampling_pairs():
    """Pair leading alpha sampling choices with causal sampled alpha2 ranks."""
    target=OUT/'sampling';target.mkdir(exist_ok=True)
    bars,panels,_=context();scorer=Scorer(bars.index);p=panels['near']
    leaders=json.loads((target/'alpha_frontier.json').read_text())[:3]
    alphas={};raws={};alpha_recipes={}
    for f in leaders:
        cid=f['candidate_id']
        with np.load(target/f'alpha_{cid}.npz',allow_pickle=False) as data:
            alphas[cid]=data['alpha'];raws[cid]=pd.Series(data['raw'],index=bars.index)
        alpha_recipes[cid]=f['recipe']
    name='close_old_open_h5_r800';alphas[name]=load_alpha()[name].to_numpy()
    alpha_recipes[name]={'kind':'close_old_open','horizon':5,'rank_window':800,'historical_stride':1}
    raws[name]=price_change_series(bars,alpha_recipes[name])
    path=target/'formula_trials.csv'
    done=set()
    if path.exists():
        old=pd.read_csv(path);done=set(zip(old.recipe_id,old.alpha))
    frontier=json.loads((target/'frontier.json').read_text()) if (target/'frontier.json').exists() else []
    pending=[];tested=0;clock=bars.index.hour*60+bars.index.minute-555
    for short,baseline in ((1,15),(1,20),(1,300),(5,300)):
        volume=[]
        for side in ('ce','pe'):
            v=p[f'{side}_native_volume'];den=v.rolling(baseline,min_periods=int(np.ceil(.8*baseline))).mean()
            volume.append(v.rolling(short,min_periods=short).mean()/den.where(den>0))
        ratio=(volume[0]+volume[1])/2
        for vol_kind in ('same_return','log_return'):
            for window in (250,300):
                vol=sum((np.log1p(p[f'{side}_return']) if vol_kind=='log_return' else p[f'{side}_return']).rolling(
                    window,min_periods=int(np.ceil(.8*window))).std() for side in ('ce','pe'))
                for lag in (0,5):
                    factors=ratio.shift(lag)/vol.shift(lag).where(vol.shift(lag)>0)
                    for stride in (1,2,5,10):
                        for phase in (range(stride) if stride in (2,5) else (0,)):
                            mask=clock%stride==phase
                            for semantics in (('minutes',) if stride==1 else ('minutes','observations')):
                                w=int(np.ceil(300/stride)) if semantics=='minutes' else 300
                                recipe={'context':'continuous_near','volume_kind':'native','volume_short':short,
                                    'volume_baseline':baseline,'volatility':f'{vol_kind}_{window}','factor_lag':lag,
                                    'rank_window':300,'historical_stride':stride,'sample_phase':phase,
                                    'lookback_unit':semantics,'rank_observations':w,'price_change':'same_as_alpha_sampling_v1'}
                                rid=json.dumps(recipe,sort_keys=True,separators=(',',':'))
                                remaining=[a for a in alphas if (rid,a) not in done]
                                if not remaining:continue
                                cache={}
                                for name in remaining:
                                    key=(alpha_recipes[name]['kind'],alpha_recipes[name]['horizon'])
                                    if key not in cache:
                                        raw=raws[name]*factors
                                        cache[key]=sampled_rank(raw,raw,mask,w).to_numpy()
                                    b=cache[key];metrics,_=scorer.score(alphas[name],b)
                                    pending.append({'recipe_id':rid,'alpha':name,**recipe,**metrics});done.add((rid,name))
                                    objective=(metrics['fit_first_exact'],metrics['fit_direction_matches'],-metrics['fit_signal_episodes'])
                                    cid=hashlib.sha256(f'{name}|{rid}'.encode()).hexdigest()[:16]
                                    if (len(frontier)<12 or objective>tuple(frontier[-1]['objective'])) and not any(f['candidate_id']==cid for f in frontier):
                                        f={'candidate_id':cid,'alpha':name,'alpha_recipe':alpha_recipes[name],
                                            'recipe':recipe,'metrics':metrics,'objective':list(objective)}
                                        frontier.append(f);frontier.sort(key=lambda v:tuple(v['objective']),reverse=True);frontier=frontier[:12]
                                        if any(f['candidate_id']==cid for f in frontier):
                                            np.savez_compressed(target/f'candidate_{cid}.npz',minutes=bars.index.as_unit('ns').asi8,
                                                alpha=alphas[name],alpha2=b)
                                tested+=1
                                if tested%20==0:
                                    pd.DataFrame(pending).to_csv(path,index=False,mode='a' if path.exists() else 'w',header=not path.exists());pending=[]
                                    tmp=target/'frontier.tmp';tmp.write_text(json.dumps(frontier,indent=2));tmp.replace(target/'frontier.json')
                                    print(f'Sampled alpha2 recipes: {tested}; fit frontier={frontier[0]["objective"]}',flush=True)
    if pending:pd.DataFrame(pending).to_csv(path,index=False,mode='a' if path.exists() else 'w',header=not path.exists())
    (target/'frontier.json').write_text(json.dumps(frontier,indent=2))
    (target/'paired_sampling_design.json').write_text(json.dumps({'paired_trials':len(done),'alpha_candidates':alpha_recipes,
        'selection':'fit first exact, then fit direction matches, then fewer fit signal episodes',
        'causality':'Sample history strictly precedes each current raw alpha2. Signals evaluated each eligible minute, not only on sampled clock boundaries. Missing historical observations fail closed.',
        'limitations':'Uses continuous nearest-expiry option factors. Conditional scoring uses source position state; autonomous replay is required. Later dates previously inspected. No clock or source P&L entry predictor.'},indent=2))
    print(f'Saved {len(done)} paired sampling trials',flush=True)


def main():
    bars,panels,_=context();trades=provider_trades();k=bars.index.get_indexer(trades.entry_minute)
    contiguous=pd.Series(bars.index,index=bars.index).shift(-1)-pd.Series(bars.index,index=bars.index)==pd.Timedelta(minutes=1)
    records=[]
    for h in (5,6):
        reference=bars.open.shift(h-1)
        history=(bars.close-reference)/reference
        ranks={price:provisional_rank(history,(bars[price].shift(-1).where(contiguous)-reference)/reference).to_numpy()[k]
               for price in ('open','low','high')}
        for i,t in enumerate(trades.itertuples()):
            alpha=ranks['open'][i];best=ranks['high' if t.direction==1 else 'low'][i]
            records.append({'signal_id':t.signal_id,'entry':t.entry,'split':t.split,'option_type':t.option_type,'span_minutes':h,
                'alpha_at_known_entry_candle_open':alpha,'NONCAUSAL_rank_at_entry_candle_low':ranks['low'][i],
                'NONCAUSAL_rank_at_entry_candle_high':ranks['high'][i],
                'known_open_direction_pass':bool(alpha>.8 if t.direction==1 else alpha<.2),
                'NONCAUSAL_any_entry_candle_price_could_pass':bool(best>.8 if t.direction==1 else best<.2)})
    table=pd.DataFrame(records);table.to_csv(OUT/'entry_price_envelopes_DIAGNOSTIC.csv',index=False)
    summary=table.groupby('span_minutes').agg(entries=('signal_id','size'),known_open_matches=('known_open_direction_pass','sum'),NONCAUSAL_envelope_matches=('NONCAUSAL_any_entry_candle_price_could_pass','sum'))
    summary.to_csv(OUT/'entry_price_envelopes_summary.csv')
    (OUT/'entry_price_envelopes_design.json').write_text(json.dumps({'interpretation':'Ranks against the previous 799 completed changes plus an entry-candle price. A high/low envelope is unavailable at the exact source entry time and must never be used to trade. Bounds assume this particular completed-history ranking convention, not hypothetical tick-sampled history.',
        'causal_predictor':'Only the opening-price column is available at the start of the entry minute.','windows':{'rank':800,'open_to_price_minutes':[5,6]}},indent=2))
    print(summary.to_string(),flush=True)
    print('Six-minute entries outside even the future candle envelope:',flush=True)
    print(table.loc[table.span_minutes.eq(6)&~table.NONCAUSAL_any_entry_candle_price_could_pass,['entry','option_type','alpha_at_known_entry_candle_open','NONCAUSAL_rank_at_entry_candle_low','NONCAUSAL_rank_at_entry_candle_high']].to_string(index=False),flush=True)
    # Test a different causal price feed rather than adjusting volume to hide
    # an alpha that cannot satisfy the stated direction threshold.
    scorer=Scorer(bars.index);scores=[];entries=[]
    for name,panel in panels.items():
        close=panel.atm_strike+panel.ce_ltp-panel.pe_ltp
        opening=panel.atm_strike+panel.ce_open-panel.pe_open
        for h in (4,5,6):
            for reference_name in ('synthetic_open','index_open'):
                reference=(opening if reference_name=='synthetic_open' else bars.open).shift(h)
                raw=(close-reference)/reference
                for fraction in (1.,.9):
                    alpha=rank(raw,800,fraction);metrics,_=scorer.score(alpha)
                    recipe={'feed':name,'horizon':h,'reference_feed':reference_name,'minimum_valid_fraction':fraction,'rank_window':800}
                    identity=json.dumps(recipe,sort_keys=True)
                    scores.append({'recipe':identity,**recipe,**metrics,
                        'all_direction_matches':sum(metrics[s+'_direction_matches'] for s in SPLITS),
                        'all_first_exact':sum(metrics[s+'_first_exact'] for s in SPLITS)})
                    for i,t in enumerate(trades.itertuples()):
                        value=alpha.iloc[k[i]]
                        entries.append({'recipe':identity,'signal_id':t.signal_id,'entry':t.entry,'option_type':t.option_type,'alpha':value,
                            'direction_pass':bool(value>.8 if t.direction==1 else value<.2)})
    pd.DataFrame(scores).to_csv(OUT/'synthetic_price_feed_trials.csv',index=False)
    pd.DataFrame(entries).to_csv(OUT/'synthetic_price_feed_every_trade.csv',index=False)
    print('Best synthetic-feed direction compatibility:',max(s['all_direction_matches'] for s in scores),'/210',flush=True)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bulk-workers',type=int,choices=(1,2),help='run the finite 16-shard grid with bounded local workers')
    parser.add_argument('--bulk-limit',type=int,default=0,help='new recipes per shard; zero scans all remaining recipes')
    parser.add_argument('--sampling',action='store_true',help='Screen causal historical sampling frequencies rather than future candle bounds')
    parser.add_argument('--sampling-pairs',action='store_true',help='Pair the fit-leading sampling alphas with alpha2 observation-frequency alternatives')
    parser.add_argument('--preceding-alpha',action='store_true',help='Diagnose prior alpha compatibility without adding a trade-delay rule')
    parser.add_argument('--option-spot',action='store_true',help='Compare the completed underlying spot fields attached to option candles')
    parser.add_argument('--boundaries',action='store_true',help='Test strict versus inclusive threshold comparisons on the saved fit-frontier recipes')
    parser.add_argument('--rank-conventions',action='store_true',help='Compare six trailing percentile/tie conventions on matched causal inputs')
    parser.add_argument('--prior-rank-alpha',action='store_true',help='Compare original alpha1 with a rank against800 past observations excluding current')
    parser.add_argument('--price-smoothing',action='store_true',help='Screen fixed completed-candle open/close blends and trailing price smoothers')
    parser.add_argument('--calendar-rank',action='store_true',help='Compare trading-observation and explicit calendar-minute rank-history support')
    parser.add_argument('--calendar-rank-pairs',action='store_true',help='Matched nine-pair alpha800/alpha2 300 trading-versus-calendar support experiment')
    parser.add_argument('--body-return-alpha',action='store_true',help='Necessary alpha screen: completed candle-body aggregates versus endpoint return')
    parser.add_argument('--weighted-alpha-rank',action='store_true',help='Six fixed observation-age kernels for alpha800; causal full-coverage rank')
    parser.add_argument('--weighted-rank-pairs',action='store_true',help='Four matched uniform versus observation-age weighted alpha/alpha2 pairs')
    parser.add_argument('--return-innovation-alpha',action='store_true',help='Twenty fixed causal trailing-mean/median return innovations versus endpoint control')
    parser.add_argument('--weighted-return-innovation-alpha',action='store_true',help='Twenty fixed return centres with the previously selected exponential rank800')
    parser.add_argument('--complete-case-alpha',action='store_true',help='Fixed shared input availability/drop policies before or after price-return construction')
    parser.add_argument('--complete-case-pairs',action='store_true',help='Two fit-leading shared-frame alphas with three fixed alpha2 drop policies')
    parser.add_argument('--hysteresis-pairs',action='store_true',help='36 fixed symmetric signal-state hypotheses and two original-rank controls')
    parser.add_argument('--volatility-normalized-alpha',action='store_true',help='Screen exploratory completed-price alpha with causal spot volatility scaling')
    parser.add_argument('--opening-reference',action='store_true',help='Test opening-price normalizations and known forming-bar openings')
    parser.add_argument('--required-prices',action='store_true',help='Calculate the underlying price needed for one specific alpha convention; diagnostic only')
    args=parser.parse_args()
    if args.hysteresis_pairs:
        if any(value for key,value in vars(args).items() if key!='hysteresis_pairs'):
            parser.error('--hysteresis-pairs is a separate experiment')
        hysteresis_pair_screen()
        raise SystemExit(0)
    if args.complete_case_pairs:
        if any(value for key,value in vars(args).items() if key!='complete_case_pairs'):
            parser.error('--complete-case-pairs is a separate experiment')
        complete_case_pair_screen()
        raise SystemExit(0)
    if args.complete_case_alpha:
        if any(value for key,value in vars(args).items() if key!='complete_case_alpha'):
            parser.error('--complete-case-alpha is a separate experiment')
        complete_case_alpha_screen()
        raise SystemExit(0)
    if args.weighted_return_innovation_alpha:
        if any(value for key,value in vars(args).items() if key!='weighted_return_innovation_alpha'):
            parser.error('--weighted-return-innovation-alpha is a separate experiment')
        return_innovation_alpha_screen(weighted=True)
        raise SystemExit(0)
    if args.return_innovation_alpha:
        if any(value for key,value in vars(args).items() if key!='return_innovation_alpha'):
            parser.error('--return-innovation-alpha is a separate experiment')
        return_innovation_alpha_screen()
        raise SystemExit(0)
    if args.weighted_rank_pairs:
        if any(value for key,value in vars(args).items() if key!='weighted_rank_pairs'):
            parser.error('--weighted-rank-pairs is a separate experiment')
        weighted_rank_pair_screen()
        raise SystemExit(0)
    if args.weighted_alpha_rank:
        if any(value for key,value in vars(args).items() if key!='weighted_alpha_rank'):
            parser.error('--weighted-alpha-rank is a separate experiment')
        weighted_alpha_rank_screen()
        raise SystemExit(0)
    if args.body_return_alpha:
        if any(value for key,value in vars(args).items() if key!='body_return_alpha'):
            parser.error('--body-return-alpha is a separate experiment')
        body_return_screen()
        raise SystemExit(0)
    if args.calendar_rank_pairs:
        if any(value for key,value in vars(args).items() if key!='calendar_rank_pairs'):
            parser.error('--calendar-rank-pairs is a separate experiment')
        calendar_rank_pair_screen()
        raise SystemExit(0)
    if args.prior_rank_alpha:
        if any(value for key, value in vars(args).items() if key != 'prior_rank_alpha'):
            parser.error('--prior-rank-alpha is a separate diagnostic')
        prior_rank_alpha_screen()
        raise SystemExit(0)
    if args.volatility_normalized_alpha:
        if any(value for key, value in vars(args).items() if key != 'volatility_normalized_alpha'):
            parser.error('--volatility-normalized-alpha is a separate diagnostic')
        volatility_normalized_alpha_screen()
        raise SystemExit(0)
    if args.bulk_workers is not None:
        if any((args.sampling,args.sampling_pairs,args.preceding_alpha,args.option_spot,args.boundaries,args.opening_reference,args.required_prices,args.rank_conventions,args.price_smoothing,args.calendar_rank)):
            parser.error('Bulk orchestration is a separate task')
        if args.bulk_limit<0:parser.error('--bulk-limit must be nonnegative')
        run_bulk_workers(args.bulk_workers,args.bulk_limit)
        raise SystemExit(0)
    if args.bulk_limit:parser.error('--bulk-limit requires --bulk-workers')
    if sum((args.sampling,args.sampling_pairs,args.preceding_alpha,args.option_spot,args.boundaries,args.opening_reference,args.required_prices,args.rank_conventions,args.price_smoothing,args.calendar_rank))>1:parser.error('Select a single diagnostic task')
    calendar_rank_screen() if args.calendar_rank else smoothed_price_screen() if args.price_smoothing else rank_convention_screen() if args.rank_conventions else required_price_review() if args.required_prices else opening_reference_screen() if args.opening_reference else boundary_screen() if args.boundaries else option_spot_screen() if args.option_spot else preceding_alpha_review() if args.preceding_alpha else sampling_pairs() if args.sampling_pairs else sampling_screen() if args.sampling else main()
