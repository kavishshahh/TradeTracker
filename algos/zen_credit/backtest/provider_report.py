"""Build the per-trade evidence report and a self-contained replay viewer."""
import json
from datetime import date
import numpy as np
import pandas as pd
from backtest.provider_research import OUTPUT, ENTRY_QUOTE_CACHE, provider_trades
from backtest.provider_calendar import expiries_for


def build_report():
    trades=provider_trades()
    entries=pd.read_csv(OUTPUT/'entry_diagnostics.csv')
    exits=pd.read_csv(OUTPUT/'exit_diagnostics.csv')
    candidates=pd.read_csv(OUTPUT/'signal_candidates.csv')
    events=pd.read_csv(OUTPUT/'event_parameters.csv')
    details=trades.merge(entries[entries.candidate.eq('baseline')].drop(columns='candidate'),on='signal_id').merge(exits,on='signal_id')
    current=entries[entries.candidate.eq('premium_cap_200')][['signal_id','direction_matches','first_exact','first_candidate_since_previous_exit','short_premium_at_actual_direction','premium_cap_pass']]
    current=current.rename(columns={c:'corrected_'+c for c in current.columns if c!='signal_id'})
    details=details.merge(current,on='signal_id')
    event_fields=['signal_id','spot','atm_strike','price_change','volume_ratio','atm_volatility','ce_iv','pe_iv','ce_oi','pe_oi']
    details=details.merge(events[events.event.eq('entry')][event_fields],on='signal_id')
    exit_fields=events[events.event.eq('exit')][['signal_id','spot','ce_iv','pe_iv']].rename(
        columns={'spot':'spot_at_exit','ce_iv':'ce_iv_at_exit','pe_iv':'pe_iv_at_exit'})
    details=details.merge(exit_fields,on='signal_id')
    details['spot_change_points']=details.spot_at_exit-details.spot
    details['short_leg_pnl']=(details.short_entry-details.short_exit)*details.units
    details['hedge_leg_pnl']=(details.hedge_exit-details.hedge_entry)*details.units
    details['holding_minutes']=(details.exit-details.entry).dt.total_seconds()/60
    reference=pd.read_csv(ENTRY_QUOTE_CACHE)
    reference.minute=pd.to_datetime(reference.minute,utc=True).dt.tz_convert('Asia/Kolkata')
    details=details.merge(reference[['minute','strike','reference_open']].rename(columns={
        'minute':'entry_minute','strike':'opening_reference_strike','reference_open':'nifty_bar_open'}),on='entry_minute')
    details['width_matches_400']=(details.short_strike-details.hedge_strike).abs().eq(400)
    details['nearest_expiry_matches']=[e==expiries_for(t.date())[0] for e,t in zip(details.expiry,details.entry)]
    details['atm_matches_last_completed_candle']=details.short_strike.eq(details.atm_strike)
    details['atm_matches_completed_candle_open']=details.short_strike.eq(details.opening_reference_strike)
    details['published_short_premium_within_200']=details.short_entry.le(200)
    details['sizing_matches']=np.floor(320000*details.allocation_pct/100/details.margin_per_lot).eq(details.lots)
    details['overlaps_previous_record']=details.entry.lt(details.exit.cummax().shift())
    details['same_minute_as_previous_exit']=details.entry_minute.eq(details.exit_minute.shift())
    def entry_text(t):
        if not t.available:
            return 'Required indicator unavailable; entry trigger cannot be tested.'
        if not t.direction_matches:
            return 'The completed-candle baseline does not satisfy both thresholds for this direction.'
        if not t.corrected_premium_cap_pass:
            return 'Both ranks align, but the selected short candle close exceeds the inferred 200 premium limit. Published fill is lower; intraminute quote timing remains unresolved.'
        direction='upward' if t.direction==1 else 'downward'
        timing='The first candidate minute matches.' if t.corrected_first_exact else 'Earlier candidate signals exist, or timing conflicts with source records; entry timing remains unexplained.'
        return f'Both baseline ranks support {direction} short-term momentum; open-reference strike and premium eligibility align. {timing} This is compatibility, not proof of the private trigger.'
    def exit_text(t):
        if not t.pnl_reconciles:
            return 'Source P&L/quantity inconsistent; excluded from exit calibration.'
        if t.exit_recorded_after_expiry:
            return 'Exit recorded after expiry; possible administrative/settlement timestamp, not an executable option quote.'
        near=pd.notna(t.baseline_minutes_before_exit) and abs(t.baseline_minutes_before_exit)<=2
        gap=' Quote gaps prevent ruling out earlier crossings.' if not t.complete_to_exit else ''
        if near:
            return f'Compatible with {t.baseline_exit_reason} under target 10 / stop +45 / dated clock, within two minutes.{gap} Minute closes cannot prove the tick trigger.'
        if pd.notna(t.baseline_minutes_before_exit) and t.baseline_minutes_before_exit>2:
            return f'Baseline would exit {t.baseline_minutes_before_exit:.0f} minutes earlier ({t.baseline_exit_reason}); rule does not reproduce this exit.{gap}'
        if t.debit-t.credit>=35:
            return f'Loss exit is compatible with a stop, but the exact threshold/first crossing is unverified.{gap}'
        if t.debit<=12:
            return f'Low closing premium is compatible with a premium target; exact first crossing is unverified.{gap}'
        return f'Exit trigger unresolved by the tested minute-close rules.{gap}'
    details['entry_explanation']=[entry_text(t) for t in details.itertuples()]
    details['exit_explanation']=[exit_text(t) for t in details.itertuples()]
    details['market_observation']=[
        (f'NIFTY changed {t.spot_change_points:+.2f} points between available entry/exit candles. '
         if pd.notna(t.spot_change_points) else 'Entry-to-exit NIFTY change unavailable at the recorded timestamps. ')
        +f'Published leg prices imply short-leg P&L {t.short_leg_pnl:+.2f}, hedge-leg P&L {t.hedge_leg_pnl:+.2f}. '
        +'These observations do not isolate delta, volatility and time decay effects.' for t in details.itertuples()]
    details.to_csv(OUTPUT/'trade_analysis.csv',index=False)
    baseline=candidates[candidates.candidate.eq('baseline')].iloc[0]
    selected=candidates[candidates.candidate.eq('selected_fit')].iloc[0]
    corrected=candidates[candidates.candidate.eq('premium_cap_200')].iloc[0]
    split_names=('fit','validation','evaluation','case_study')
    total=lambda row,suffix:sum(int(row[f'{s}_{suffix}']) for s in split_names)
    summary={
        'trades':len(trades),'reported_pnl':float(trades.pnl_reported.sum()),
        'complete_minute_paths':int(details.complete_to_exit.sum()),
        'missing_held_spread_minutes':int(details.missing_spread_minutes.sum()),
        'source_pnl_discrepancies':int((~trades.pnl_reconciles).sum()),
        'after_expiry_exit_records':int(trades.exit_recorded_after_expiry.sum()),
        'overlapping_records':int(details.overlaps_previous_record.sum()),
        'same_minute_reentries':int(details.same_minute_as_previous_exit.sum()),
        'candidate_rows':len(candidates),
        'baseline_direction_matches':total(baseline,'direction_matches'),
        'baseline_first_minute_matches':total(baseline,'first_exact'),
        'selected_direction_matches':total(selected,'direction_matches'),
        'selected_first_minute_matches':total(selected,'first_exact'),
        'width_400_matches':int(details.width_matches_400.sum()),
        'nearest_expiry_matches':int(details.nearest_expiry_matches.sum()),
        'atm_last_completed_candle_matches':int(details.atm_matches_last_completed_candle.sum()),
        'capital_sizing_matches':int(details.sizing_matches.sum()),
        'opening_price_atm_matches':int(details.atm_matches_completed_candle_open.sum()),
        'published_short_premium_within_200':int(details.published_short_premium_within_200.sum()),
        'corrected_direction_matches':total(corrected,'direction_matches'),
        'corrected_first_minute_matches':total(corrected,'first_exact'),
        'baseline_flat_signal_episodes':total(baseline,'flat_signal_episodes'),
        'corrected_flat_signal_episodes':total(corrected,'flat_signal_episodes'),
        'five_minute_move_direction_matches':int((details.price_change*details.direction>0).sum()),
        'entries_1015_to_1035':int((details.entry.dt.hour*60+details.entry.dt.minute).between(615,635).sum()),
        'entry_volume_ratio_above_one':int(details.volume_ratio.gt(1).sum()),
    }
    ec=pd.read_csv(OUTPUT/'exit_candidate_summary.csv')
    chosen=ec[ec.target.eq(10)&ec.stop_rule.astype(str).eq('45')&ec.schedule.eq('dated')]
    summary['baseline_exit_matches_within_two_minutes']=int(chosen.matches_within_two_minutes.sum())
    (OUTPUT/'findings.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    lines=['# Zen Credit: all-trade replay and reverse-engineering findings','',
        '**The private entry formula has not been recovered. The existing algorithm is not a verified replica.**','',
        f'Analyzed {len(trades)} provider trades from 9 July 2025 through 1 October 2026. Source-reported P&L: INR {summary["reported_pnl"]:,.2f}, before any independently modeled costs. This is the provider ledger, not profit earned by our reconstructed algorithm.','',
        '## What the data supports','',
        f'- All {summary["width_400_matches"]} spreads have a 400-point hedge and all {summary["nearest_expiry_matches"]} use the nearest expiry.',
        f'- Using the last completed index candle’s close matches {summary["atm_last_completed_candle_matches"]}/210 short strikes; its open resolves all 41 disagreements.',
        f'- **{summary["opening_price_atm_matches"]}/210 short strikes equal the ATM strike from the opening price of the last completed NIFTY candle.** This matches every record and is now the entry strike reference. The current market spot is still recorded separately.',
        f'- **{summary["published_short_premium_within_200"]}/210 published short fills are at or below 200**, including two exactly at 200. An inferred 200 premium eligibility limit is now implemented. Three original-contract candle closes exceed 200 despite lower published fills; minute candles cannot reproduce those exact quotes.',
        f'- All {summary["capital_sizing_matches"]} quantities reconcile to floor(320,000 × allocation / broker margin per lot). Historical broker margins differ from our fixed margin estimate.',
        f'- **{summary["five_minute_move_direction_matches"]}/210 spreads follow the direction of the observed five-minute NIFTY move.** 108/109 put spreads follow a rise and 99/101 call spreads follow a fall. This is strong evidence for a momentum entry mapping; it does not identify the private volume/volatility filter.',
        f'- **{summary["entries_1015_to_1035"]}/210 entries occur between 10:15 and 10:35.** Of the 52 later entries, 26 are second entries on their date and 26 are first entries. There is no one-trade-per-day rule in the published ledger.',
        f'- **{summary["entry_volume_ratio_above_one"]}/210 entries have a volume ratio above 1** using our mean-five-minute / mean-300-minute CE/PE volume measure. This is consistent with volume participation but is not a universal eligibility condition: 16 entries do not satisfy it, and time-of-day volume must be controlled before inferring causation.',
        '- Scheduled exits cluster at 15:00 in the earlier history and 14:53 from July 2026. A dated historical replay profile implements a 1 July entry-date boundary; the exact private switch date is unknown between the last observed 15:00 exit (25 June) and first regular 14:53 exit (2 July). Forward defaults remain 14:53.',
        '- A 400-point put hedge below the short strike is OTM relative to an ATM short put, despite the public description calling it ITM.','',
        '## Entry tests','',
        f'The finite bank has {len(candidates)} rows, including formula variants, timing diagnostics and baseline aliases. It covers spot changes, lagged-open normalization, parity-implied forward prices, option-return differences, volume windows, combined/relative volume, volatility of same-contract returns, overnight returns, rolling ATM prices, price levels, IV and OI. These are plausible interpretations, not every possible private formula.','',
        '| Period | Trades | Baseline direction | Baseline first minute | Fit-selected direction | Fit-selected first minute |',
        '|---|---:|---:|---:|---:|---:|']
    for s in split_names:
        lines.append(f'| {s} | {baseline[s+"_trades"]} | {baseline[s+"_direction_matches"]} | {baseline[s+"_first_exact"]} | {selected[s+"_direction_matches"]} | {selected[s+"_first_exact"]} |')
    lines+=['',
        f'The table compares the original signal reconstruction with the alpha2 variant selected on fit data. The corrected strategy retains the original ranks, uses the candle-open strike reference and applies the inferred premium limit. It agrees with {summary["corrected_direction_matches"]}/210 directions and {summary["corrected_first_minute_matches"]}/210 first eligible minutes in the conditional test. Flat-signal episodes fall from {summary["baseline_flat_signal_episodes"]} to {summary["corrected_flat_signal_episodes"]}; this does not mean all remaining episodes would become orders.',
        '',
        'Strike-reference and premium-limit hypotheses were found by inspecting the full ledger. Their chronological scores are descriptive checks, not untouched out-of-sample validation. The premium ceiling is inferred from fills, not disclosed as an exact private rule.',
        '',
        'Fit: entries through February 2026; validation: March–June; evaluation: July–August; September: previously inspected case studies. Formula selection uses fit data only. Exit-rule hypotheses were informed by the observed ledger and do not have an untouched holdout. Additional timing/body diagnostics are exploratory.',
        '',
        '**Timing is conditional on the provider’s recorded position history.** For each entry, find the first eligible signal after the previous provider exit. This is not an autonomous backtest and does not claim those signals would all become actual orders. Flat-signal minutes and episodes include legitimate entry signals as well as extra opportunities; see signal_candidates.csv. Overlapping records and same-minute reentries limit the timing metric.',
        '',
        'The fit-selected volume/volatility variant improves training timing but reduces directional agreement in later periods. It has not been promoted to the trading algorithm. Delays, multi-bar confirmation and alternative candle bodies are reported separately. NONCAUSAL_containing_candle deliberately uses the later close of the entry candle as a diagnostic and must never be used in live decisions.',
        '',
        'Opening-price alpha variants were explored after discovering the strike-reference pattern. They did not reliably improve entry replication. Alpha2 still uses the original indicator ATM panel; identifying the strike used for an order does not prove the private indicator’s ATM convention.',
        '', '## Exit replay and limitations','',
        f'{summary["complete_minute_paths"]}/210 trades have both original legs available at every index decision minute through the recorded exit. There are {summary["missing_held_spread_minutes"]:,} missing held-spread minutes across the remaining paths. Coverage is minute-close coverage, not complete tick history.',
        '',
        'The exit grid compares net-premium targets 5/10/15, stops of +40/+45/+50 points or 5% of inferred normal-day margin, and 14:53/15:00/dated schedules. First crossings are measured from reported entry credit. A two-minute post-exit diagnostic window allows for candle timing; those later values are explicitly not available at the recorded exit. Minute closes can miss intraminute touches, so these tests cannot prove the broker’s exact stop or target.',
        '',
        f'The existing target 10 / stop +45 with the dated schedule matches {summary["baseline_exit_matches_within_two_minutes"]}/{summary["complete_minute_paths"]} complete-path exits within two minutes. The grid’s +40 stop scores higher on this sample, but selecting a smaller stop to offset missing intraminute touches is not evidence that the private stop is +40; no stop change was promoted.',
        '',
        'Missing original legs are never replaced with another strike or expiry, set to zero, or forward-filled. Dhan’s expired archive is limited to near-expiry ATM ±10 and other expiry ATM ±3. Active October contracts use security-ID histories; expired contracts use the rolling archive. The feeds can differ.',
        '',
        f'Source issues: {summary["source_pnl_discrepancies"]} P&L discrepancy, {summary["after_expiry_exit_records"]} exits recorded after expiry, {summary["overlapping_records"]} entry overlapping a previous recorded position, and {summary["same_minute_reentries"]} reentries in the same minute as a previous exit. All are retained and flagged.',
        '',
        'Signal 68b6768710b8ef5d6802773a reports INR 2,576.25, while its displayed leg prices and full quantity imply INR 7,728.75. Its summary also splits quantities inconsistently. It is excluded from exit calibration. The UI “Targets Hit” label counts displayed target rows and is not sufficient evidence of the economic exit trigger.',
        '', '## Your two screenshots','',
        '| Entry → exit (IST) | Short / hedge CE | Published P&L | Evidence |',
        '|---|---|---:|---|',
        '| 28 Sep 10:18 → 29 Sep 09:27 | 22,850 / 23,250 | INR 23,686.00 | Baseline ranks at entry ≈0.071 / 0.085 support bearish direction, but it had generated a bullish signal at 10:15. Exit net premium 10.15 is consistent with a near-10 target; missing hedge quotes prevent verification of first crossing. |',
        '| 30 Sep 10:33 → 1 Oct 14:53 | 22,750 / 23,150 | INR 34,547.50 | Baseline ranks ≈0.046 / 0.051 support bearish direction, but it signalled bearish at 10:31 and bullish at 10:15. Complete path supports the scheduled 14:53 exit. |',
        '',
        'Combined published P&L: **INR 58,233.50**. The second position crossed a 10%-of-margin profit level at 12:11 on 1 October and stayed open until 14:53, contradicting a universal 10%-of-margin take-profit rule.','',
        '## Autonomous check of the corrected algorithm','',
        'A separate replay from 28 September through 1 October, starting flat and using the corrected strike reference, premium limit and dated schedule, still generates five entries: four closed and one open at the period end. It enters put spreads at 10:15 on 28 and 30 September, instead of the provider’s later call spreads. This demonstrates that the missing entry condition remains material.',
        '',
        'The simulation reports INR -31,583.50 realized and INR +6,207.50 unrealized, with 24 missing held-leg quote minutes. These figures are provisional and exclude costs. They must not be presented as the provider’s results. See autonomous_recent/summary.md and autonomous_recent/trades.csv.','',
        '## Files and reproduction','',
        '- Open replay.html to select any trade and inspect its fixed-contract price path, entry indicators and findings.',
        '- trade_analysis.csv: one row per trade, conditions, timing comparison, exit explanation and source flags.',
        '- event_parameters.csv: observed ATM prices, volumes, returns, IV, OI and baseline components at each entry and exit, using that trade’s expiry.',
        '- entry_parameters.csv and signal_candidates.csv: candidate values and chronological scorecards.',
        '- actual_contract_paths.csv.gz: each original leg at each minute; the last two minutes after exit are diagnostic only.',
        '- exit_candidates_per_trade.csv and exit_candidate_summary.csv: exit-rule comparisons.',
        '', 'From zen_credit, using the existing cache:', '', '```powershell',
        r'..\.venv\Scripts\python.exe -B -m backtest.provider_research --prepare-features',
        r'..\.venv\Scripts\python.exe -B -m backtest.provider_research --prepare-entry-quotes',
        r'..\.venv\Scripts\python.exe -B -m backtest.provider_signals',
        r'..\.venv\Scripts\python.exe -B -m backtest.provider_research --replay-actual',
        r'..\.venv\Scripts\python.exe -B -m backtest.provider_report','```','',
        'The download-only command resumes missing market requests. No live orders are placed. Historical profile flag for the autonomous simulator: --provider-history-rules. Entry replication remains unresolved; changing thresholds to force these two examples would overfit.','',
        '## Sources','',
        '- [Provider strategy and trade history](https://algos.dhan.co/managers/stratzy/zen-credit-spread-overnight/68596cd26aa2cba24bbb67da?tab=algo-performance)',
        '- [Dhan expired options archive](https://dhanhq.co/docs/v2/expired-options-data/)',
        '- [Dhan historical candles](https://dhanhq.co/docs/v2/historical-data/)',
        '- Dated NSE calendar, expiry and lot-size sources are recorded in backtest/provider_calendar.py and backtest/nifty_2026.py.','']
    (OUTPUT/'summary.md').write_text('\n'.join(lines),encoding='utf-8')
    build_viewer(details,summary)
    print(json.dumps(summary,indent=2))


def build_viewer(details,summary):
    paths=pd.read_csv(OUTPUT/'actual_contract_paths.csv.gz')
    signals=pd.read_csv(OUTPUT/'baseline_minute_signals.csv.gz')
    signals.minute=pd.to_datetime(signals.minute,utc=True)
    payload=[]
    for t in details.itertuples():
        p=paths[paths.signal_id.eq(t.signal_id)]
        s=signals[(signals.minute>=t.entry_minute-pd.Timedelta(minutes=15))&(signals.minute<=t.entry_minute+pd.Timedelta(minutes=5))]
        chart=[[str(r.minute),r.net,r.short,r.hedge] for r in p.itertuples()]
        payload.append({'id':t.signal_id,'entry':str(t.entry),'exit':str(t.exit),'entry_minute':str(t.entry_minute),
            'expiry':str(t.expiry),'legs':f'{t.short_strike:g}/{t.hedge_strike:g} {t.option_type}',
            'pnl':t.pnl_reported,'units':t.units,'credit':t.credit,'debit':t.debit,'alpha':t.alpha,'alpha2':t.alpha2,
            'entry_explanation':t.entry_explanation+' Reference NIFTY open '+f'{t.nifty_bar_open:.2f}'+
                ', short strike '+f'{t.opening_reference_strike:.0f}'+', selected short candle close '+
                f'{t.corrected_short_premium_at_actual_direction:.2f}'+'.',
            'exit_explanation':t.exit_explanation+' '+t.market_observation,
            'missing':t.missing_spread_minutes,'path':chart,'signals':[[str(r.minute.tz_convert('Asia/Kolkata')),r.alpha,r.alpha2] for r in s.itertuples()]})
    encoded=json.dumps(payload,default=str).replace('NaN','null').replace('Infinity','null').replace('</','<\\/')
    html='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Zen Credit · trade replay</title><style>
body{font:16px system-ui,sans-serif;background:#f3f5f8;color:#182536;margin:0}main{max-width:1180px;margin:auto;padding:30px}h1{font-size:30px;margin-bottom:8px}.muted{color:#526177}.note{background:#fff3d4;padding:16px;border-radius:10px;line-height:1.5}section{background:white;padding:20px;border-radius:12px;margin-top:18px}select{font:inherit;width:100%;padding:10px}#facts{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin:20px 0}.big{font-size:22px;font-weight:650}svg{width:100%;height:auto}p{line-height:1.55}.legend{font-size:13px;color:#526177}a{color:#174eaf}#tip{min-height:22px;font-size:14px} @media(max-width:600px){#facts{grid-template-columns:1fr 1fr}main{padding:15px}}</style>
<main><h1>Zen Credit · actual trade replay</h1><p class="muted">210 provider records · July 2025–October 2026 · all times IST</p>
<div class="note"><b>The private entry formula is unresolved.</b> These charts replay the provider’s original contracts. They are not profits generated by our algorithm. Missing prices remain gaps; completed candles cannot reveal exact intraminute triggers.</div>
<section><label for="trade">Select a trade</label><select id="trade"></select><div id="facts"></div><p id="entryText"></p><p id="exitText"></p></section>
<section><h2>Original spread: short premium − hedge premium</h2><p class="legend">Blue: observed net premium · red: hypothesized stop (entry +45) · green: target 10 · grey dashed: reported exit minute. The final two candles are post-exit diagnostics. Horizontal spacing counts observed trading minutes, excluding overnight closures.</p><svg id="price" viewBox="0 0 1100 330" role="img" aria-label="Original spread premium path"></svg><div id="tip">Move over the chart for candle values.</div></section>
<section><h2>Baseline entry conditions</h2><p class="legend">Blue: alpha · orange: alpha2 · thresholds 0.2 / 0.8 · dashed line: actual entry. Both ranks must exceed 0.8 for puts or fall below 0.2 for calls.</p><svg id="signal" viewBox="0 0 1100 250" role="img" aria-label="Entry alpha and alpha2"></svg></section>
<section><h2>Evidence and limitations</h2><p>118 trades have uninterrupted minute-close paths through the reported exit. Other paths have absent quotes or exits recorded after expiry. Dhan’s expired archive restricts available strikes. No missing hedge is assumed worthless.</p><p><a href="summary.md">Full findings</a> · <a href="trade_analysis.csv">All-trade analysis CSV</a> · <a href="event_parameters.csv">Entry and exit parameters</a> · <a href="signal_candidates.csv">Candidate scorecard</a></p></section></main>
<script>const data=PAYLOAD;const sel=document.getElementById('trade');const fmt=n=>n==null?'Unavailable':Number(n).toLocaleString('en-IN',{maximumFractionDigits:2});
for(let i=0;i<data.length;i++){let o=document.createElement('option');o.value=i;o.textContent=`${i+1}. ${data[i].entry.slice(0,16)} | ${data[i].legs} | ₹${fmt(data[i].pnl)}`;sel.append(o)}
const el=(tag,attrs)=>{let e=document.createElementNS('http://www.w3.org/2000/svg',tag);for(let [k,v] of Object.entries(attrs))e.setAttribute(k,v);return e};
function chart(id,rows,cols,limits,lines,mark){let svg=document.getElementById(id);svg.replaceChildren();let H=id==='price'?330:250,L=65,R=1080,T=20,B=H-40;let vals=rows.flatMap(r=>cols.map(c=>r[c])).filter(v=>v!=null);let min=limits?limits[0]:Math.min(0,...vals,...lines.map(l=>l[0])),max=limits?limits[1]:Math.max(1,...vals,...lines.map(l=>l[0]))*1.08;let x=i=>L+i/Math.max(1,rows.length-1)*(R-L),y=v=>B-(v-min)/(max-min)*(B-T);
for(let i=0;i<=4;i++){let v=min+(max-min)*i/4;svg.append(el('line',{x1:L,x2:R,y1:y(v),y2:y(v),stroke:'#e5e9ee'}));let tx=el('text',{x:L-8,y:y(v)+4,'text-anchor':'end','font-size':12,fill:'#526177'});tx.textContent=v.toFixed(1);svg.append(tx)}
for(let [v,c] of lines)svg.append(el('line',{x1:L,x2:R,y1:y(v),y2:y(v),stroke:c,'stroke-dasharray':'6 4'}));
for(let k=0;k<cols.length;k++){let path='',gap=true;rows.forEach((r,i)=>{if(r[cols[k]]==null){gap=true;return}path+=(gap?'M':'L')+x(i)+','+y(r[cols[k]])+' ';gap=false});svg.append(el('path',{d:path,fill:'none',stroke:k?'#d77b16':'#2768bb','stroke-width':2}))}
let mi=rows.findIndex(r=>new Date(r[0])>=new Date(mark));if(mi>=0)svg.append(el('line',{x1:x(mi),x2:x(mi),y1:T,y2:B,stroke:'#687583','stroke-dasharray':'3 4'}));
for(let i of [0,Math.floor((rows.length-1)/2),rows.length-1]){if(i<0)continue;let tx=el('text',{x:x(i),y:H-12,'text-anchor':i===0?'start':i===rows.length-1?'end':'middle','font-size':12,fill:'#526177'});tx.textContent=rows[i]?.[0].slice(5,16)||'';svg.append(tx)}
if(id==='price')svg.onmousemove=e=>{let box=svg.getBoundingClientRect(),i=Math.round(((e.clientX-box.left)*1100/box.width-L)/(R-L)*(rows.length-1));let r=rows[Math.max(0,Math.min(rows.length-1,i))];document.getElementById('tip').textContent=r?`${r[0]} | net ${fmt(r[1])} | short ${fmt(r[2])} | hedge ${fmt(r[3])}`:'No quotes'};
}
function render(){let t=data[+sel.value];let facts=document.getElementById('facts');facts.replaceChildren();for(let [label,value] of [['Published P&L','₹'+fmt(t.pnl)],['Credit → debit',fmt(t.credit)+' → '+fmt(t.debit)],['Units / expiry',t.units+' / '+t.expiry],['Missing minutes',t.missing]]){let d=document.createElement('div'),l=document.createElement('div'),v=document.createElement('div');l.className='muted';l.textContent=label;v.className='big';v.textContent=value;d.append(l,v);facts.append(d)}document.getElementById('entryText').textContent='Entry '+t.entry+' — '+t.entry_explanation;document.getElementById('exitText').textContent='Exit '+t.exit+' — '+t.exit_explanation;chart('price',t.path,[1],null,[[10,'#20835c'],[t.credit+45,'#bf514c']],t.exit.slice(0,16)+':00+05:30');chart('signal',t.signals,[1,2],[0,1],[[.2,'#8995a3'],[.8,'#8995a3']],t.entry_minute)}sel.value=data.length-1;sel.onchange=render;render();</script></html>'''.replace('PAYLOAD',encoded)
    (OUTPUT/'replay.html').write_text(html,encoding='utf-8')


if __name__=='__main__':
    build_report()
