"""Checkpoint summary and every-trade evidence for fit-selected trial candidates."""
import argparse
import json
import numpy as np
import pandas as pd
from backtest.provider_trials import OUT,Scorer,SPLITS,threshold_config,premium_eligibility,ENTRY_QUOTE_CACHE,candidate_entry_allowed,entry_event_mask
from config import StrategyConfig
from utils.time import IST


def premium_entry_effects(baseline_dir,current_dir,gate,output):
    """Compare independent replay entries; labels explain changes, never trade inputs."""
    keys=['entry_ts','option_type','sell_strike','buy_strike','expiry']
    frames=[]
    for directory in (baseline_dir,current_dir):
        frame=pd.read_csv(directory/'trades.csv')
        frame.entry_ts=pd.to_datetime(frame.entry_ts,utc=True).dt.tz_convert(IST).astype(str)
        frame.expiry=pd.to_datetime(frame.expiry).dt.date.astype(str)
        frames.append(frame[keys+['sell_leg_entry']])
    changed=frames[0].merge(frames[1],on=keys,how='outer',indicator=True,suffixes=('_baseline','_premium'))
    removed=int(changed._merge.eq('left_only').sum());added=int(changed._merge.eq('right_only').sum())
    changed=changed.loc[changed._merge.ne('both')].copy()
    changed['status']=changed._merge.map({'left_only':'removed','right_only':'added','both':'unchanged'}).astype(str)
    reasons={}
    for path in sorted(current_dir.glob('decisions_*.csv.gz')):
        decisions=pd.read_csv(path,usecols=['minute','reason','alpha','alpha2'])
        decisions['minute']=pd.to_datetime(decisions.minute,utc=True).dt.tz_convert(IST).astype(str)
        for row in decisions.loc[decisions.minute.isin(changed.entry_ts)].itertuples():
            reasons[row.minute]=(row.reason,row.alpha,row.alpha2)
    changed['new_replay_reason_at_entry']=[reasons.get(ts,('',np.nan,np.nan))[0] for ts in changed.entry_ts]
    changed['new_alpha']=[reasons.get(ts,('',np.nan,np.nan))[1] for ts in changed.entry_ts]
    changed['new_alpha2']=[reasons.get(ts,('',np.nan,np.nan))[2] for ts in changed.entry_ts]
    changed['direct_premium_rejection']=changed.status.eq('removed')&changed.new_replay_reason_at_entry.eq('research premium eligibility')
    expiry_day=pd.to_datetime(changed.entry_ts,utc=True).dt.tz_convert(IST).dt.date==pd.to_datetime(changed.expiry).dt.date
    changed['minimum_short_premium']=np.where(expiry_day,gate['expiry_day_min'],gate['normal_day_min'])
    changed['maximum_short_premium']=gate['maximum']
    from backtest.provider_research import provider_trades
    source=provider_trades()
    published={(str(t.entry_minute),t.option_type,float(t.short_strike),float(t.hedge_strike),str(t.expiry)) for t in source.itertuples()}
    changed['published_entry_match']=[tuple(row) in published for row in changed[keys].itertuples(index=False,name=None)]
    changed.drop(columns='_merge').to_csv(output,index=False)
    return removed,added,int(changed.direct_premium_rejection.sum())


def opening_reference_evidence(target):
    """Compare observable contract selection at source minutes, not execution causes."""
    from backtest.provider_fixed_factors import OPENING_CACHE
    from backtest.provider_research import FEATURE_CACHE,BAR_CACHE,provider_trades
    source=provider_trades();bars=pd.read_csv(BAR_CACHE,index_col=0)
    idx=pd.to_datetime(bars.index,utc=True).tz_convert(IST)+pd.Timedelta(minutes=1)
    ids=idx.get_indexer(source.entry_minute)
    if (ids<5).any():raise ValueError('Missing preceding alpha2 factor observations')
    lagged=idx[ids-5]
    output=pd.DataFrame({'signal_id':source.signal_id,'entry':source.entry,'side':source.option_type,
        'source_short_strike':source.short_strike,'factor_time_lag5':lagged})
    for label,path in (('close_atm',FEATURE_CACHE),('open_atm',OPENING_CACHE)):
        p=pd.read_csv(path);p.minute=pd.to_datetime(p.minute,utc=True).dt.tz_convert(IST)
        p.expiry=pd.to_datetime(p.expiry).dt.date;p=p.set_index(['minute','expiry'])
        for suffix,times in (('entry',source.entry_minute),('lag5',lagged)):
            selected=p.reindex(pd.MultiIndex.from_arrays([times,source.expiry]))
            for field in ('atm_strike','ce_ltp','pe_ltp','ce_native_volume','pe_native_volume','ce_return','pe_return'):
                output[f'{label}_{field}_{suffix}']=selected[field].to_numpy()
    output.to_csv(target/'source_atm_reference_comparison.csv',index=False)
    return output


def atm_control_evidence(target,control):
    """All-trade ranks plus independent replay states for matched input panels."""
    from backtest.provider_research import provider_trades
    source=provider_trades();cid=control['candidate_id'];seed=control['control_for']
    volume_control=control.get('control_type') in ('volume_aggregation','volume_input')
    labels=('candidate','control') if volume_control else ('open_atm','close_atm')
    saved=json.loads((target/'frontier.json').read_text())
    recipes={f['candidate_id']:f['recipe'] for f in saved}
    from backtest.provider_trials import context,factor_contexts,continuous_native_components,CONTRACT_VOLUME_KINDS
    bars,_,_=context()
    frame=source[['signal_id','entry','entry_minute','option_type','direction','split']].copy()
    for label,identity in zip(labels,(seed,cid)):
        with np.load(target/f'candidate_{identity}.npz',allow_pickle=False) as stored:
            idx=pd.to_datetime(stored['minutes'],unit='ns',utc=True).tz_convert(IST)
            ids=idx.get_indexer(source.entry_minute)
            if (ids<1).any():raise ValueError('Missing control entry minute or preceding observation')
            a,b=stored['alpha'][ids],stored['alpha2'][ids];full_b=stored['alpha2'].copy()
            frame[f'{label}_previous_alpha']=stored['alpha'][ids-1]
            frame[f'{label}_previous_alpha2']=stored['alpha2'][ids-1]
        p=factor_contexts(bars,opening=recipes[identity].get('atm_reference')=='last_completed_bar_open',
            cumulative=recipes[identity].get('volume_kind') in CONTRACT_VOLUME_KINDS)['continuous_near'][0]
        components=continuous_native_components(bars,p,recipes[identity],control['alpha_recipe'])
        np.testing.assert_allclose(components.alpha2.to_numpy(),full_b,equal_nan=True,atol=1e-12,rtol=0)
        selected=components.reindex(source.entry_minute)
        for key in components.columns:
            if key!='alpha2':frame[f'{label}_{key}']=selected[key].to_numpy()
        frame[f'{label}_alpha']=a;frame[f'{label}_alpha2']=b
        cfg=threshold_config(StrategyConfig(),control['recipe'].get('threshold_comparison','strict'))
        frame[f'{label}_thresholds_pass']=np.where(source.direction==1,
            (a>cfg.bullish_threshold)&(b>cfg.bullish_threshold),(a<cfg.bearish_threshold)&(b<cfg.bearish_threshold))
        replay_dir=target/f'full_autonomous_{identity}_ledger'
        comparison=pd.read_csv(replay_dir/'source_trade_comparison.csv').set_index('signal_id').reindex(source.signal_id)
        frame[f'{label}_exact_entry']=comparison.exact_entry_direction_strikes_expiry.to_numpy()
        frame[f'{label}_exact_exit']=comparison.exact_exit_for_exact_entry.to_numpy()
        pieces=[]
        for path in sorted(replay_dir.glob('decisions_*.csv.gz')):
            d=pd.read_csv(path,usecols=['minute','reason','entry_ts'])
            d.minute=pd.to_datetime(d.minute,utc=True).dt.tz_convert(IST)
            pieces.append(d.loc[d.minute.isin(source.entry_minute)])
        decisions=pd.concat(pieces).set_index('minute').reindex(source.entry_minute)
        frame[f'{label}_model_reason']=decisions.reason.to_numpy()
        frame[f'{label}_model_position_open']=decisions.entry_ts.notna().to_numpy()
    first,second=labels
    np.testing.assert_allclose(frame[f'{first}_alpha'],frame[f'{second}_alpha'],equal_nan=True)
    if volume_control:
        keys=('price_change','atm_volatility_lagged') if control.get('control_type')=='volume_input' else ('price_change','ce_volume_ratio_lagged','pe_volume_ratio_lagged','atm_volatility_lagged')
        for key in keys:
            np.testing.assert_allclose(frame[f'{first}_{key}'],frame[f'{second}_{key}'],equal_nan=True)
    frame['threshold_gained']=frame[f'{first}_thresholds_pass']&~frame[f'{second}_thresholds_pass']
    frame['threshold_lost']=~frame[f'{first}_thresholds_pass']&frame[f'{second}_thresholds_pass']
    frame['exact_entry_gained']=frame[f'{first}_exact_entry']&~frame[f'{second}_exact_entry']
    frame['exact_entry_lost']=~frame[f'{first}_exact_entry']&frame[f'{second}_exact_entry']
    frame['direct_model_threshold_entry']=frame.exact_entry_gained&frame.threshold_gained&~frame[f'{second}_model_position_open']&frame[f'{second}_model_reason'].eq('no signal')
    name='volume_control' if volume_control else 'atm_control'
    suffix=f'_for_{seed}' if target.name=='contract_cumulative' and recipes[seed].get('volume_kind')!='contract_cumulative' else ''
    filename=f'{name}_every_trade_{cid}{suffix}.csv'
    frame.to_csv(target/filename,index=False)
    frame.attrs['evidence_filename']=filename
    return frame


def crossing_replay_evidence(directory,candidate):
    """Explain source entry changes using two independent replay position paths."""
    recipe=candidate['recipe'];cid=candidate['candidate_id'];seed=recipe['crossing_seed_candidate_id']
    root=directory.parent;family=recipe['crossing_seed_family']
    baseline_dir=(root if family=='main' else root/family)/f'full_autonomous_{seed}_ledger'
    current_dir=directory/f'full_autonomous_{cid}_ledger'
    reports=[p/'report.json' for p in (baseline_dir,current_dir)]
    if not all(p.exists() and json.loads(p.read_text())['result']['complete_history'] for p in reports):return None
    frame=pd.read_csv(directory/'entry_crossing_every_trade.csv')
    frame=frame.loc[frame.candidate_id.eq(cid)].copy()
    frame.entry=pd.to_datetime(frame.entry,utc=True).dt.tz_convert(IST)
    for label,path in (('level',baseline_dir),('crossing',current_dir)):
        comparison=pd.read_csv(path/'source_trade_comparison.csv').set_index('signal_id').reindex(frame.signal_id)
        frame[f'{label}_exact_entry']=comparison.exact_entry_direction_strikes_expiry.to_numpy()
        frame[f'{label}_exact_exit']=comparison.exact_exit_for_exact_entry.to_numpy()
        pieces=[]
        for file in sorted(path.glob('decisions_*.csv.gz')):
            d=pd.read_csv(file,usecols=['minute','reason','entry_ts'])
            d.minute=pd.to_datetime(d.minute,utc=True).dt.tz_convert(IST)
            pieces.append(d.loc[d.minute.isin(frame.entry.dt.floor('min'))])
        decisions=pd.concat(pieces).set_index('minute').reindex(frame.entry.dt.floor('min'))
        frame[f'{label}_model_reason']=decisions.reason.to_numpy()
        frame[f'{label}_model_position_open']=decisions.entry_ts.notna().to_numpy()
    frame['exact_entry_gained']=frame.crossing_exact_entry&~frame.level_exact_entry
    frame['exact_entry_lost']=~frame.crossing_exact_entry&frame.level_exact_entry
    frame['direct_crossing_entry_rejection']=frame.exact_entry_lost&frame.crossing_model_reason.eq('research entry crossing')
    frame.to_csv(directory/f'crossing_source_replay_{cid}.csv',index=False)
    return frame


def rank_replay_evidence(directory,candidate):
    """Compare matched rank changes and two independent position paths."""
    from backtest.provider_research import provider_trades
    r=candidate['recipe'];cid=candidate['candidate_id'];seed=r['rank_seed_candidate_id']
    baseline=directory.parent/r['rank_seed_family']/f'full_autonomous_{seed}_ledger'
    current=directory/f'full_autonomous_{cid}_ledger'
    if not all((p/'report.json').exists() and json.loads((p/'report.json').read_text())['result']['complete_history'] for p in (baseline,current)):return None
    source=provider_trades();frame=source[['signal_id','entry','entry_minute','option_type','direction','split']].copy()
    archives=[directory.parent/r['rank_seed_family']/f'candidate_{seed}.npz',directory/f'candidate_{cid}.npz']
    for label,path,archive in zip(('baseline','candidate'),(baseline,current),archives):
        with np.load(archive,allow_pickle=False) as stored:
            index=pd.to_datetime(stored['minutes'],unit='ns',utc=True).tz_convert(IST)
            ids=index.get_indexer(source.entry_minute)
            if (ids<1).any():raise ValueError('Missing rank comparison minute')
            a,b=stored['alpha'][ids],stored['alpha2'][ids]
            frame[f'{label}_alpha']=a;frame[f'{label}_alpha2']=b
            frame[f'{label}_previous_alpha']=stored['alpha'][ids-1]
            frame[f'{label}_previous_alpha2']=stored['alpha2'][ids-1]
        frame[f'{label}_thresholds_pass']=np.where(source.direction.eq(1),(a>.8)&(b>.8),(a<.2)&(b<.2))
        comparison=pd.read_csv(path/'source_trade_comparison.csv').set_index('signal_id').reindex(source.signal_id)
        frame[f'{label}_exact_entry']=comparison.exact_entry_direction_strikes_expiry.to_numpy()
        pieces=[]
        for file in sorted(path.glob('decisions_*.csv.gz')):
            d=pd.read_csv(file,usecols=['minute','reason','entry_ts'])
            d.minute=pd.to_datetime(d.minute,utc=True).dt.tz_convert(IST)
            pieces.append(d.loc[d.minute.isin(source.entry_minute)])
        decisions=pd.concat(pieces).set_index('minute').reindex(source.entry_minute)
        frame[f'{label}_model_reason']=decisions.reason.to_numpy()
        frame[f'{label}_model_position_open']=decisions.entry_ts.notna().to_numpy()
    frame['threshold_gained']=frame.candidate_thresholds_pass&~frame.baseline_thresholds_pass
    frame['threshold_lost']=~frame.candidate_thresholds_pass&frame.baseline_thresholds_pass
    frame['exact_entry_gained']=frame.candidate_exact_entry&~frame.baseline_exact_entry
    frame['exact_entry_lost']=~frame.candidate_exact_entry&frame.baseline_exact_entry
    frame['direct_model_threshold_entry']=frame.exact_entry_gained&frame.threshold_gained&~frame.baseline_model_position_open&frame.baseline_model_reason.eq('no signal')
    frame.to_csv(directory/f'rank_source_replay_{cid}.csv',index=False)
    return frame


def main():
    table=pd.read_csv(OUT/'formula_trials.csv')
    frontier=json.loads((OUT/'frontier.json').read_text())
    quotes=None
    if any(f['recipe'].get('premium_gate') is not None for f in frontier):
        quotes=pd.read_csv(ENTRY_QUOTE_CACHE)
        quotes.index=pd.to_datetime(quotes.pop('minute'),utc=True).dt.tz_convert(IST)
    records=[];score=[]
    for f in frontier:
        cid=f['candidate_id']
        with np.load(OUT/f'candidate_{cid}.npz',allow_pickle=False) as data:
            idx=pd.to_datetime(data['minutes'],unit='ns',utc=True).tz_convert(IST)
            a,b=data['alpha'],data['alpha2']
        comparison=f['recipe'].get('threshold_comparison','strict')
        cfg=threshold_config(StrategyConfig(),comparison)
        premium=premium_eligibility(idx,f,quotes)
        event=entry_event_mask(a,b,f['recipe'].get('entry_event','level'),comparison)
        allowed=candidate_entry_allowed(idx,f,a,b,quotes)
        scorer=Scorer(idx);metrics,signal=scorer.score(a,b,comparison,allowed)
        hit=np.minimum.accumulate(np.where(signal!=0,np.arange(len(idx)),len(idx))[::-1])[::-1]
        starts=scorer.starts
        first=hit[np.minimum(starts,len(idx)-1)]
        score.append({'candidate_id':cid,'alpha':f['alpha'],'recipe':json.dumps(f['recipe'],sort_keys=True),**metrics,
            'all_direction_matches':sum(metrics[s+'_direction_matches'] for s in SPLITS),
            'all_first_exact':sum(metrics[s+'_first_exact'] for s in SPLITS)})
        for i,t in enumerate(scorer.trades.itertuples()):
            k=scorer.entries[i];j=first[i]
            meaningful=starts[i]<len(idx) and starts[i]<=k and j<len(idx)
            ts=idx[j] if meaningful else pd.NaT
            records.append({'candidate_id':cid,'signal_id':t.signal_id,'split':t.split,'entry':t.entry,'option_type':t.option_type,
                'alpha':a[k],'alpha2':b[k],
                'direction_thresholds_pass':bool((a[k]>cfg.bullish_threshold and b[k]>cfg.bullish_threshold) if t.direction==1 else (a[k]<cfg.bearish_threshold and b[k]<cfg.bearish_threshold)),
                'premium_eligibility_pass':bool(premium[k,0 if t.direction==1 else 1]) if premium is not None else True,
                'entry_event_pass':bool(event[k,0 if t.direction==1 else 1]) if event is not None else True,
                'entry_conditions_pass':bool(signal[k]==t.direction),
                'alpha_direction_pass':bool(a[k]>cfg.bullish_threshold if t.direction==1 else a[k]<cfg.bearish_threshold),
                'alpha2_direction_pass':bool(b[k]>cfg.bullish_threshold if t.direction==1 else b[k]<cfg.bearish_threshold),
                'first_after_prior_source_exit':ts,'first_direction':int(signal[j]) if meaningful else 0,
                'first_minutes_before_entry':(t.entry_minute-ts).total_seconds()/60 if meaningful else np.nan,
                'first_exact':bool(meaningful and j==k and signal[k]==t.direction)})
    pd.DataFrame(records).to_csv(OUT/'frontier_every_trade.csv',index=False)
    frame=pd.DataFrame(score);frame.to_csv(OUT/'frontier_scorecard.csv',index=False)
    best=frame.iloc[0];recipes=table.recipe_id.nunique()
    exit_scores=pd.read_csv(OUT/'exit_rule_trials.csv') if (OUT/'exit_rule_trials.csv').exists() else None
    lines=['# Zen Credit replication trials','',
        f'Checkpoint: {recipes:,} formula recipes, {len(table):,} paired alpha/alpha2 trials; 210 published trade entries.',
        '', '## Current result','',
        f'Fit-selected leader: `{best.candidate_id}`. Directional entry conditions pass at {best.all_direction_matches}/210 source entries. Conditional first-signal timing is exact at {best.all_first_exact}/210 entries.',
        '',f'Alpha: `{best.alpha}`. Alpha2 recipe:', '', '```json',json.dumps(frontier[0]['recipe'],indent=2),'```','',
        '| Period | Entries | Entry conditions and direction | First signal exact | Extra flat signal minutes |',
        '|---|---:|---:|---:|---:|']
    for split in SPLITS:
        lines.append(f'| {split} | {best[split+"_trades"]} | {best[split+"_direction_matches"]} | {best[split+"_first_exact"]} | {best[split+"_extra_signal_minutes"]} |')
    lines+=['','## What these scores establish','',
        'These candidates are not replicas. Conditional timing assumes the published position history. The autonomous recent-week comparison supplies its own position state and measures exact entry minute, direction, strikes and expiry. Positive P&L alone is not a match.',
        '', 'Selection uses the first chronological fit period. Later periods were inspected earlier in this research and are not an untouched holdout. The 0.8/0.2 entry thresholds stay fixed. Dates, entry times and published P&L are labels, not alpha predictors.',
        '', 'Minute-close data cannot recover exact intraminute prices. Missing original hedge quotes can delay simulated exits. Synthetic cumulative ATM volume is a session sum over changing selected ATM contracts, not the true cumulative volume of a fixed contract.',
        '', 'The current-opening alpha variants use a known minute-opening price against completed historical changes. Their alpha2 ranks use successive causally available opening-based changes; this is an explicit alternative data convention.',
        '', '## Exit trials','']
    if exit_scores is not None:
        n=exit_scores.groupby('split').trades.first().sum()
        lines.append(f'{exit_scores.recipe.nunique()} profit-target, profit-floor and trailing-profit recipes tested on {n} complete, reconciled original-spread paths. Incomplete paths do not contribute matches. Exit paths are censored two minutes after the source exit; these are conditional diagnostics, not autonomous trades.')
        lines+=['','The 10%-of-reported-margin profit-floor hypothesis exits the September 30 position at 12:13 on October 1, about 160 minutes early. It does not explain the published 14:53 exit.']
    full_path=OUT/f'full_autonomous_{best.candidate_id}_ledger'/'report.json'
    if full_path.exists():
        full=json.loads(full_path.read_text())['result']
        lines+=['','## Full-history autonomous replay','',
            f'Completed {full["completed_blocks"]}/{full["total_blocks"]} raw-data chunks. Entries, directions, strikes and expiry match exactly for {full["exact_entries"]}/210 source records; {full["extra_entries"]} extra entries and {full["missing_source_entries"]} missed source entries. Of matched entries, {full["exact_exits_for_exact_entries"]} also match the reported exit minute.',
            '',f'Missing held-leg quote minutes: {full["missing_held_quote_minutes"]:,}. Position state carries between chunks; official expiry settlement resolves expired contracts when earlier quotes are unavailable. Missing prices can delay exits and alter later entries.',
            '',f'Whole history complete: {full["complete_history"]}. Entry eligibility extends through the final source exit date, so entries after the last published entry are counted as extras too.',
            '',f'[Trade-by-trade autonomous comparison](full_autonomous_{best.candidate_id}_ledger/source_trade_comparison.csv).']
    recent_path=OUT/'autonomous_comparison.csv'
    if recent_path.exists():
        recent=pd.read_csv(recent_path)
        current=recent.loc[recent.candidate_id.eq(best.candidate_id)]
        if not current.empty:
            lines+=['','## September 28–October 1 autonomous replay','',
                '| Execution profile | Entries | Exact source entries | Extras | Realized plus MTM, INR | Missing held quotes |',
                '|---|---:|---:|---:|---:|---:|']
            for r in current.itertuples():
                value=f'{r.total_pnl:,.2f}' if pd.notna(r.total_pnl) else 'unavailable'
                lines.append(f'| {r.execution_style} | {r.simulated_entries} | {r.exact_entries_direction_strikes}/{r.source_trades} | {r.extra_entries} | {value} | {r.missing_held_quote_minutes} |')
            lines+=['','These runs start flat and maintain their own positions. P&L is provisional and excludes costs; missing held-leg quotes can delay exits. An open-position MTM is not realized profit.','', '[Autonomous comparison](autonomous_comparison.csv).']
            week=[r for r in records if r['candidate_id']==best.candidate_id and '2026-09-28'<=str(r['entry'])[:10]<='2026-10-01']
            if week:
                lines+=['','Model values at the published entry minute (not the provider\'s undisclosed alpha values):','',
                    '| Source entry, IST | Spread side | Alpha | Alpha2 | Both directional thresholds pass |',
                    '|---|---|---:|---:|---|']
                for r in week:
                    lines.append(f'| {r["entry"]} | {r["option_type"]} | {r["alpha"]:.6f} | {r["alpha2"]:.6f} | {r["direction_thresholds_pass"]} |')
    bounds=OUT/'entry_price_envelopes_summary.csv'
    if bounds.exists():
        lines+=['','## Price-feed diagnostics','',
            'Five-minute open-to-current-price alpha passes direction at 174/210 entry-candle openings; the six-minute interpretation passes 199/210. Even the future six-minute entry-candle high/low envelope permits only 206/210. These noncausal extremes are diagnostic only: historical rank sampling could differ, and the extreme may occur after the source entry.',
            '', 'Four entries remain outside that specific completed-history ranking convention even at a favorable intraminute extreme: August 1, August 5, October 17 and December 10, 2025. Volume adjustments cannot repair an alpha that fails its own threshold under that convention.',
            '', '[Every-trade price bounds](entry_price_envelopes_DIAGNOSTIC.csv). The separate 24 synthetic forward price-feed trials recover at most 183/210 entry directions and do not improve on the index opening-reference candidate. These feeds use strike + call premium - put premium; they are not actual futures candles.',
            '', '[Synthetic-feed trials](synthetic_price_feed_trials.csv).']
    margin_scores=OUT/'margin_exit_scorecard.csv'
    if margin_scores.exists():
        margins=pd.read_csv(margin_scores)
        row=margins.loc[margins.scenario.eq('multiplier')&margins.multiplier.eq(1.5)&margins.equity_proxy.eq('fixed_capital')].iloc[0]
        lines+=['','## Possible broker margin exits','',
            f'All 210 source trades screened. {int(row.trades)} entered before expiry and stayed recorded open into expiry. At unchanged source quantities and assumed INR 320,000 account funds, a 1.50x margin scenario flags {int(row.possible_shortfalls)} possible shortfalls; only {int(row.same_exit_minute)} first observed breaches share the actual exit minute ({int(row.within_two_minutes)} within two minutes).',
            '', 'The user reports additional deposited margin allowed their similar position to survive until EOD. Broker-driven exits therefore need investigation alongside strategy exits. This account-specific explanation is not a recovered universal exit rule: historical funds, top-ups, margin updates and RMS reasons are unknown. Production sizing remains unchanged.',
            '', '[Every-trade margin scenarios](margin_exit_scenarios.csv), [assumptions and findings](margin_exit_review.md).']
    premium_scores=OUT/'premium_exit_trials.csv'
    if premium_scores.exists():
        premium=pd.read_csv(premium_scores)
        lines+=['','## Premium target interpretations','',
            f'{premium.recipe.nunique()} exit recipes compare net-spread, combined-premium and sold-option targets, plus no target. Scores use the same 118 complete, reconciled paths. The fit-selected no-target recipe matches 44 exit minutes, versus 39 for net-premium 10; it still leaves early exits unexplained.',
            '', 'A sold-option premium target of 15 first appears one minute after the February 10 source exit, and five minutes before the September 29 source exit. It is not a recovered uniform exit trigger. No production target has changed.',
            '', '[Premium exit evidence](premium_exit_review.md), [every-trade trials](premium_exit_trials_per_trade.csv.gz).']
    fraction_scores=OUT/'premium_fraction_exit_trials.csv'
    if fraction_scores.exists():
        fraction=pd.read_csv(fraction_scores)
        fit=fraction.loc[fraction.split.eq('fit')].sort_values(['exact','within_two_minutes','earlier'],ascending=[False,False,True])
        chosen=fit.iloc[0]
        selected=fraction.loc[fraction.recipe.eq(chosen.recipe)]
        lines+=['','## Targets as fractions of entry premium','',
            f'{fraction.recipe.nunique()} recipes compare remaining premiums of 5%, 10%, 15%, 20%, 25% or 50% of their entry values on the same 118 complete, reconciled paths. The fit-selected recipe is `{chosen.recipe}`; it matches {int(selected.exact.sum())} exit minutes and {int(selected.within_two_minutes.sum())} within two minutes across the scored periods.',
            '', 'A fraction of 0.10 means 90% premium decay, not a 10% return on margin. The incomplete September 28 hedge path still cannot be scored as an observed target hit.',
            '', '[Fractional-target evidence](premium_fraction_exit_review.md), [every-trade trials](premium_fraction_exit_trials_per_trade.csv.gz).']
    exit_bounds=OUT/'september_exit_bounds_design.json'
    if exit_bounds.exists():
        bounds=json.loads(exit_bounds.read_text())
        target=next(r for r in bounds['targets'] if r['target']==10.)
        candles=pd.read_csv(OUT/'september_exit_bounds_DIAGNOSTIC.csv')
        candles.index=pd.to_datetime(candles.pop('bar_start'),utc=True).dt.tz_convert(IST)
        exit_bar=pd.Timestamp(bounds['source_exit']).floor('min')
        previous_bar=exit_bar-pd.Timedelta(minutes=1)
        before=candles.loc[previous_bar,'DIAGNOSTIC_net_lower_intrabar']
        during=candles.loc[exit_bar,'DIAGNOSTIC_net_lower_intrabar']
        lines+=['','## September 29 missing-hedge price bounds','',
            f'The 23250 CE hedge is absent from the archive. Newly obtained original-short and lower-strike call OHLC data give an outer interval for its spread value under a same-expiry call-price monotonicity assumption. A 10-point target is first not excluded in the candle starting `{target["first_possible_bar_start"]}`, the source exit candle. Earlier morning candles exclude it under these assumptions.',
            '', f'At {previous_bar:%H:%M}, the conservative intrabar spread lower bound is {before:.2f}; at {exit_bar:%H:%M} it is {during:.2f}. The recorded exit debit is {bounds["source_exit_net_fill"]:.2f}. This supports investigating a 10-point target with intraminute execution differences; it does not establish an actual touch or rule out broker liquidation.',
            '', 'High/low combinations are not simultaneous prices, and last traded prices need not be executable quotes. Current-candle high/low are known only after completion. No bound is used to fill the missing hedge, trigger an autonomous exit, or claim an incomplete path matches.',
            '', '[Every-candle bounds](september_exit_bounds_DIAGNOSTIC.csv), [requests, assumptions and limits](september_exit_bounds_design.json).']
    probe_path=OUT/'far_strike_probe.json'
    if probe_path.exists():
        probe=json.loads(probe_path.read_text())
        control=probe.get('documented_range_control',{})
        if probe.get('status')=='returned' and control:
            lines+=['','## Historical quote availability','',
                f'With the renewed token, Dhan accepted both read-only requests for September 29, 2026. ATM+12 returned {probe["rows"]} candles, while ATM+10 returned {control["rows"]}. At the September 28 position\'s recorded exit, its original 23250 CE hedge lay about 12 strikes above ATM. The control confirms data exists for the date; it does not supply the missing held hedge.',
                '', '[Sanitized request and control](far_strike_probe.json). No replacement strike, price interpolation or forward fill is used to invent its exit path.']
    sampling_scores=OUT/'sampling'/'alpha_sampling_trials.csv'
    if sampling_scores.exists():
        sampled=pd.read_csv(sampling_scores)
        every=pd.read_csv(OUT/'sampling'/'alpha_sampling_every_trade.csv')
        unresolved=int((~every.groupby('signal_id').direction_pass.any()).sum())
        lines+=['','## Indicator sampling diagnostics','',
            f'{len(sampled)} causal alpha variants tested at historical strides of 1, 2, 5 and 10 minutes, with the current value evaluated every minute. At most {int(sampled.all_direction_matches.max())}/210 entry directions pass in one variant. {unresolved} source entries fail every variant at the recorded entry minute.',
            '', 'The alternatives compare 800 observed trading minutes with 800 sampled observations. Samples strictly precede the current value. For the current-opening variant, this also omits the latest aligned completed row from history, unlike the older provisional-rank convention; the two are explicit causal alternatives.',
            '', '[Every-trade sampling values](sampling/alpha_sampling_every_trade.csv). This finite bank does not establish that no other private price feed or ranking convention could work.']
        preceding=OUT/'sampling'/'preceding_alpha_DIAGNOSTIC.csv'
        if preceding.exists():
            earlier=pd.read_csv(preceding)
            earlier=earlier.loc[earlier.alpha_recipe.eq('close_old_open_h5_r800')]
            counts={lag:int(earlier.loc[earlier.minutes_before_recorded_entry.le(lag)].groupby('signal_id').direction_threshold_pass.any().sum()) for lag in (0,1,5)}
            lines+=['',f'The baseline opening-reference alpha is compatible at {counts[0]}/210 recorded entry minutes, or at {counts[1]}/210 when a preceding one-minute signal is allowed; extending to five preceding minutes still reaches only {counts[5]}/210. Actual decision and execution timestamps are unknown. No arbitrary delay rule has been added.',
                '', '[Prior-minute alpha diagnostic](sampling/preceding_alpha_DIAGNOSTIC.csv).']
        paired_path=OUT/'sampling'/'formula_trials.csv'
        paired_frontier=OUT/'sampling'/'frontier.json'
        if paired_path.exists() and paired_frontier.exists():
            paired=pd.read_csv(paired_path);leader=json.loads(paired_frontier.read_text())[0]
            direction=sum(leader['metrics'][s+'_direction_matches'] for s in SPLITS)
            exact=sum(leader['metrics'][s+'_first_exact'] for s in SPLITS)
            lines+=['',f'The separate sampled-alpha2 bank contains {len(paired):,} paired trials. Its fit-selected leader passes both thresholds at {direction}/210 entries and conditionally matches {exact}/210 first signals.',
                '', '[Sampled-alpha2 evidence and autonomous replay](sampling/summary.md). Sampled histories require all selected observations to be valid, an explicit stricter alternative to the main bank\'s 90% rank-history coverage rule.']
    expanded_table=OUT/'expanded'/'formula_trials.csv'
    expanded_frontier=OUT/'expanded'/'frontier.json'
    if expanded_table.exists() and expanded_frontier.exists():
        expanded=pd.read_csv(expanded_table);leader=json.loads(expanded_frontier.read_text())[0]
        contexts=sorted({json.loads(r)['context'] for r in expanded.recipe_id.unique()})
        lines+=['','## Alternative volume definitions','',
            f'The expanded bank contains {expanded.recipe_id.nunique():,} recipes and {len(expanded):,} paired trials across {", ".join(contexts)}. It compares reciprocal call/put ratios, previous-bar ratios, raw volume, total-volume ratios, normalized put/call ratios, geometric means and minimum ratios. These are hypotheses, including departures from the description\'s arithmetic average.',
            '',f'Fit-selected leader: `{leader["candidate_id"]}`. Its later-period scores and autonomous weekly comparison are saved separately; a better conditional fit score does not establish replication.',
            '', '[Expanded-bank evidence and replay](expanded/summary.md).']
    option_spot=OUT/'option_spot_trials.csv'
    if option_spot.exists():
        spots=pd.read_csv(option_spot)
        lines+=['','## Option-candle underlying spot','',
            f'{len(spots)} causal alpha variants use the underlying spot stored with CE or PE candles, retaining index candle opens as the opening reference. The best direction compatibility is {int(spots.all_direction_matches.max())}/210. This feed alternative does not resolve every alpha mismatch.',
            '', '[Every-trade option-spot alpha values](option_spot_every_trade.csv), [feed coverage](option_spot_design.json). Missing prices are not filled.']
    opening_trials=OUT/'opening_reference_trials.csv'
    if opening_trials.exists():
        opening=pd.read_csv(opening_trials)
        entries=pd.read_csv(OUT/'opening_reference_every_trade.csv')
        unresolved=int((~entries.groupby('signal_id').direction_pass.any()).sum())
        chosen=opening.sort_values(['fit_direction_matches','fit_first_exact','fit_signal_episodes'],ascending=[False,False,True]).iloc[0]
        lines+=['','## Opening-price normalization and forming candles','',
            f'{len(opening)} alpha variants hold the rank at 800 observations. Alternatives normalize by the start/current bar open, start/current session open, previous session close, or use unscaled point changes. The best overall direction compatibility is {int(opening.all_direction_matches.max())}/210; {unresolved} entries fail every variant at the recorded entry minute.',
            '',f'Fit-selected alpha: `{chosen.candidate_id}`, {chosen.price_expression}, {chosen.normalization}; {int(chosen.all_direction_matches)}/210 compatible directions. Selection does not use later-period scores.',
            '', 'The forming-row alternatives compare a known current-minute opening change with completed historical changes. They supply no future current-minute close/high/low/volume and cannot reconstruct the private intraminute decision price.',
            '', '[Every-trade opening-reference values](opening_reference_every_trade.csv), [definitions and causality](opening_reference_design.json). This alpha-only screen does not recover alpha2 or generate autonomous entries.']
    required_prices=OUT/'required_index_prices_DIAGNOSTIC.csv'
    if required_prices.exists():
        required=pd.read_csv(required_prices)
        exceptions=required.loc[~required.NONCAUSAL_favorable_extreme_can_pass]
        lines+=['','## Required price for the opening-reference alpha','',
            'Inverting this specific 800-observation rank gives the underlying price required to cross its threshold. Four source entries require a price outside their entire recorded entry candle under this convention. This does not exclude another private history/feed or decision timestamp.',
            '', '| Source entry, IST | Side | Required index price | Recorded candle low | Recorded candle high | Distance beyond candle |',
            '|---|---|---:|---:|---:|---:|']
        for r in exceptions.itertuples():
            lines.append(f'| {r.entry} | {r.option_type} | {r.required_index_price:.2f} | {r.NONCAUSAL_entry_candle_low:.2f} | {r.NONCAUSAL_entry_candle_high:.2f} | {r.distance_outside_candle_points:.2f} |')
        lines+=['','The required-price calculation uses completed history; current-candle low/high are noncausal comparison labels. They are not available at the source entry and never used to place a replay trade.',
            '', '[Every-trade required prices](required_index_prices_DIAGNOSTIC.csv), [exact convention and limits](required_index_prices_design.json).']
    source_audit=OUT.parent/'source_record_audit.json'
    if source_audit.exists():
        audit=json.loads(source_audit.read_text())
        lines+=['','## Source-record integrity','',
            f'All {audit["trades"]} source records pass the timestamp/name-minute, leg-side, symbol/strike, shared-expiry, multiplier and 400-point credit-spread checks. Reported P&L reconciles for {audit["pnl_reconciles"]}/210; all entries remain in entry tests.',
            '',f'{audit["recorded_after_expiry"]} exits are recorded after contract expiry, {audit["overlapping_records_by_minute"]} records overlap by minute, and {audit["same_minute_reentries"]} reentries share a prior exit minute. These labels are retained. Valid parsing does not prove broker execution timestamps, original alpha values or liquidation reasons.',
            '', '[Every-record metadata audit](../source_record_audit.csv), [audit scope](../source_record_audit.json).']
        if 'position_state_constraints' in audit:
            counts=audit['position_state_constraints']
            lines+=['',f'The precise timestamps show up to {audit["maximum_simultaneous_published_positions"]} concurrently open published spreads. There are {counts["overlapping_published_positions"]} overlapping position pairs and {counts["exit_then_entry_within_one_minute"]} exits followed by entries later within the same minute. A one-position, one-evaluation-per-minute engine cannot reproduce all these entry and exit labels together, irrespective of alpha parameters.',
                '', 'This identifies an execution-model limitation, not an entry trigger or proof of simultaneous broker holdings. The records may describe overlapping strategy signals or delayed status updates; broker order events are unavailable. No concurrent-position or same-minute reentry rule has been enabled.',
                '', '[Exact intervals and model constraints](../position_state_constraints.csv).']
        if 'public_exit_fields' in audit:
            fields=audit['public_exit_fields']
            lines+=['','### Public stop and target fields','',
                f'All {fields["legs_with_zero_stop_loss"]} published leg stops and {fields["legs_with_zero_target_price"]} leg targets are zero. This does not establish absence of internal spread-level exit rules.',
                '',f'The last exit summary value equals the sum of average leg exit prices in {fields["exit_value_matches_sum_of_average_leg_prices"]}/210 records and the net spread price in {fields["exit_value_matches_net_spread_price"]}/210. It therefore does not disclose a net-spread target threshold.',
                '', '[Every-trade exit-field audit](../public_exit_field_audit.csv). Source final prices and P&L remain comparison labels.']
    rank_selected=OUT/'rank_exit_selected.json'
    if rank_selected.exists():
        selected=json.loads(rank_selected.read_text())
        lines+=['','## Alpha and alpha2 exit tests','',
            'Four causal signal reconstructions test loss of directional support below 0.8, 0.5 or 0.2, using alpha, alpha2, either or both, with persistence of 1, 3 or 5 trading observations. Each gets matched no-rank controls with identical stops, premium targets and time exits. Only the first modeled exit scores.',
            '', '| Entry-signal bank | Rank rule exact / within 2 min | No-rank control exact / within 2 min | Rank rule early exits |',
            '|---|---:|---:|---:|---:|']
        for r in selected:
            lines.append(f'| {r["family"]} | {r["exact"]} / {r["within_two_minutes"]} | {r["control_exact"]} / {r["control_within_two_minutes"]} | {r["earlier"]} |')
        lines+=['','These are source-conditioned exit diagnostics on complete, reconciled paths. They do not recover private alpha values or confirm broker liquidation. Fit rules were chosen on the earliest period; later periods have already been inspected. No production exit rule changed.',
            '', '[Full exit-rule report](rank_exit_review.md), [every-trade ranks](rank_exit_every_trade.csv), [all split scores](rank_exit_trials.csv).']
    boundary_dir=OUT if OUT.name=='boundaries' else OUT/'boundaries'
    boundary_design=boundary_dir/'boundary_design.json'
    if boundary_design.exists():
        design=json.loads(boundary_design.read_text())
        relative='' if boundary_dir==OUT else 'boundaries/'
        lines+=['','## Equality at the threshold','',
            f'{design["trials"]} comparisons test strict, inclusive, bearish-only inclusive and bullish-only inclusive semantics on saved fit-frontier recipes. Nominal cutoffs remain 0.20 and 0.80. Equality is an explicit alternative to the supplied description\'s strict wording; production rules remain strict.',
            '', 'The minimum-volume candidate has alpha2 exactly 0.20 at the September 30 published entry. The following case is retained because of that observed equality; it is not an untouched validation sample. The volume minimum also differs from the description\'s stated average.']
        boundary_frontier=json.loads((boundary_dir/'frontier.json').read_text())
        recent_boundary=pd.read_csv(boundary_dir/'autonomous_comparison.csv') if (boundary_dir/'autonomous_comparison.csv').exists() else pd.DataFrame()
        for cid in design.get('case_candidates',[]):
            case=next(f for f in boundary_frontier if f['candidate_id']==cid)
            directions=sum(case['metrics'][s+'_direction_matches'] for s in SPLITS)
            exact=sum(case['metrics'][s+'_first_exact'] for s in SPLITS)
            lines+=['',f'Case `{cid}`: both thresholds agree at {directions}/210 recorded entry minutes; source-conditioned first signals are exact at {exact}/210.']
            if not recent_boundary.empty:
                selected=recent_boundary.loc[recent_boundary.candidate_id.eq(cid)]
                lines+=['']
                for r in selected.itertuples():
                    lines.append(f'- Weekly {r.execution_style}: {r.exact_entries_direction_strikes}/{r.source_trades} exact entries, {r.extra_entries} extras, {r.exact_exits_for_exact_entries} exact exits; {r.missing_held_quote_minutes} missing held-leg quote minutes. Provisional gross P&L plus MTM: INR {r.total_pnl:,.2f}.')
            full_case=boundary_dir/f'full_autonomous_{cid}_ledger'/'report.json'
            if full_case.exists():
                full=json.loads(full_case.read_text())['result']
                lines+=['',f'Full-history replay checkpoint: {full["completed_blocks"]}/{full["total_blocks"]} chunks, {full["exact_entries"]} exact entries, {full["extra_entries"]} extras, {full["exact_exits_for_exact_entries"]} matching exits among exact entries. Whole history complete: {full["complete_history"]}.',
                    '',f'[Full-history case comparison]({relative}full_autonomous_{cid}_ledger/source_trade_comparison.csv).']
            lines+=['', 'Reproduce this explicit case from `zen_credit/`:','', '```powershell',
                f'..\\.venv\\Scripts\\python.exe -B -u -m backtest.provider_trials --family boundaries --replay-top 1 --candidate {cid}',
                f'..\\.venv\\Scripts\\python.exe -B -u -m backtest.provider_autonomous --family boundaries --candidate {cid}','```']
        lines+=['',f'[Boundary comparison design]({relative}boundary_design.json). A weekly entry match does not establish matching exits or replication across the full history.']
    eligibility_dir=OUT if OUT.name=='eligibility' else OUT/'eligibility'
    eligibility_design=eligibility_dir/'eligibility_design.json'
    if eligibility_design.exists():
        design=json.loads(eligibility_design.read_text())
        saved=json.loads((eligibility_dir/'frontier.json').read_text())
        relative='' if eligibility_dir==OUT else 'eligibility/'
        lines+=['','## Premium eligibility hypotheses','',
            f'Provider metadata lists a PREMIUM eligibility check but gives no definition or limits. This separate bank tests {design["paired_trials"]} combinations on five saved seeds. Normal-day minimums are {design["normal_day_min_grid"]}; expiry-day minimums are {design["expiry_day_min_grid"]}; maximum short premium is 200.',
            '', 'The minimum applies to the selected short option, with expiry determined from the actual contract. Quotes must be present at the decision minute. Fit scoring uses the ledger opening-reference ATM; autonomous replays check the actual proposed short premium for each execution style. No sizing, reserve margin, production signal or exit rule has changed.',
            '', 'Candidate selection uses fit first-signal matches, direction and fewer episodes. The 40/20 version of the previously examined weekly candidate is retained as an explicit case, not chosen from later-period P&L.']
        selected_ids=[design['fit_selected_leader']]+design.get('case_candidates',[])
        recent=pd.read_csv(eligibility_dir/'autonomous_comparison.csv') if (eligibility_dir/'autonomous_comparison.csv').exists() else pd.DataFrame()
        for cid in dict.fromkeys(selected_ids):
            f=next(v for v in saved if v['candidate_id']==cid)
            gate=f['recipe']['premium_gate']
            first=sum(f['metrics'][s+'_first_exact'] for s in SPLITS)
            directions=sum(f['metrics'][s+'_direction_matches'] for s in SPLITS)
            lines+=['',f'Candidate `{cid}`: normal minimum {gate["normal_day_min"]}, expiry minimum {gate["expiry_day_min"]}, maximum {gate["maximum"]}; {directions}/210 directional entry conditions, {first}/210 source-conditioned first signals.']
            if not recent.empty:
                for r in recent.loc[recent.candidate_id.eq(cid)].itertuples():
                    lines.append(f'- Weekly {r.execution_style}: {r.exact_entries_direction_strikes}/{r.source_trades} exact entries, {r.extra_entries} extras, {r.exact_exits_for_exact_entries} matching exits; {r.missing_held_quote_minutes} missing held-leg quote minutes.')
            path=eligibility_dir/f'full_autonomous_{cid}_ledger'/'report.json'
            if path.exists():
                r=json.loads(path.read_text())['result']
                lines+=['',f'Full replay: {r["completed_blocks"]}/{r["total_blocks"]} chunks, {r["exact_entries"]}/210 exact entries, {r["extra_entries"]} extras, {r["missing_source_entries"]} missed entries, {r["exact_exits_for_exact_entries"]} matching exits among exact entries. Complete history: {r["complete_history"]}. Missing held quotes: {r["missing_held_quote_minutes"]:,}.',
                    '',f'[Every-trade replay comparison]({relative}full_autonomous_{cid}_ledger/source_trade_comparison.csv).']
                seed_family=f['recipe']['eligibility_seed_family']
                seed_id=f['recipe']['eligibility_seed_candidate_id']
                root=OUT.parent if OUT.name=='eligibility' else OUT
                seed_dir=root if seed_family=='main' else root/seed_family
                baseline=seed_dir/f'full_autonomous_{seed_id}_ledger'/'report.json'
                if baseline.exists() and r['complete_history']:
                    before=json.loads(baseline.read_text())['result']
                    if before['complete_history']:
                        lines+=['',f'Its ungated seed `{seed_id}` had {before["exact_entries"]} exact entries, {before["extra_entries"]} extras and {before["exact_exits_for_exact_entries"]} matching exits. Premium gating changes exact entries by {r["exact_entries"]-before["exact_entries"]:+d} and extra entries by {r["extra_entries"]-before["extra_entries"]:+d}.']
                        effects=eligibility_dir/f'premium_entry_effects_{cid}.csv'
                        removed,added,direct=premium_entry_effects(baseline.parent,path.parent,gate,effects)
                        lines+=['',f'{removed} original replay entries disappear and {added} new entries appear as the position path changes. Of the removed entries, {direct} are directly rejected at their original entry minute by the premium check; other changes depend on the altered position path.',
                            '',f'[Changed entries and concrete rejection reasons]({relative}{effects.name}).']
                        rejected=pd.read_csv(effects)
                        rejected=rejected.loc[rejected.direct_premium_rejection]
                        if not rejected.empty:
                            lines+=['','| Rejected simulated entry, IST | Side | Short premium | Minimum | Alpha | Alpha2 |',
                                '|---|---|---:|---:|---:|---:|']
                            for v in rejected.itertuples():
                                lines.append(f'| {v.entry_ts} | {v.option_type} | {v.sell_leg_entry_baseline:.2f} | {v.minimum_short_premium:.2f} | {v.new_alpha:.5f} | {v.new_alpha2:.5f} |')
        lines+=['',f'[Eligibility design]({relative}eligibility_design.json), [entry evidence]({relative}frontier_every_trade.csv), [source fills versus selected historical premiums]({relative}source_premium_comparison.csv). These limits remain hypotheses.']
    opening_dir=OUT if OUT.name=='opening_atm' else OUT/'opening_atm'
    if (opening_dir/'panel_design.json').exists():
        comparison=opening_reference_evidence(opening_dir)
        close_matches=int(comparison.close_atm_atm_strike_entry.eq(comparison.source_short_strike).sum())
        open_matches=int(comparison.open_atm_atm_strike_entry.eq(comparison.source_short_strike).sum())
        relative='' if opening_dir==OUT else 'opening_atm/'
        lines+=['','## ATM reference used by option factors','',
            f'The existing close-selected factor ATM matches {close_matches}/210 published short strikes at entry. Selecting ATM from the last completed index candle open matches {open_matches}/210. This is evidence for investigating which contract feeds alpha2, not proof that alpha2 uses that contract.',
            '', 'The separate opening_atm bank rebuilds native volume and same-contract one-minute returns at the opening-selected strike. All ranks and factors are trailing. It compares price-level, same-contract price-change, simple-return and log-return volatility, summed across CE and PE. Source strikes are comparison labels, never panel inputs.',
            '', 'The comparison includes option inputs at the entry minute and five completed observations earlier. When factor lag is five, the latter is the relevant option observation; an entry-minute strike discrepancy alone does not explain the entry signal.',
            '',f'[All 210 contract/input comparisons]({relative}source_atm_reference_comparison.csv), [panel definitions]({relative}panel_design.json).']
        path=opening_dir/'frontier.json'
        if path.exists():
            saved=json.loads(path.read_text());candidate=saved[0];cid=candidate['candidate_id']
            first=sum(candidate['metrics'][s+'_first_exact'] for s in SPLITS)
            directions=sum(candidate['metrics'][s+'_direction_matches'] for s in SPLITS)
            lines+=['',f'Opening-reference fit leader `{cid}`: {directions}/210 directional thresholds, {first}/210 source-conditioned first signals.']
            full_path=opening_dir/f'full_autonomous_{cid}_ledger'/'report.json'
            if full_path.exists():
                r=json.loads(full_path.read_text())['result']
                lines+=['',f'Autonomous replay: {r["completed_blocks"]}/{r["total_blocks"]} chunks; {r["exact_entries"]}/210 exact entries, {r["extra_entries"]} extras, {r["exact_exits_for_exact_entries"]} matching exits among exact entries. Complete history: {r["complete_history"]}.',
                    '',f'[Every-trade replay comparison]({relative}full_autonomous_{cid}_ledger/source_trade_comparison.csv).']
            for control in (f for f in saved if f.get('control_for')):
                control_id=control['candidate_id'];seed=control['control_for']
                paths=[opening_dir/f'full_autonomous_{identity}_ledger'/'report.json' for identity in (control_id,seed)]
                if not all(p.exists() for p in paths):continue
                results=[json.loads(p.read_text())['result'] for p in paths]
                if not all(r['complete_history'] for r in results):continue
                evidence=atm_control_evidence(opening_dir,control)
                lines+=['','### Same-formula ATM input control','',
                    'This comparison keeps the price-change expression, alpha, volume ratio, volatility window, rank thresholds, sizing and exits identical. Only the option contract selection feeding alpha2 changes.',
                    '', '| Option-factor ATM | Exact entries | Extras | Matching exits among exact entries |',
                    '|---|---:|---:|---:|']
                for label,result in zip(('Completed candle close','Completed candle open'),results):
                    lines.append(f'| {label} | {result["exact_entries"]} | {result["extra_entries"]} | {result["exact_exits_for_exact_entries"]} |')
                lines+=['',f'At published entry minutes, the opening panel gains {int(evidence.threshold_gained.sum())} directional threshold passes and loses {int(evidence.threshold_lost.sum())}. Autonomous exact entries gained: {int(evidence.exact_entry_gained.sum())}; lost: {int(evidence.exact_entry_lost.sum())}. In {int(evidence.direct_model_threshold_entry.sum())} gained entries, the close-panel replay was flat and explicitly returned no signal while the opening-panel alpha2 passes. Other differences involve changed position paths.',
                    '',f'[All 210 ranks and replay-state comparisons]({relative}atm_control_every_trade_{control_id}.csv). These explain changes in the reconstruction; they do not expose the provider\'s private trigger.',
                    '', 'Reproduce the matched control after generating the opening bank:','', '```powershell',
                    f'..\\.venv\\Scripts\\python.exe -B -u -m backtest.provider_trials --family opening_atm --atm-control {seed}',
                    f'..\\.venv\\Scripts\\python.exe -B -u -m backtest.provider_autonomous --family opening_atm --candidate {control_id}','```']
                direct=evidence.loc[evidence.direct_model_threshold_entry]
                if not direct.empty:
                    lines+=['','| Published entry, IST | Side | Alpha | Close-ATM alpha2 | Open-ATM alpha2 |',
                        '|---|---|---:|---:|---:|']
                    for v in direct.itertuples():
                        lines.append(f'| {v.entry} | {v.option_type} | {v.open_atm_alpha:.5f} | {v.close_atm_alpha2:.5f} | {v.open_atm_alpha2:.5f} |')
    volume_dir=OUT if OUT.name=='opening_volume' else OUT/'opening_volume'
    if (volume_dir/'search_design.json').exists():
        design=json.loads((volume_dir/'search_design.json').read_text())
        saved=json.loads((volume_dir/'frontier.json').read_text());chosen=saved[0]
        relative='' if volume_dir==OUT else 'opening_volume/'
        lines+=['','## Opening-ATM volume aggregation','',
            f'{design["tested_formula_recipes"]} formula recipes compare arithmetic, geometric and harmonic means of the two leg volume ratios, a minimum-ratio confirmation hypothesis, and a ratio of combined volumes. Arithmetic controls overlap the preceding opening_atm screen. Rank thresholds remain 0.8/0.2; factor lag stays five.',
            '',f'Fit-selected candidate `{chosen["candidate_id"]}` uses `{chosen["recipe"]["volume_kind"]}`. These alternatives are hypotheses; a minimum is not the stated average. No service rule or risk allocation has changed.',
            '',f'[Volume definitions]({relative}search_design.json), [all candidate/source entry checks]({relative}frontier_every_trade.csv).']
        for f in saved:
            if f.get('control_type')!='volume_aggregation':continue
            cid=f['candidate_id'];seed=f['control_for']
            paths=[volume_dir/f'full_autonomous_{identity}_ledger'/'report.json' for identity in (seed,cid)]
            if not all(p.exists() for p in paths):continue
            results=[json.loads(p.read_text())['result'] for p in paths]
            if not all(r['complete_history'] for r in results):continue
            evidence=atm_control_evidence(volume_dir,f)
            lines+=['','### Matched volume-aggregation control','',
                'Only the volume aggregation changes. The same index change, alpha, CE/PE ratios, volatility, factor lag, ATM reference, rank cutoffs, sizing and exit policy apply to both replays.',
                '', '| Aggregation | Exact entries | Extras | Matching exits among exact entries |',
                '|---|---:|---:|---:|']
            for label,r in zip(('Fit-selected alternative','Arithmetic mean'),results):
                lines.append(f'| {label} | {r["exact_entries"]} | {r["extra_entries"]} | {r["exact_exits_for_exact_entries"]} |')
            lines+=['',f'The alternative gains {int(evidence.threshold_gained.sum())} directional threshold passes and loses {int(evidence.threshold_lost.sum())} at source entries. Autonomous exact entries gained: {int(evidence.exact_entry_gained.sum())}; lost: {int(evidence.exact_entry_lost.sum())}. Direct model threshold entries: {int(evidence.direct_model_threshold_entry.sum())}. A stronger source-conditioned score alone does not establish better replication.',
                '',f'[All 210 components and replay-state comparisons]({relative}volume_control_every_trade_{cid}.csv). Reconstructed triggers do not identify the provider\'s private alpha values.',
                '', 'Reproduce the arithmetic control after generating this bank:','', '```powershell',
                f'..\\.venv\\Scripts\\python.exe -B -u -m backtest.provider_trials --family opening_volume --volume-control {seed}',
                f'..\\.venv\\Scripts\\python.exe -B -u -m backtest.provider_autonomous --family opening_volume --candidate {cid}','```']
            direct=evidence.loc[evidence.direct_model_threshold_entry]
            if not direct.empty:
                lines+=['','| Published entry, IST | Side | Alpha | Arithmetic alpha2 | Alternative alpha2 |',
                    '|---|---|---:|---:|---:|']
                for v in direct.itertuples():
                    lines.append(f'| {v.entry} | {v.option_type} | {v.candidate_alpha:.5f} | {v.control_alpha2:.5f} | {v.candidate_alpha2:.5f} |')
    pcr_dir=OUT if OUT.name=='opening_pcr' else OUT/'opening_pcr'
    if (pcr_dir/'search_design.json').exists():
        design=json.loads((pcr_dir/'search_design.json').read_text())
        pcr_design=design.get('opening_pcr_design')
        if pcr_design is not None:
            saved=json.loads((pcr_dir/'frontier.json').read_text());chosen=saved[0]
            relative='' if pcr_dir==OUT else 'opening_pcr/'
            lines+=['','## Put/call volume-ratio interpretations','',
                f'{design["tested_formula_recipes"]} opening-selected ATM formulas compare PE/CE, CE/PE, reciprocal-pair averages and ordinary per-leg-volume controls. The scan tests raw ratios, trailing mean-of-minute ratios, ratio-of-trailing means, and baseline-normalized ratios. Simple/log return volatility uses 300 observations; factor lags are zero or five. Alpha and 0.8/0.2 cutoffs remain unchanged.',
                '', 'Missing and zero denominators stay missing. Mean-of-ratio windows of one are omitted because they duplicate literal ratios. Native arithmetic formulas overlap earlier banks and serve as controls. These definitions are explicit alternatives to an unspecified volume ratio, not recovered private parameters.',
                '',f'Fit-selected leader `{chosen["candidate_id"]}` uses `{chosen["recipe"]["volume_kind"]}`.',
                '',f'[Definitions and selection]({relative}search_design.json), [every-trade entry checks]({relative}frontier_every_trade.csv).']
            recovery_path=pcr_dir/'settlement_recovery.json'
            if recovery_path.exists():
                recovery=json.loads(recovery_path.read_text())
                lines+=['','### Settlement-data recovery','',
                    f'The first matched-control run failed to obtain the official {recovery["expiry"]} settlement archive, leaving an expired position open and suppressing later entries. That run was preserved separately and is excluded from strategy comparisons. A retry recovered the original dated archive; NIFTY 50 final index close is {recovery["official_index_close"]:.2f}. The control was restarted with this verified input.',
                    '', f'[Official NSE daily archive]({recovery["official_archive_url"]}), [recovery record]({relative}settlement_recovery.json). The research runner now retries transient archive failures and stops if a required settlement remains unavailable. No minute-close proxy or invented option price is used.']
            for f in saved:
                if f.get('control_type')!='volume_aggregation':continue
                cid=f['candidate_id'];seed=f['control_for']
                paths=[pcr_dir/f'full_autonomous_{identity}_ledger'/'report.json' for identity in (seed,cid)]
                if not all(p.exists() for p in paths):continue
                results=[json.loads(p.read_text())['result'] for p in paths]
                if not all(r['complete_history'] for r in results):continue
                evidence=atm_control_evidence(pcr_dir,f)
                lines+=['','### Matched per-leg-volume control','',
                    'Only the volume factor definition changes. The price change, alpha, volatility, factor lag, ATM reference, thresholds, sizing and exits remain identical.',
                    '', '| Volume factor | Exact entries | Extras | Matching exits among exact entries |',
                    '|---|---:|---:|---:|']
                for label,r in zip(('Selected cross-leg ratio','Per-leg relative-volume arithmetic mean'),results):
                    lines.append(f'| {label} | {r["exact_entries"]} | {r["extra_entries"]} | {r["exact_exits_for_exact_entries"]} |')
                lines+=['',f'Source threshold passes gained: {int(evidence.threshold_gained.sum())}; lost: {int(evidence.threshold_lost.sum())}. Autonomous exact entries gained: {int(evidence.exact_entry_gained.sum())}; lost: {int(evidence.exact_entry_lost.sum())}. Direct model threshold entries: {int(evidence.direct_model_threshold_entry.sum())}. Other changes involve altered position paths.',
                    '',f'[All 210 factor and replay comparisons]({relative}volume_control_every_trade_{cid}.csv). Components are reconstructed hypotheses, not disclosed provider alpha values.']
                direct=evidence.loc[evidence.direct_model_threshold_entry]
                if not direct.empty:
                    lines+=['','| Published entry, IST | Side | Alpha | Per-leg alpha2 | Cross-ratio alpha2 |',
                        '|---|---|---:|---:|---:|']
                    for v in direct.itertuples():
                        lines.append(f'| {v.entry} | {v.option_type} | {v.candidate_alpha:.5f} | {v.control_alpha2:.5f} | {v.candidate_alpha2:.5f} |')
    cumulative_dir=OUT if OUT.name=='contract_cumulative' else OUT/'contract_cumulative'
    if (cumulative_dir/'search_design.json').exists():
        design=json.loads((cumulative_dir/'search_design.json').read_text())
        selected=design.get('fit_selected_continuous_cumulative_leader')
        relative='' if cumulative_dir==OUT else 'contract_cumulative/'
        lines+=['','## Actual contract cumulative-volume hypothesis','',
            f'{design["tested_formula_recipes"]} formulas compare native minute volume with complete daily totals of the same selected expiry and strike. Totals reset each date and require every earlier regular-session candle. Both source-entry prefixes are complete for all 210 trades.',
            '', 'Each leg uses short-window volume divided by its own trailing mean; CE and PE ratios are averaged. Short windows are 1/5/15, baselines 20/60/300, simple/log return volatility 300, and factor lag 0/5. This is a candidate interpretation of the unspecified volume input, not evidence of the provider formula.',
            '', 'Additional session-average inputs divide the same fixed-contract cumulative total by completed regular-session minutes. One variant normalizes this average by its own trailing mean. Another divides current minute volume directly by this session average (short=1; no separate trailing denominator). Missing daily prefixes remain unknown. Elapsed minutes convert volume units; they are not a fitted time filter.',
            '',f'Continuous cumulative fit leader: `{selected}`. Native controls may score better in the global frontier; the cumulative leader is retained separately to test this input fairly.',
            '',f'[Panel coverage]({relative}panel_design.json), [trial definitions]({relative}search_design.json).']
        saved=json.loads((cumulative_dir/'frontier.json').read_text())
        linked=design.get('contract_volume_control_links',{})
        comparisons=[{**next(f for f in saved if f['candidate_id']==cid),'control_for':seed,'control_type':'volume_input'} for seed,cid in linked.items()] if linked else saved
        for control in comparisons:
            if control.get('control_type')!='volume_input':continue
            cid=control['candidate_id'];seed=control['control_for']
            seed_kind=next(f['recipe']['volume_kind'] for f in saved if f['candidate_id']==seed)
            paths=[cumulative_dir/f'full_autonomous_{identity}_ledger'/'report.json' for identity in (seed,cid)]
            if not all(p.exists() for p in paths):continue
            results=[json.loads(p.read_text())['result'] for p in paths]
            if not all(r['complete_history'] for r in results):continue
            evidence=atm_control_evidence(cumulative_dir,control)
            lines+=['',f'### Matched `{seed_kind}` versus minute-volume replay','',
                '| Volume input | Exact entries | Extra entries | Matching exits among exact entries |',
                '|---|---:|---:|---:|']
            for label,r in zip((seed_kind,'Native minute volume'),results):
                lines.append(f'| {label} | {r["exact_entries"]} | {r["extra_entries"]} | {r["exact_exits_for_exact_entries"]} |')
            lines+=['',f'Source threshold passes gained: {int(evidence.threshold_gained.sum())}; lost: {int(evidence.threshold_lost.sum())}. Autonomous exact entries gained: {int(evidence.exact_entry_gained.sum())}; lost: {int(evidence.exact_entry_lost.sum())}. Direct model threshold gains: {int(evidence.direct_model_threshold_entry.sum())}. Other entry changes follow altered position paths.',
                '',f'[All 210 inputs, ranks and independent replay states]({relative}{evidence.attrs["evidence_filename"]}). Sizing, exits and the original thresholds remain identical.']
            weekly=evidence.loc[evidence.entry.dt.date.between(pd.Timestamp('2026-09-28').date(),pd.Timestamp('2026-10-01').date())]
            if not weekly.empty:
                lines+=['','| Published entry, IST | Alpha | Candidate alpha2: previous / entry | Native alpha2: previous / entry |',
                    '|---|---:|---:|---:|']
                for v in weekly.itertuples():
                    lines.append(f'| {v.entry} | {v.candidate_alpha:.5f} | {v.candidate_previous_alpha2:.5f} / {v.candidate_alpha2:.5f} | {v.control_previous_alpha2:.5f} / {v.control_alpha2:.5f} |')
                lines+=['', 'These ranks describe reconstructed inputs. A threshold alignment at the source timestamp is evidence for this hypothesis, not proof of the private trigger. Weekly profits remain provisional because 351 held-quote observations are missing. The first exit is delayed until official expiry settlement; the source exits the previous morning.']
    crossing_dir=OUT if OUT.name=='crossings' else OUT/'crossings'
    if (crossing_dir/'crossing_design.json').exists():
        design=json.loads((crossing_dir/'crossing_design.json').read_text())
        paired=pd.read_csv(crossing_dir/'formula_trials.csv')
        saved=json.loads((crossing_dir/'frontier.json').read_text())
        selected=next(f for f in saved if f['candidate_id']==design['fit_selected_crossing_leader'])
        relative='' if crossing_dir==OUT else 'crossings/'
        lines+=['','## Fresh threshold-crossing entry hypotheses','',
            f'{design["trials"]} matched rules compare level conditions, a new joint condition, a fresh alpha crossing, a fresh alpha2 crossing and simultaneous crossings on four saved reconstructions.',
            '', 'The prior observation is checked before the entry clock and position state. Opening the entry window, a new session or becoming flat does not manufacture a crossing. Missing prior ranks fail closed. This is an explicit hypothesis, not an extra criterion stated by the provider.',
            '', '| Seed bank | Level entry passes | Joint crossing | Alpha crossing | Alpha2 crossing | Both crossing |',
            '|---|---:|---:|---:|---:|---:|']
        for seed in design['seeds']:
            subset=paired.loc[paired.crossing_seed_candidate_id.eq(seed['candidate_id'])]
            counts={r.entry_event:sum(getattr(r,s+'_direction_matches') for s in SPLITS) for r in subset.itertuples()}
            lines.append(f'| {seed["family"]} | {counts["level"]} | {counts["joint"]} | {counts["alpha"]} | {counts["alpha2"]} | {counts["both"]} |')
        cid=selected['candidate_id'];recipe=selected['recipe'];seed=recipe['crossing_seed_candidate_id']
        lines+=['',f'Fit-selected crossing rule: `{cid}`, `{recipe["entry_event"]}`, seeded from `{seed}`. Selection uses fit scores and excludes unchanged level controls. Level controls have stronger conditional scores; fewer signal episodes alone do not establish improvement.',
            '',f'[Every-trade current and prior ranks]({relative}entry_crossing_every_trade.csv), [exact definitions and selection]({relative}crossing_design.json).']
        evidence=crossing_replay_evidence(crossing_dir,selected)
        if evidence is not None:
            base_root=crossing_dir.parent;family=recipe['crossing_seed_family']
            baseline=(base_root if family=='main' else base_root/family)/f'full_autonomous_{seed}_ledger'/'report.json'
            results=[json.loads(p.read_text())['result'] for p in (baseline,crossing_dir/f'full_autonomous_{cid}_ledger'/'report.json')]
            lines+=['','### Full-history crossing replay','',
                '| Entry criterion | Exact entries | Extra entries | Matching exits among exact entries |',
                '|---|---:|---:|---:|']
            for label,r in zip(('Both ranks beyond cutoff','Fresh crossing'),results):
                lines.append(f'| {label} | {r["exact_entries"]} | {r["extra_entries"]} | {r["exact_exits_for_exact_entries"]} |')
            lines+=['',f'Autonomous exact source entries gained: {int(evidence.exact_entry_gained.sum())}; lost: {int(evidence.exact_entry_lost.sum())}. Direct crossing rejections of formerly matched entries: {int(evidence.direct_crossing_entry_rejection.sum())}. Other changes reflect altered position paths.',
                '',f'[All 210 independent replay states]({relative}crossing_source_replay_{cid}.csv). This compares the reconstruction, not the private provider ranks.']
            direct=evidence.loc[evidence.direct_crossing_entry_rejection].head(5)
            if not direct.empty:
                lines+=['','| Published entry, IST | Side | Previous alpha / alpha2 | Entry alpha / alpha2 |',
                    '|---|---|---:|---:|']
                for v in direct.itertuples():
                    lines.append(f'| {v.entry} | {v.option_type} | {v.previous_alpha:.5f} / {v.previous_alpha2:.5f} | {v.alpha:.5f} / {v.alpha2:.5f} |')
        episode_path=crossing_dir/'entry_episode_summary.csv'
        if episode_path.exists():
            episodes=pd.read_csv(episode_path)
            lines+=['','### One trade per continuous signal episode','',
                'This audit tests whether a latch could suppress repeat entries while retaining the first eligible entry in a signal episode. Episodes follow joint ranks, alpha alone or alpha2 alone; the entry clock, session and position state do not reset them.',
                '', '| Seed bank | Joint repeated entries | Alpha repeated entries | Alpha2 repeated entries |',
                '|---|---:|---:|---:|']
            for seed in design['seeds']:
                subset=episodes.loc[episodes.seed_candidate_id.eq(seed['candidate_id'])]
                counts={r.episode_basis:r.simulated_repeated_episodes for r in subset.itertuples()}
                lines.append(f'| {seed["family"]} | {counts["joint"]} | {counts["alpha"]} | {counts["alpha2"]} |')
            lines+=['','A once-per-episode gate rejects no entries in the main, opening-ATM or harmonic seed paths, so it cannot change those deterministic paths. The boundary seed has one repeated extra entry; its downstream effect would require another independent replay. These are observed repeat counts, not a new backtest score.',
                '', f'[Every published and simulated entry episode]({relative}entry_episode_every_entry.csv), [audit definitions]({relative}entry_episode_design.json).']
    rank_dir=OUT if OUT.name=='rank_conventions' else OUT/'rank_conventions'
    if (rank_dir/'rank_design.json').exists():
        design=json.loads((rank_dir/'rank_design.json').read_text())
        saved=json.loads((rank_dir/'frontier.json').read_text())
        relative='' if rank_dir==OUT else 'rank_conventions/'
        lines+=['','## Matched rank conventions','',
            f'{design["trials"]} combinations compare six percentile and tie conventions independently for alpha and alpha2 on four fixed input models. Windows, minimum valid fractions, 0.8/0.2 cutoffs, pricing, volume, sizing and exits remain fixed.',
            '',f'{design["equivalent_alternatives_excluded"]} non-control conventions produce exactly the same eligible signals as their seeds and are excluded from selecting changed-signal alternatives. All four unchanged percentile controls reproduce the original arrays exactly, including missing values.',
            '',f'[Definitions and selection]({relative}rank_design.json).']
        audit=rank_dir/'equivalent_replay_audit.json'
        if audit.exists():
            d=json.loads(audit.read_text())
            lines+=['',f'The completed minimum-tie-rank replay reproduces all {d["all_replay_trade_rows_identical"]} seed trade rows across entry/exit timestamps, contracts, quantities, prices and P&L. It is an equivalent control, not an improvement.',
                '',f'[Replay equivalence audit]({relative}equivalent_replay_audit.json).']
        for identity in dict.fromkeys([design['fit_selected_rank_leader']]+list(design['fit_selected_by_seed'].values())):
            candidate=next(f for f in saved if f['candidate_id']==identity)
            evidence=rank_replay_evidence(rank_dir,candidate)
            if evidence is None:continue
            r=candidate['recipe'];base=rank_dir.parent/r['rank_seed_family']/f'full_autonomous_{r["rank_seed_candidate_id"]}_ledger'
            results=[json.loads((p/'report.json').read_text())['result'] for p in (base,rank_dir/f'full_autonomous_{identity}_ledger')]
            lines+=['',f'### `{identity}`: `{r["alpha_rank_convention"]}` alpha, `{r["alpha2_rank_convention"]}` alpha2','',
                '| Rank definition | Exact entries | Extras | Matching exits among exact entries |','|---|---:|---:|---:|']
            for label,result in zip(('Original percentile','Selected rank convention'),results):
                lines.append(f'| {label} | {result["exact_entries"]} | {result["extra_entries"]} | {result["exact_exits_for_exact_entries"]} |')
            lines+=['',f'Source threshold passes gained: {int(evidence.threshold_gained.sum())}; lost: {int(evidence.threshold_lost.sum())}. Exact entries gained: {int(evidence.exact_entry_gained.sum())}; lost: {int(evidence.exact_entry_lost.sum())}. Direct model threshold gains: {int(evidence.direct_model_threshold_entry.sum())}. Other entry changes follow the altered position path.',
                '',f'[All 210 ranks and independent replay states]({relative}rank_source_replay_{identity}.csv). These are reconstructed model triggers, not disclosed provider ranks.']
    family=OUT.name if OUT.name in ('fine','expanded','mixed','fixed_contract','sampling','boundaries','rank_conventions','eligibility','opening_atm','opening_volume','opening_pcr','contract_cumulative','crossings','bulk') else 'main'
    prefix='..\\.venv\\Scripts\\python.exe -B -u -m backtest.'
    commands=[prefix+'provider_price_bounds --rank-conventions'] if family=='rank_conventions' else [prefix+'provider_price_bounds --sampling-pairs'] if family=='sampling' else [prefix+'provider_price_bounds --boundaries'] if family=='boundaries' else [prefix+'provider_trials --premium-gates'] if family=='eligibility' else [prefix+'provider_trials --family crossings'] if family=='crossings' else [prefix+f'provider_trials --family {family} --limit 1000']
    if family=='bulk':commands=[prefix+'provider_price_bounds --bulk-workers 2']
    commands+=[prefix+f'provider_trials --family {family} --replay-top 1',
        prefix+f'provider_autonomous --family {family}',prefix+f'provider_trial_report --family {family}']
    if family in ('opening_atm','opening_volume','opening_pcr','contract_cumulative'):commands.insert(0,prefix+'provider_fixed_factors --opening-reference')
    if family=='contract_cumulative':commands.insert(1,prefix+'provider_fixed_factors --contract-cumulative')
    if family=='main':
        commands[1:1]=[prefix+'provider_exit_trials',prefix+'provider_exit_trials --margin',prefix+'provider_exit_trials --premium-exits',
            prefix+'provider_exit_trials --premium-fractions',prefix+'provider_exit_trials --rank-exits',prefix+'provider_exit_trials --september-bounds',prefix+'provider_research --source-audit',
            prefix+'provider_price_bounds --option-spot',prefix+'provider_price_bounds --boundaries',prefix+'provider_price_bounds --opening-reference',prefix+'provider_price_bounds --required-prices']
    lines+=['','## Reproduce','', 'From `zen_credit/`:','', '```powershell',*commands,'```','',
        'Trials checkpoint every 25 new recipes and resume from the journal. Run one formula-search worker at a time. Research candidates are not promoted into the service configuration.',
        '', 'Files: '+', '.join(f'[{label}]({name})' for label,name in (
            ('every-trade evidence','frontier_every_trade.csv'),('scorecard','frontier_scorecard.csv'),
            ('autonomous comparison','autonomous_comparison.csv'),('exit rule scores','exit_rule_trials.csv')) if (OUT/name).exists())+'.']
    (OUT/'summary.md').write_text('\n'.join(lines),encoding='utf-8')
    print(f'Summary: {len(table)} paired trials, best entry conditions {best.all_direction_matches}/210, first exact {best.all_first_exact}/210',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--family',choices=('main','fine','expanded','mixed','fixed_contract','sampling','boundaries','rank_conventions','eligibility','opening_atm','opening_volume','opening_pcr','contract_cumulative','crossings','bulk'),default='main')
    args=parser.parse_args()
    if args.family!='main':OUT=OUT/args.family
    main()
