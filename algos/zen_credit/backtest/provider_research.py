"""Reproduce provider trades and test causal signal hypotheses against actual events.

Run from zen_credit: python -B -u -m backtest.provider_research --download-only
All requests are read-only. Raw responses stay in the existing Dhan cache.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time, timedelta
import gc
import json
from pathlib import Path

import numpy as np
import pandas as pd

from backtest.dhan_history import DhanHistoryClient, chunks, option_payload, spot_payload
from config import REPO_ROOT
from backtest.provider_calendar import ProviderCalendar, expiries_for, lot_size
from backtest.dhan_replay import load_history, parse_series, atm_panels, supplement_fixed_contracts
from utils.time import IST

OUTPUT = REPO_ROOT / "reports" / "provider_research"
FEATURE_CACHE = REPO_ROOT / "data" / "dhan_cache" / "provider_atm_features.csv.gz"
BAR_CACHE = REPO_ROOT / "data" / "dhan_cache" / "provider_index_minutes.csv.gz"
ENTRY_QUOTE_CACHE = REPO_ROOT / "data" / "dhan_cache" / "provider_entry_quotes.csv.gz"


def provider_trades():
    raw = json.loads((REPO_ROOT / "data/reference/provider_trades.json").read_text(encoding="utf-8"))["data"]
    rows = []
    for record in raw:
        if len(record["trades"]) != 2:
            raise ValueError("Provider record is not a two-leg spread")
        short = next(t for t in record["trades"] if t["transactionType"] == "SELL")
        hedge = next(t for t in record["trades"] if t["transactionType"] == "BUY")
        entry = pd.Timestamp(record["createdAt"]).tz_convert(IST)
        exit_ts = pd.Timestamp(record["closedOn"]).tz_convert(IST)
        expiry = pd.Timestamp(short["expiry"]).tz_convert(IST).date()
        credit = short["entryPrice"] - hedge["entryPrice"]
        debit = short["avgExitPrice"] - hedge["avgExitPrice"]
        units = record["lotsBought"] * short["multiplier"]
        rows.append({"signal_id": record["signalId"], "entry": entry, "exit": exit_ts,
                     "entry_minute": entry.floor("min"), "exit_minute": exit_ts.floor("min"),
                     "option_type": short["optionType"], "direction": 1 if short["optionType"] == "PE" else -1,
                     "expiry": expiry, "short_strike": short["strikePrice"], "hedge_strike": hedge["strikePrice"],
                     "short_entry": short["entryPrice"], "hedge_entry": hedge["entryPrice"],
                     "short_exit": short["avgExitPrice"], "hedge_exit": hedge["avgExitPrice"],
                     "credit": credit, "debit": debit, "lots": record["lotsBought"],
                     "lot_size": short["multiplier"], "units": units, "margin_per_lot": record["marginRequired"],
                     "allocation_pct": record["capitalAllocated"], "pnl_reported": record["pnl"],
                     "pnl_calculated": (credit-debit)*units,
                     "pnl_reconciles": abs((credit-debit)*units-record["pnl"]) <= .02,
                     "summary_count": len(record.get("summary", [])),
                     "exit_recorded_after_expiry": exit_ts.date() > expiry,
                     "margin_return_pct": 100*(credit-debit)*short["multiplier"]/record["marginRequired"],
                     "exit_record_value": record["exits"][-1]["value"],
                     "gross_exit_premium": short["avgExitPrice"] + hedge["avgExitPrice"],
                     "short_security_id": short["exchangeToken"], "hedge_security_id": hedge["exchangeToken"]})
    result = pd.DataFrame(rows).sort_values("entry").reset_index(drop=True)
    result["split"] = [split_name(d) for d in result.entry.dt.date]
    return result


def split_name(day):
    if day <= date(2026, 2, 28):
        return "fit"
    if day <= date(2026, 6, 30):
        return "validation"
    if day <= date(2026, 8, 31):
        return "evaluation"
    return "case_study"


def audit_source_records():
    """Check the published labels independently of any fitted price signal."""
    trades=provider_trades().set_index('signal_id')
    raw=json.loads((REPO_ROOT/'data/reference/provider_trades.json').read_text())['data']
    rows=[];exit_fields=[]
    for record in raw:
        t=trades.loc[record['signalId']]
        short=next(x for x in record['trades'] if x['transactionType']=='SELL')
        hedge=next(x for x in record['trades'] if x['transactionType']=='BUY')
        last=record['exits'][-1]
        exit_fields.append({'signal_id':record['signalId'],'entry':t.entry,'exit':t.exit,
            'short_stop_loss':short.get('stopLoss'),'hedge_stop_loss':hedge.get('stopLoss'),
            'short_target_price':short.get('targetPrice'),'hedge_target_price':hedge.get('targetPrice'),
            'exit_summary_value':last['value'],'sum_leg_average_exit_prices':t.gross_exit_premium,
            'net_spread_average_exit_price':t.debit,'exit_summary_per_lot_pnl':last.get('pnl'),
            'total_reported_pnl':t.pnl_reported,'reported_lots':t.lots,
            'exit_summary_pnl_pct':last.get('pnlPercent'),
            'exit_value_matches_sum':abs(last['value']-t.gross_exit_premium)<=.02,
            'exit_value_matches_net':abs(last['value']-t.debit)<=.02})
        named=pd.to_datetime(record['name'].split(':',1)[-1],format='%d/%m/%Y %H:%M',errors='coerce')
        named=named.tz_localize(IST) if pd.notna(named) else pd.NaT
        rows.append({'signal_id':record['signalId'],'source_name':record['name'],
            'entry':t.entry,'exit':t.exit,'short_symbol':short['symbol'],'hedge_symbol':hedge['symbol'],
            'short_side':short['transactionType'],'hedge_side':hedge['transactionType'],
            'option_type':t.option_type,'short_strike':t.short_strike,'hedge_strike':t.hedge_strike,
            'expiry':t.expiry,'credit':t.credit,'debit':t.debit,'units':t.units,
            'pnl_reported':t.pnl_reported,'pnl_calculated':t.pnl_calculated,
            'raw_entry_timestamp_matches':pd.Timestamp(record['createdAt']).tz_convert(IST)==t.entry,
            'raw_exit_timestamp_matches':pd.Timestamp(record['closedOn']).tz_convert(IST)==t.exit,
            'name_minute_matches':named==t.entry_minute,
            'same_side_and_expiry':short['optionType']==hedge['optionType'] and short['expiry']==hedge['expiry'],
            'symbols_match_strike_and_type':all(x['symbol'].endswith(str(int(x['strikePrice']))+x['optionType']) for x in (short,hedge)),
            'same_multiplier':short['multiplier']==hedge['multiplier'],
            'credit_spread_order':t.credit>0 and (t.hedge_strike>t.short_strike if t.option_type=='CE' else t.hedge_strike<t.short_strike),
            'width_400':abs(t.hedge_strike-t.short_strike)==400,
            'pnl_reconciles':t.pnl_reconciles,'recorded_after_expiry':t.exit_recorded_after_expiry,
            'summary_count':t.summary_count})
    frame=pd.DataFrame(rows).sort_values('entry')
    frame['overlap_previous_record_minutes']=frame.entry.dt.floor('min')<frame.exit.dt.floor('min').cummax().shift()
    frame['same_minute_as_previous_exit']=frame.entry.dt.floor('min')==frame.exit.dt.floor('min').shift()
    checks=('raw_entry_timestamp_matches','raw_exit_timestamp_matches','name_minute_matches',
        'same_side_and_expiry','symbols_match_strike_and_type','same_multiplier','credit_spread_order','width_400')
    summary={'trades':len(frame),'metadata_checks_pass':{c:int(frame[c].sum()) for c in checks},
        'pnl_reconciles':int(frame.pnl_reconciles.sum()),'recorded_after_expiry':int(frame.recorded_after_expiry.sum()),
        'overlapping_records_by_minute':int(frame.overlap_previous_record_minutes.sum()),
        'same_minute_reentries':int(frame.same_minute_as_previous_exit.sum()),
        'limitation':'This validates parsing of published metadata, not broker execution timestamps, original alpha values, RMS reasons or missing intraminute prices. After-expiry record times may be processing times; no source timestamp is changed.'}
    constraints=[];active=[];maximum_active=0;prior=None
    for t in frame.itertuples():
        active=[p for p in active if p.exit>t.entry]
        for p in active:
            constraints.append({'kind':'overlapping_published_positions','prior_signal':p.signal_id,
                'prior_entry':p.entry,'prior_exit':p.exit,'new_signal':t.signal_id,'new_entry':t.entry,
                'overlap_seconds':(p.exit-t.entry).total_seconds(),
                'interpretation':'One-position model cannot hold both source intervals. Public timestamps do not establish actual broker state.'})
        if prior is not None and prior.exit.floor('min')==t.entry.floor('min') and prior.exit<=t.entry:
            constraints.append({'kind':'exit_then_entry_within_one_minute','prior_signal':prior.signal_id,
                'prior_entry':prior.entry,'prior_exit':prior.exit,'new_signal':t.signal_id,'new_entry':t.entry,
                'overlap_seconds':(prior.exit-t.entry).total_seconds(),
                'interpretation':'One evaluation per minute cannot match both this exit and entry while prohibiting reentry on an exit evaluation.'})
        active.append(t);maximum_active=max(maximum_active,len(active));prior=t
    summary['maximum_simultaneous_published_positions']=maximum_active
    summary['position_state_constraints']={kind:sum(c['kind']==kind for c in constraints) for kind in
        ('overlapping_published_positions','exit_then_entry_within_one_minute')}
    public_exits=pd.DataFrame(exit_fields).sort_values('entry')
    summary['public_exit_fields']={
        'legs_with_zero_stop_loss':int(public_exits[['short_stop_loss','hedge_stop_loss']].eq(0).sum().sum()),
        'legs_with_zero_target_price':int(public_exits[['short_target_price','hedge_target_price']].eq(0).sum().sum()),
        'exit_value_matches_sum_of_average_leg_prices':int(public_exits.exit_value_matches_sum.sum()),
        'exit_value_matches_net_spread_price':int(public_exits.exit_value_matches_net.sum()),
        'interpretation':'Zero public leg thresholds do not establish absence of internal spread stops. Exit summary value generally equals the sum of average leg exit prices, not a disclosed net-spread target. Reported P&L and final prices are labels, never exit predictors.'}
    OUTPUT.mkdir(exist_ok=True)
    frame.to_csv(OUTPUT/'source_record_audit.csv',index=False)
    pd.DataFrame(constraints).to_csv(OUTPUT/'position_state_constraints.csv',index=False)
    public_exits.to_csv(OUTPUT/'public_exit_field_audit.csv',index=False)
    (OUTPUT/'source_record_audit.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2),flush=True)


SOURCE_CANDLE_FIELDS = ['open', 'high', 'low', 'close', 'volume', 'strike', 'spot', 'iv', 'oi']


def source_candle_offset(strike, atm, code):
    """Return an exact supported rolling offset, never nearest-strike rounding."""
    if code not in (1, 2):return None, 'expiry_not_near_or_next'
    if not np.isfinite(atm) or atm <= 0:return None, 'atm_strike_unknown'
    offset = (float(strike)-float(atm))/50
    if not np.isfinite(offset) or offset != int(offset):return None, 'strike_not_on_atm_grid'
    offset = int(offset)
    if abs(offset) > (10 if code == 1 else 3):return None, 'outside_supported_offset'
    return offset, None


def source_candle_extract(frame, minute, strike, fill):
    """Inspect an exact contract candle; its range is a diagnostic label only."""
    if minute not in frame.index:return {'status': 'candle_unavailable'}
    rows = frame.loc[[minute]]
    if 'strike' not in rows:return {'status': 'returned_strike_unknown'}
    rows = rows.loc[pd.to_numeric(rows.strike, errors='coerce').eq(float(strike))]
    if rows.empty:return {'status': 'returned_strike_mismatch'}
    if len(rows) != 1:return {'status': 'duplicate_exact_candle'}
    row = rows.iloc[0]; result = {'status': 'available'}
    for field in SOURCE_CANDLE_FIELDS:
        value = row.get(field, np.nan)
        result[field] = float(value) if pd.notna(value) else np.nan
    low, high = result['low'], result['high']
    if np.isfinite(low) and np.isfinite(high) and 0 <= low <= high:
        result['fill_range_flag'] = 'inside_range' if low <= fill <= high else 'outside_range'
        result['fill_distance_outside'] = max(low-fill, fill-high, 0.)
    else:result['fill_range_flag'] = 'range_unknown'
    return result


def source_candles(limit=0, client=None, offline_client=None):
    """Targeted source-leg OHLC audit; one small contract/day response at a time.

    Raw API cache resumes downloads. CSV rows checkpoint completed leg events;
    only historical charts are requested, with no execution or signal changes.
    """
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
        raise ValueError('Source-candle limit must be a nonnegative integer')
    client = client or DhanHistoryClient(); offline_client = offline_client or DhanHistoryClient(offline=True)
    calendar = ProviderCalendar(); trades = provider_trades()
    target = OUTPUT/'source_leg_candles.csv'; coverage = OUTPUT/'source_leg_candles_coverage.json'
    OUTPUT.mkdir(exist_ok=True)
    saved = pd.read_csv(target).to_dict('records') if target.exists() else []
    records = {(r['signal_id'], r['event'], r['leg']):r for r in saved}
    completed = {key for key, r in records.items()
        if r.get('event_status') not in ('request_failed', 'pending')
        and r.get('prior_status') not in ('request_failed', 'pending')}
    count = 0; memo = {}; block_cache = {}
    def fetch(payload):
        key = json.dumps(payload, sort_keys=True)
        if key not in memo:
            data = client.request('rollingoption', payload)
            side = 'ce' if payload['drvOptionType'] == 'CALL' else 'pe'
            memo[key] = parse_series(data['data'].get(side), date.fromisoformat(payload['fromDate']),
                date.fromisoformat(payload['toDate']), calendar)
            # At most the current event day's bounded response set remains live.
        return memo[key]
    def inspect(minute, expiry, strike, fill, side):
        day = minute.date()
        if day > expiry:return {'status': 'after_expiry'}
        if not calendar.is_trading_day(day):return {'status': 'nontrading_day'}
        if not time(9, 15) <= minute.time() < time(15, 30):return {'status': 'outside_session'}
        listed = expiries_for(day)
        if expiry not in listed:return {'status': 'expiry_not_near_or_next'}
        code = listed.index(expiry)+1; label = 'ce' if side == 'CALL' else 'pe'
        atm_frame = None
        for first, last in history_blocks():
            if first <= day < last:
                block_key = (first, last, code, side)
                if block_key not in block_cache:
                    payload = option_payload(first, last, code, 0, side)
                    payload['requiredData'] = SOURCE_CANDLE_FIELDS.copy()
                    try:
                        raw = offline_client.request('rollingoption', payload)
                        block_cache[block_key] = parse_series(raw['data'].get(label), first, last, calendar)
                    except RuntimeError as exc:
                        if not str(exc).startswith('Missing offline cache:'):raise
                        block_cache[block_key] = pd.DataFrame()
                    if len(block_cache) > 4:
                        old_key = next(iter(block_cache))
                        if old_key != block_key:block_cache.pop(old_key)
                atm_frame = block_cache[block_key]
                break
        if atm_frame is None or minute not in atm_frame.index or 'strike' not in atm_frame:
            payload = option_payload(day, day+timedelta(days=1), code, 0, side)
            payload['requiredData'] = SOURCE_CANDLE_FIELDS.copy(); atm_frame = fetch(payload)
        if minute not in atm_frame.index:return {'status': 'atm_candle_unavailable', 'expiry_code': code}
        atm_rows = atm_frame.loc[[minute]]
        if len(atm_rows) != 1:return {'status': 'duplicate_atm_candle', 'expiry_code': code}
        atm = float(atm_rows.iloc[0].get('strike', np.nan)); offset, error = source_candle_offset(strike, atm, code)
        meta = {'expiry_code': code, 'atm_strike': atm, 'offset': offset}
        if error:return {**meta, 'status': error}
        if offset == 0:frame = atm_frame
        else:
            payload = option_payload(day, day+timedelta(days=1), code, offset, side)
            payload['requiredData'] = SOURCE_CANDLE_FIELDS.copy(); frame = fetch(payload)
        return {**meta, **source_candle_extract(frame, minute, strike, fill)}
    def checkpoint():
        frame = pd.DataFrame(list(records.values()))
        temporary = target.with_suffix('.tmp'); frame.to_csv(temporary, index=False); temporary.replace(target)
        report = {'audit_version': 1, 'expected_leg_events': len(trades)*4,
            'processed_leg_events': len(frame), 'completed_this_run': count,
            'cached_requests_this_run': client.cached+offline_client.cached,
            'downloaded_requests_this_run': client.downloaded,
            'event_status_counts': frame.event_status.value_counts().to_dict(),
            'prior_status_counts': frame.prior_status.value_counts().to_dict(),
            'event_fill_range_counts': frame.get('event_fill_range_flag', pd.Series(dtype=str)).value_counts().to_dict(),
            'prior_fill_range_counts': frame.get('prior_fill_range_flag', pd.Series(dtype=str)).value_counts().to_dict(),
            'scope': 'Both source spread legs at entry and exit; exact expiry and strike verified. Preceding candle is previous elapsed minute, not a filled prior session quote.',
            'causality': 'Event candle completes after source timestamp and is diagnostic only. Previous candle is completed at event minute. Published timestamps/fills are labels, never predictors; no source fill altered.',
            'limits': 'OHLC range does not establish execution at source second or synchronized spread fills. Unsupported offsets, after-expiry timestamps, missing candles and failed requests remain separate. Existing ATM-only unavailable counts do not prove these non-ATM candles unavailable from Dhan.'}
        temporary = coverage.with_suffix('.tmp'); temporary.write_text(json.dumps(report, indent=2)); temporary.replace(coverage)
        return report
    for trade in trades.itertuples():
        for event in ('entry', 'exit'):
            timestamp = getattr(trade, event); minute = timestamp.floor('min'); memo.clear()
            for leg in ('short', 'hedge'):
                key = (trade.signal_id, event, leg)
                if key in completed:continue
                if limit and count >= limit:
                    print(json.dumps(checkpoint(), indent=2), flush=True); return
                strike = getattr(trade, leg+'_strike'); fill = getattr(trade, leg+'_'+event)
                row = {'signal_id': trade.signal_id, 'event': event, 'leg': leg,
                    'timestamp': timestamp, 'event_candle': minute, 'prior_candle': minute-pd.Timedelta(minutes=1),
                    'expiry': trade.expiry, 'option_type': trade.option_type, 'strike': strike, 'source_fill': fill}
                if count % 10 == 0:
                    records[key] = {**row, 'event_status': 'pending', 'prior_status': 'pending'}
                    checkpoint()
                for prefix, candle_minute in (('event', minute), ('prior', minute-pd.Timedelta(minutes=1))):
                    try:
                        detail = inspect(candle_minute, trade.expiry, strike, fill,
                            'CALL' if trade.option_type == 'CE' else 'PUT')
                    except (RuntimeError, ValueError) as exc:
                        detail = {'status': 'request_failed', 'error': str(exc)}
                    row.update({prefix+'_'+k:v for k,v in detail.items()})
                records[key] = row; count += 1
                if count % 10 == 0:
                    checkpoint(); print(f'Source-leg candles: {len(records)}/{len(trades)*4}; downloaded={client.downloaded}', flush=True)
                if any(row.get(p+'_error', '').endswith('HTTP 401') for p in ('event', 'prior')):
                    checkpoint(); raise RuntimeError('Historical authorization failed; audit checkpoint preserved')
    print(json.dumps(checkpoint(), indent=2), flush=True)


def source_joint_fill_scan(frames, clock, trade, event, relation):
    """Joint exact-contract fill feasibility; all scanned candles are labels."""
    timestamp = getattr(trade, event)
    merged = pd.concat(frames).sort_index() if frames else pd.DataFrame()
    legs = {leg: merged.loc[pd.to_numeric(merged['strike'], errors='coerce').eq(getattr(trade, leg+'_strike'))]
        if 'strike' in merged else pd.DataFrame() for leg in ('short', 'hedge')}
    rows = []
    for minute in clock:
        row = {'signal_id': trade.signal_id, 'event': event, 'source_timestamp': timestamp,
            'expiry': trade.expiry, 'option_type': trade.option_type, 'day_relation': relation,
            'candle_start': minute, 'candle_end': minute+pd.Timedelta(minutes=1),
            'distance_seconds_from_source': (minute-timestamp).total_seconds()}
        matches = []
        for leg in ('short', 'hedge'):
            strike = getattr(trade, leg+'_strike'); fill = getattr(trade, leg+'_'+event)
            detail = source_candle_extract(legs[leg], minute, strike, fill)
            row[leg+'_source_strike'] = strike; row[leg+'_source_fill'] = fill
            row.update({leg+'_'+key:value for key,value in detail.items()})
            matches.append(detail.get('fill_range_flag') == 'inside_range')
        row['both_exact_known'] = all(row[leg+'_status'] == 'available' for leg in ('short', 'hedge'))
        row['joint_fill_range_match'] = all(matches)
        rows.append(row)
    return rows


def source_fill_timing(client=None):
    """Scan only the six anomalous source events, without changing timestamps."""
    client = client or DhanHistoryClient(); calendar = ProviderCalendar()
    audit = pd.read_csv(OUTPUT/'source_leg_candles.csv')
    events = audit.loc[audit.event_fill_range_flag.eq('outside_range'), ['signal_id', 'event']].drop_duplicates()
    if len(events) > 8:raise ValueError('Bounded timing audit supports at most8 anomalous events')
    trades = provider_trades().set_index('signal_id')
    destination = OUTPUT/'source_fill_timing.csv'; report_path = OUTPUT/'source_fill_timing.json'
    previous = json.loads(report_path.read_text()) if report_path.exists() else {}
    completed = set(previous.get('completed_day_keys', [])); day_reports = previous.get('day_reports', [])
    rows = pd.read_csv(destination).to_dict('records') if destination.exists() else []
    def checkpoint(active=None):
        frame = pd.DataFrame(rows)
        if not frame.empty:
            temporary = destination.with_suffix('.tmp'); frame.to_csv(temporary, index=False); temporary.replace(destination)
        matches = frame.loc[frame.joint_fill_range_match.eq(True)] if not frame.empty else frame
        summary = {'audit_version':1, 'anomalous_events': len(events), 'expected_day_scans':len(events)*2,
            'completed_day_keys':sorted(completed), 'completed_day_scans':len(completed),
            'active_day':active, 'day_reports':day_reports, 'scanned_candles':len(frame),
            'joint_fill_range_matches':len(matches), 'downloaded_this_run':client.downloaded,
            'cache_hits_this_run':client.cached,
            'scope':'Only events with outside-event OHLC fills. Same expiry and BOTH source strikes; event day and previous trading day. Supported near±10/next±3 offsets only; exact returned strikes verified.',
            'causality':'All full-candle ranges are diagnostic labels, including candles after the event. No timestamp/fill changes and no new predictors or source-conditioned execution rules.',
            'limits':'Joint ranges only show both prices traded within the same minute separately, not synchronized fills, actual broker timing, liquidation causes or stale-price proof.'}
        temporary = report_path.with_suffix('.tmp'); temporary.write_text(json.dumps(summary, indent=2)); temporary.replace(report_path)
        return summary
    for event_row in events.itertuples():
        trade = trades.loc[event_row.signal_id].copy(); trade['signal_id'] = event_row.signal_id
        timestamp = trade[event_row.event]
        # Series attributes preserve the existing source-entry/exit field names.
        previous_day = timestamp.date()-timedelta(days=1)
        while not calendar.is_trading_day(previous_day):previous_day -= timedelta(days=1)
        for day, relation in ((timestamp.date(), 'event_day'), (previous_day, 'previous_trading_day')):
            key = f'{event_row.signal_id}|{event_row.event}|{day}'
            if key in completed:continue
            checkpoint(key)
            listed = expiries_for(day)
            if trade.expiry not in listed:
                day_reports.append({'day_key':key,'status':'expiry_not_near_or_next','candles':0})
                completed.add(key);checkpoint();continue
            code = listed.index(trade.expiry)+1; side = 'CALL' if trade.option_type=='CE' else 'PUT'
            label = 'ce' if side=='CALL' else 'pe'
            def fetch(offset):
                payload = option_payload(day, day+timedelta(days=1), code, offset, side)
                payload['requiredData'] = SOURCE_CANDLE_FIELDS.copy()
                response = client.request('rollingoption', payload)
                return parse_series(response['data'].get(label), day, day+timedelta(days=1), calendar)
            atm = fetch(0); offsets = set()
            if 'strike' in atm:
                for strike in (trade.short_strike, trade.hedge_strike):
                    for reference in atm.strike.unique():
                        offset, error = source_candle_offset(strike, reference, code)
                        if error is None:offsets.add(offset)
            frames = []
            for offset in sorted(offsets):
                frame = atm if offset==0 else fetch(offset)
                if 'strike' in frame:
                    frame = frame.loc[pd.to_numeric(frame.strike,errors='coerce').isin((trade.short_strike,trade.hedge_strike))]
                    if not frame.empty:frames.append(frame)
            # Every underlying clock row is retained, even if one fixed leg is unavailable.
            scan = source_joint_fill_scan(frames, atm.index.unique(), trade, event_row.event, relation)
            rows.extend(scan)
            joint = [r for r in scan if r['joint_fill_range_match']]
            day_reports.append({'day_key':key,'status':'scanned' if len(atm) else 'atm_day_empty',
                'expiry_code':code,'requested_offsets':sorted(offsets),'candles':len(scan),
                'both_exact_known':sum(r['both_exact_known'] for r in scan), 'joint_matches':len(joint),
                'joint_match_starts':[str(r['candle_start']) for r in joint]})
            completed.add(key);checkpoint()
            print(f'Source fill timing: {len(completed)}/{len(events)*2} day scans; joint matches={len(joint)}; downloaded={client.downloaded}',flush=True)
    print(json.dumps(checkpoint(), indent=2),flush=True)


def prepare_features():
    """Process one raw chunk at a time to keep peak memory bounded."""
    client = DhanHistoryClient(offline=True)
    calendar = ProviderCalendar()
    all_bars, all_panels, quality = [], [], []
    previous_quotes = None
    previous_minute = None
    for first, last in history_blocks():
        # Full strike coverage matters for the previous close of today's ATM
        # contract after an overnight gap. A shallow ATM +/-1 panel loses it.
        bars, quotes, conflicts = load_history(client, first, last, calendar=calendar,
            expiry_resolver=expiries_for)
        quotes, fixed = supplement_fixed_contracts(client, bars, quotes, last, calendar, expiries_for, lot_size)
        quote_history = pd.concat([previous_quotes, quotes]) if previous_quotes is not None else quotes
        minutes = bars.index + pd.Timedelta(minutes=1)
        previous_times = pd.Series([previous_minute] + list(minutes[:-1]), index=minutes)
        extras = []
        for code in (1, 2):
            for side, label in (("CALL", "ce"), ("PUT", "pe")):
                payload = option_payload(first, last, code, 0, side)
                payload["requiredData"] = ["open", "high", "low", "close", "volume", "strike", "spot", "iv", "oi"]
                data = client.request("rollingoption", payload)
                extra = parse_series(data["data"].get(label), first, last, calendar)
                if extra.empty:
                    continue
                extra["minute"] = extra.index + pd.Timedelta(minutes=1)
                mapping = {d: expiries_for(d)[code-1] for d in set(extra.index.date)}
                extra["expiry"] = [mapping[d] for d in extra.index.date]
                for field in ("iv", "oi", "open", "high", "low", "spot"):
                    if field not in extra:
                        extra[field] = np.nan
                cols = ["iv", "oi", "open", "high", "low", "spot"]
                extra = extra.set_index(["minute", "expiry", "strike"])[cols]
                extra.columns = [f"{label}_{c}" for c in cols]
                extras.append(extra)
        extra_wide = pd.concat(extras, axis=1) if extras else pd.DataFrame()
        # Each side/expiry-code has disjoint contract keys, but concat creates
        # repeated field names. Coalesce only equal-named columns across codes.
        if extra_wide.columns.duplicated().any():
            extra_wide = extra_wide.T.groupby(level=0).first().T
        for expiry, panel in atm_panels(quotes, bars).items():
            panel["expiry"] = expiry
            panel.index.name = "minute"
            keys = pd.MultiIndex.from_arrays([panel.index, panel.expiry, panel.atm_strike], names=quotes.index.names)
            current = quotes.reindex(keys)
            previous_keys = pd.MultiIndex.from_arrays(
                [previous_times.reindex(panel.index), panel.expiry, panel.atm_strike], names=quotes.index.names)
            previous = quote_history.reindex(previous_keys)
            for side in ("ce", "pe"):
                panel[f"{side}_ltp"] = current[f"{side}_ltp"].to_numpy()
                panel[f"{side}_native_volume"] = current[f"{side}_volume"].to_numpy()
                old = previous[f"{side}_ltp"].to_numpy()
                now = current[f"{side}_ltp"].to_numpy()
                valid = np.isfinite(old) & (old > 0) & (now > 0)
                prior_times = pd.DatetimeIndex(previous_times.reindex(panel.index))
                adjacent = (panel.index-prior_times) == pd.Timedelta(minutes=1)
                overnight = (panel.index.date != prior_times.date) & (panel.index.hour == 9) & (panel.index.minute == 16)
                valid &= adjacent | overnight
                panel[f"{side}_return_with_overnight"] = np.divide(
                    now, old, out=np.full(len(old), np.nan), where=valid) - 1
            if not extra_wide.empty:
                fields = extra_wide.reindex(keys)
                for field in fields.columns:
                    panel[field] = fields[field].to_numpy()
            all_panels.append(panel.reset_index())
        all_bars.append(bars)
        previous_minute = minutes[-1]
        previous_quotes = quotes.loc[quotes.index.get_level_values("minute") == previous_minute].copy()
        quality.append({"start": str(first), "end_exclusive": str(last), "index_minutes": len(bars),
                        "conflicting_records": len(conflicts), "fixed_data": fixed})
        del quotes, extras, extra_wide, quote_history
        gc.collect()
    bars = pd.concat(all_bars).sort_index()
    panels = pd.concat(all_panels, ignore_index=True).sort_values(["expiry", "minute"])
    if bars.index.duplicated().any() or panels.duplicated(["minute", "expiry"]).any():
        raise ValueError("Duplicate chunk-boundary observations")
    bars.to_csv(BAR_CACHE, compression="gzip")
    panels.to_csv(FEATURE_CACHE, index=False, compression="gzip")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "feature_coverage.json").write_text(json.dumps(quality, indent=2, default=str), encoding="utf-8")
    provider_trades().to_csv(OUTPUT / "actual_trades.csv", index=False)
    print(f"Prepared {len(bars):,} index bars and {len(panels):,} expiry-specific ATM observations", flush=True)


def replay_actual_trades():
    """Mark original fixed contracts; never roll a held strike with the ATM series."""
    client, calendar = DhanHistoryClient(offline=True), ProviderCalendar()
    trades = provider_trades()
    collected = []
    for first, last in history_blocks():
        active = trades[(trades.entry.dt.date < last) & (trades.exit.dt.date >= first)]
        if active.empty:
            continue
        bars, quotes, _ = load_history(client, first, last, calendar=calendar, expiry_resolver=expiries_for)
        quotes, _ = supplement_fixed_contracts(client, bars, quotes, last, calendar, expiries_for, lot_size)
        minutes = bars.index + pd.Timedelta(minutes=1)
        for t in active.itertuples():
            times = minutes[(minutes >= t.entry_minute) & (minutes <= t.exit_minute+pd.Timedelta(minutes=2)) & (minutes.date <= t.expiry)]
            legs=[]
            for strike in (t.short_strike,t.hedge_strike):
                keys=pd.MultiIndex.from_arrays([times,[t.expiry]*len(times),[strike]*len(times)],names=quotes.index.names)
                legs.append(quotes.reindex(keys)[f'{t.option_type.lower()}_ltp'].to_numpy())
            path=pd.DataFrame({'signal_id':t.signal_id,'minute':times,'short':legs[0],'hedge':legs[1]})
            path['net']=path.short-path.hedge
            path['gross']=path.short+path.hedge
            path['spot']=bars.close.reindex(times-pd.Timedelta(minutes=1)).to_numpy()
            path['pnl_from_reported_entry']=(t.credit-path.net)*t.units
            path['known_at_reported_exit']=path.minute<=t.exit_minute
            collected.append(path)
        del quotes
        gc.collect()
    paths=pd.concat(collected,ignore_index=True).sort_values(['signal_id','minute'])
    if paths.duplicated(['signal_id','minute']).any():
        raise ValueError('Duplicate replay minutes')
    paths.to_csv(OUTPUT/'actual_contract_paths.csv.gz',index=False,compression='gzip')
    details, candidates=[] , []
    for t in trades.itertuples():
        path=paths[paths.signal_id.eq(t.signal_id)]
        observed=path[(path.minute>t.entry_minute)&(path.minute<=t.exit_minute)]
        # Later completed candles are only an explicit +/-2-minute timing
        # diagnostic; they are never treated as information known at exit.
        probe=path[path.minute>t.entry_minute]
        complete=bool(len(observed) and observed.net.notna().all() and observed.minute.max()==t.exit_minute and not t.exit_recorded_after_expiry)
        context={'signal_id':t.signal_id,'path_minutes':len(observed),'missing_spread_minutes':int(observed.net.isna().sum()),
                 'complete_to_exit':complete,'observed_min_net':observed.net.min(),'observed_max_net':observed.net.max(),
                 'minimum_observed_pnl':observed.pnl_from_reported_entry.min(),'maximum_observed_pnl':observed.pnl_from_reported_entry.max()}
        day=min(calendar.next_trading_day(t.entry.date()),t.expiry) if t.entry.date()<t.expiry else t.expiry
        for target in (5.,10.,15.):
            for stop_label in ('40','45','50','five_pct_normal_margin'):
                stop=(.05*t.margin_per_lot/t.lot_size/(1.54 if t.entry.date()==t.expiry else 1)) if stop_label=='five_pct_normal_margin' else float(stop_label)
                for schedule in ('14:53','15:00','dated'):
                    clock=('15:00' if t.entry.date()<date(2026,7,1) else '14:53') if schedule=='dated' else schedule
                    due=pd.Timestamp(f'{day} {clock}',tz=IST)
                    sl=probe.net>=t.credit+stop
                    tp=probe.net<=target
                    timed=probe.minute>=due
                    hit=probe[sl|tp|timed]
                    first_hit=hit.iloc[0] if len(hit) else None
                    first=first_hit.minute if first_hit is not None else pd.NaT
                    delta=(first-t.exit_minute).total_seconds()/60 if pd.notna(first) else np.nan
                    reason=('stop' if first_hit.net>=t.credit+stop else 'target' if first_hit.net<=target else 'time') if first_hit is not None else 'not_observed'
                    candidates.append({'signal_id':t.signal_id,'split':t.split,'target':target,'stop_rule':stop_label,'stop_points':stop,'schedule':schedule,
                        'first_hit':first,'minutes_before_actual_exit':-delta,'within_two_minutes':bool(pd.notna(first) and abs(delta)<=2),
                        'reason':reason,'complete_to_exit':complete,'source_pnl_reconciles':t.pnl_reconciles})
                    if (target,stop_label,schedule)==(10.,'45','dated'):
                        context.update({'baseline_first_exit':first,'baseline_exit_reason':reason,'baseline_minutes_before_exit':-delta})
        for name,condition in {'net10':observed.net<=10,'gross15':observed.gross<=15,
             'profit10pct_margin':(t.credit-observed.net)*t.lot_size>=.1*t.margin_per_lot}.items():
            hits=observed[condition]
            context[f'{name}_first_hit']=hits.minute.iloc[0] if len(hits) else pd.NaT
        details.append(context)
    pd.DataFrame(details).to_csv(OUTPUT/'exit_diagnostics.csv',index=False)
    comparisons=pd.DataFrame(candidates)
    comparisons.to_csv(OUTPUT/'exit_candidates_per_trade.csv',index=False)
    valid=comparisons[comparisons.complete_to_exit & comparisons.source_pnl_reconciles]
    valid.groupby(['target','stop_rule','schedule','split']).agg(trades=('signal_id','size'),matches_within_two_minutes=('within_two_minutes','sum')).reset_index().to_csv(OUTPUT/'exit_candidate_summary.csv',index=False)
    print(f'Replayed {len(trades)} actual trades; {sum(d["complete_to_exit"] for d in details)} complete paths',flush=True)


def prepare_entry_quotes():
    """Quotes for the ATM strike chosen from the last completed index bar's open."""
    client,calendar=DhanHistoryClient(offline=True),ProviderCalendar()
    frames=[]
    for first,last in history_blocks():
        bars,quotes,_=load_history(client,first,last,calendar=calendar,expiry_resolver=expiries_for)
        quotes,_=supplement_fixed_contracts(client,bars,quotes,last,calendar,expiries_for,lot_size)
        minutes=bars.index+pd.Timedelta(minutes=1)
        mapping={d:expiries_for(d)[0] for d in set(bars.index.date)}
        expiry=[mapping[d] for d in bars.index.date]
        strike=np.floor((bars.open.to_numpy()+25-1e-8)/50)*50
        keys=pd.MultiIndex.from_arrays([minutes,expiry,strike],names=quotes.index.names)
        selected=quotes.reindex(keys)
        frame=pd.DataFrame({'minute':minutes,'expiry':expiry,'strike':strike,
                            'reference_open':bars.open.to_numpy(),
                            'ce_ltp':selected.ce_ltp.to_numpy(),'pe_ltp':selected.pe_ltp.to_numpy()})
        frames.append(frame)
        del quotes
        gc.collect()
    pd.concat(frames,ignore_index=True).to_csv(ENTRY_QUOTE_CACHE,index=False,compression='gzip')
    print('Prepared opening-price strike quotes for every decision minute',flush=True)


def history_blocks():
    # Reuse the already verified September cache boundaries exactly.
    return (list(chunks(date(2025, 6, 18), date(2026, 8, 17)))
            + [(date(2026, 8, 17), date(2026, 9, 7)), (date(2026, 9, 7), date(2026, 10, 2))])


def research_jobs():
    features, wings, extras = [], [], []
    for first, last in history_blocks():
        features.append(("intraday", spot_payload(first, last)))
        for code, offsets in ((1, range(-10, 11)), (2, range(-3, 4))):
            for offset in offsets:
                for side in ("CALL", "PUT"):
                    job = ("rollingoption", option_payload(first, last, code, offset, side))
                    (features if abs(offset) <= 1 else wings).append(job)
        for code in (1, 2):
            for side in ("CALL", "PUT"):
                p = option_payload(first, last, code, 0, side)
                p["requiredData"] = ["open", "high", "low", "close", "volume", "strike", "spot", "iv", "oi"]
                extras.append(("rollingoption", p))
    return [("features", features), ("extra_features", extras), ("held_strikes", wings)]


def download_research(workers=12):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    errors = []
    def fetch(job):
        client = DhanHistoryClient()
        client.request(*job)
        return client.cached, client.downloaded
    for stage, jobs in research_jobs():
        print(f"Downloading {stage}: {len(jobs)} requests", flush=True)
        hits = downloaded = 0
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(fetch, job): job for job in jobs}
            for i, future in enumerate(as_completed(futures), 1):
                try:
                    h, n = future.result()
                    hits += h
                    downloaded += n
                except Exception as exc:
                    endpoint, payload = futures[future]
                    errors.append({"stage": stage, "endpoint": endpoint, "request": payload,
                                   "error": str(exc)})
                if i % 20 == 0 or i == len(jobs):
                    print(f"  {stage}: {i}/{len(jobs)}; cached={hits}; downloaded={downloaded}; errors={len(errors)}", flush=True)
                    (OUTPUT / "download_status.json").write_text(json.dumps(
                        {"stage": stage, "completed": i, "total": len(jobs), "errors": errors}, indent=2), encoding="utf-8")
    if errors:
        raise RuntimeError(f"{len(errors)} historical requests failed; see download_status.json and rerun to resume")


def held_quote_range_audit():
    """Classify all held-quote gaps using actual cached ATM strikes, never spot rounding."""
    run=OUTPUT/'replication_trials'/'weighted_rank_pairs'/'full_autonomous_5346fa75f4d90520_ledger'
    target=OUTPUT/'replication_trials'/'held_quote_limits';target.mkdir(exist_ok=True)
    client=DhanHistoryClient(offline=True);calendar=ProviderCalendar();records=[]
    blocks={str(first):(first,last) for first,last in history_blocks()}
    for path in sorted(run.glob('missing_quotes_*.csv.gz')):
        try:gaps=pd.read_csv(path)
        except pd.errors.EmptyDataError:continue
        if gaps.empty:continue
        stamp=path.name.removeprefix('missing_quotes_').removesuffix('.csv.gz');first,last=blocks[stamp]
        atm={}
        for code in (1,2):
            for side,label in (('CALL','ce'),('PUT','pe')):
                payload=option_payload(first,last,code,0,side)
                raw=client.request('rollingoption',payload)
                frame=parse_series(raw['data'].get(label),first,last,calendar)
                atm[(code,label)]=frame['strike'] if 'strike' in frame else pd.Series(dtype=float)
        for g in gaps.itertuples():
            minute=pd.Timestamp(g.minute);expiry=pd.Timestamp(g.expiry).date();label=g.option_type.lower()
            listed=expiries_for(minute.date());code=listed.index(expiry)+1 if expiry in listed else None
            row={'minute':minute,'entry_ts':g.entry_ts,'expiry':expiry,'option_type':g.option_type,
                 'sell_strike':g.sell_strike,'buy_strike':g.buy_strike,'expiry_code':code,'candle_start':minute-pd.Timedelta(minutes=1)}
            statuses=[]
            for leg,strike in (('short',g.sell_strike),('hedge',g.buy_strike)):
                value=atm[(code,label)].get(minute-pd.Timedelta(minutes=1),np.nan) if code else np.nan
                offset=(float(strike)-value)/50 if np.isfinite(value) else np.nan
                if minute.date()>expiry:status='after_expiry'
                elif code is None:status='expiry_not_near_or_next'
                else:
                    _,error=source_candle_offset(strike,value,code)
                    status=error or 'within_documented_range'
                row.update({leg+'_atm_strike':value,leg+'_required_offset':offset,leg+'_range_status':status})
                statuses.append(status)
            if 'outside_supported_offset' in statuses:row['gap_range_class']='at_least_one_leg_outside_supported_range'
            elif all(s=='within_documented_range' for s in statuses):row['gap_range_class']='both_legs_within_documented_range'
            else:row['gap_range_class']=';'.join(sorted(set(statuses)))
            records.append(row)
        print(f'Held quote range audit {stamp}: {len(gaps)} gap minutes',flush=True)
    frame=pd.DataFrame(records);expected=json.loads((run/'report.json').read_text())['result']['missing_held_quote_minutes']
    if len(frame)!=expected:raise ValueError('Held quote audit does not cover all committed gap minutes')
    frame.to_csv(target/'held_gap_ranges.csv',index=False)
    grouped=frame.groupby(['entry_ts','expiry','sell_strike','buy_strike','option_type','gap_range_class']).size().rename('gap_minutes').reset_index()
    grouped.to_csv(target/'held_gap_ranges_by_trade.csv',index=False)
    recent=frame[pd.to_datetime(frame.minute,utc=True).dt.tz_convert(IST).dt.strftime('%Y-%m-%d').eq('2026-09-29')]
    recent.to_csv(target/'september29_gap_ranges.csv',index=False)
    result={'candidate_id':'5346fa75f4d90520','expected_gap_minutes':expected,'audited_gap_minutes':len(frame),
        'gap_range_counts':frame.gap_range_class.value_counts().to_dict(),
        'short_range_counts':frame.short_range_status.value_counts().to_dict(),
        'hedge_range_counts':frame.hedge_range_status.value_counts().to_dict(),
        'september29_counts':recent.gap_range_class.value_counts().to_dict(),
        'distinct_positions_with_gaps':frame.entry_ts.nunique(),
        'cache_requests':client.cached,'downloaded_requests':client.downloaded,
        'causality':'Actual ATM strike from completed decision-minus-one-minute candle; no source fill, future candle or quote interpolation.',
        'limitations':'Range availability is not candle availability. Inside-range gaps require separate exact-quote/conflict/source checks; this audit does not repair prices or rerun P&L.',
        'production_change':False,'replication_complete':False}
    (target/'held_quote_range_summary.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2),flush=True);return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download-only", action="store_true")
    parser.add_argument("--prepare-features", action="store_true")
    parser.add_argument("--replay-actual", action="store_true")
    parser.add_argument("--prepare-entry-quotes", action="store_true")
    parser.add_argument("--source-audit", action="store_true",help="Validate published timestamps and spread sides without fitting signals")
    parser.add_argument('--source-candles', action='store_true',help='Audit exact source-leg entry/exit OHLC using historical charts only')
    parser.add_argument('--source-fill-timing', action='store_true',help='Joint same-contract OHLC timing diagnosis for outside-range source events')
    parser.add_argument('--held-quote-limits', action='store_true',help='Classify all committed best-replication quote gaps using cached ATM-relative strike limits')
    parser.add_argument('--source-candles-limit', type=int, default=0,help='New leg events this invocation; zero processes all remaining')
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()
    if args.held_quote_limits:
        if any((args.download_only,args.prepare_features,args.replay_actual,args.prepare_entry_quotes,args.source_audit,args.source_candles,args.source_fill_timing,args.source_candles_limit)):
            parser.error('--held-quote-limits is a separate offline diagnostic')
        held_quote_range_audit();return
    if not 1 <= args.workers <= 16:
        parser.error("workers must be between 1 and 16; requests share a global rate limiter")
    if args.source_candles_limit < 0 or (args.source_candles_limit and not args.source_candles):
        parser.error('--source-candles-limit must be nonnegative and requires --source-candles')
    if args.source_candles and any((args.source_audit,args.prepare_entry_quotes,args.replay_actual,args.prepare_features,args.download_only)):
        parser.error('--source-candles is a separate diagnostic')
    if args.source_fill_timing and any((args.source_candles,args.source_audit,args.prepare_entry_quotes,args.replay_actual,args.prepare_features,args.download_only)):
        parser.error('--source-fill-timing is a separate diagnostic')
    if args.source_fill_timing:
        source_fill_timing()
    elif args.source_candles:
        source_candles(args.source_candles_limit)
    elif args.source_audit:
        audit_source_records()
    elif args.prepare_entry_quotes:
        prepare_entry_quotes()
    elif args.replay_actual:
        replay_actual_trades()
    elif args.prepare_features:
        prepare_features()
    else:
        download_research(args.workers)


if __name__ == "__main__":
    main()
