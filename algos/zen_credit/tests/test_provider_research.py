"""Historical regime boundaries and independence from unavailable future candles."""
from datetime import date
import numpy as np
import pandas as pd
from config import StrategyConfig
from backtest.provider_calendar import ProviderCalendar, expiries_for, history_config, lot_size
from risk.exits import time_exit_due
from strategy.alpha import calculate_alpha
from strategy.alpha2 import calculate_alpha2
from tests.conftest import ist, session_bars
from tests.conftest import make_chain
from dataclasses import replace
from strategy.engine import MarketView, StrategyEngine


def test_fixed_contract_rank_retains_original_price_denominator_and_causality():
    from backtest.provider_fixed_factors import contract_alpha2_ranks,contract_rank_price_changes
    index=pd.date_range('2025-07-01 09:16',periods=1100,freq='min',tz='Asia/Kolkata')
    t=np.arange(len(index),dtype=float)
    bars=pd.DataFrame({'open':22000+t+np.sin(t),'close':22002+t+2*np.cos(t/3)},index=index)
    changes=contract_rank_price_changes(bars)
    pd.testing.assert_series_equal(changes.close_old_open_h5,
        ((bars.close-bars.open.shift(5))/bars.open.shift(5)).rename('close_old_open_h5'))
    pd.testing.assert_series_equal(changes.close_close_old_open_h5,
        ((bars.close-bars.close.shift(5))/bars.open.shift(5)).rename('close_close_old_open_h5'))
    quotes=pd.DataFrame({'ce_ltp':100*np.exp(.03*np.sin(t/7)),
        'pe_ltp':90*np.exp(.04*np.cos(t/9)),
        'ce_volume':10+t%31,'pe_volume':12+t%19},index=index)
    whole=contract_alpha2_ranks(quotes,changes)
    assert whole.shape==(1100,48)
    pd.testing.assert_frame_equal(whole.iloc[:850],contract_alpha2_ranks(quotes.iloc[:850],changes.iloc[:850]))
    # Carry610 observations covers STD300 + lag5 + rank300 and return predecessor.
    carried=contract_alpha2_ranks(quotes.iloc[190:],changes.iloc[190:])
    pd.testing.assert_frame_equal(whole.iloc[800:],carried.loc[index[800:]])
    quotes.loc[index[900],'ce_volume']=np.nan
    unavailable=contract_alpha2_ranks(quotes,changes)
    assert unavailable.filter(regex='lag0$').loc[index[900]].isna().all()


def test_fixed_contract_ranks_are_not_changing_atm_path_ranks():
    from backtest.provider_fixed_factors import contract_alpha2_ranks
    index=pd.date_range('2025-07-01 09:16',periods=900,freq='min',tz='Asia/Kolkata')
    t=np.arange(len(index),dtype=float)
    changes=pd.DataFrame({'close_old_open_h5':np.sin(t/23),
        'close_close_old_open_h5':np.cos(t/29)},index=index)
    def quotes(offset):
        return pd.DataFrame({'ce_ltp':100*np.exp(.04*np.sin(t/(7+offset))),
            'pe_ltp':80*np.exp(.03*np.cos(t/(9+offset))),
            'ce_volume':20+(t%(31+offset))**2,'pe_volume':12+t%(19+offset)},index=index)
    a=contract_alpha2_ranks(quotes(0),changes);b=contract_alpha2_ranks(quotes(4),changes)
    pick=(t//40)%2==0;raw='raw_close_old_open_h5_native_v1_b10_logstd150_lag0'
    rank=raw.replace('raw_','rank_',1)
    selected=a[rank].where(pick,b[rank])
    stitched=a[raw].where(pick,b[raw]).rolling(300,min_periods=270).rank(pct=True)
    valid=selected.notna()&stitched.notna()
    assert valid.sum()>300
    assert (selected[valid]-stitched[valid]).abs().max()>.01


def test_fixed_contract_rank_masks_nonadjacent_returns():
    from backtest.provider_fixed_factors import contract_alpha2_ranks
    # Fewer than120 adjacent returns: huge overnight price jump cannot make STD valid.
    index=pd.DatetimeIndex([pd.Timestamp('2025-07-01',tz='Asia/Kolkata')+pd.Timedelta(days=i)
        for i in range(650)])
    t=np.arange(len(index),dtype=float)
    quotes=pd.DataFrame({'ce_ltp':100+t,'pe_ltp':90+t,
        'ce_volume':10+t%7,'pe_volume':12+t%11},index=index)
    changes=pd.DataFrame({'close_old_open_h5':np.sin(t),'close_close_old_open_h5':np.cos(t)},index=index)
    assert contract_alpha2_ranks(quotes,changes).isna().all().all()


def test_fixed_rank_volatility_variants_causal_and_original_unchanged():
    from backtest.provider_fixed_factors import contract_alpha2_ranks
    first=pd.date_range('2025-07-01 09:16',periods=375,freq='min',tz='Asia/Kolkata')
    second=pd.date_range('2025-07-02 09:16',periods=375,freq='min',tz='Asia/Kolkata')
    index=first.append(second);t=np.arange(len(index),dtype=float)
    quotes=pd.DataFrame({'ce_ltp':100*np.exp(.03*np.sin(t/7)+(t>=375)*.7),
        'pe_ltp':90*np.exp(.04*np.cos(t/9)+(t>=375)*.4),
        'ce_volume':10+t%31,'pe_volume':12+t%19},index=index)
    changes=pd.DataFrame({'close_old_open_h5':np.sin(t/23),
        'close_close_old_open_h5':np.cos(t/29)},index=index)
    original=contract_alpha2_ranks(quotes,changes)
    pd.testing.assert_frame_equal(original,contract_alpha2_ranks(quotes,changes,'adjacent_log_return'))
    # Independent original-formula calculation proves default behavior retained.
    ratios=[];stds=[]
    adjacent=pd.Series(index,index=index).diff().eq(pd.Timedelta(minutes=1))
    for side in ('ce','pe'):
        ratios.append(quotes[side+'_volume']/quotes[side+'_volume'].rolling(10,min_periods=8).mean())
        stds.append(np.log(quotes[side+'_ltp']/quotes[side+'_ltp'].shift()).where(adjacent).rolling(150,min_periods=120).std())
    raw=changes.close_old_open_h5*(ratios[0]+ratios[1])/2/(stds[0]+stds[1])
    name='raw_close_old_open_h5_native_v1_b10_logstd150_lag0'
    pd.testing.assert_series_equal(original[name],raw.rename(name))
    for variant,tag in (('observed_log_return','observedlogstd'),('price_std','pricestd')):
        full=contract_alpha2_ranks(quotes,changes,variant)
        assert full.shape==(750,48)
        assert all(tag in col for col in full)
        pd.testing.assert_frame_equal(full.iloc[:650],contract_alpha2_ranks(quotes.iloc[:650],changes.iloc[:650],variant))
    observed=contract_alpha2_ranks(quotes,changes,'observed_log_return')
    assert abs(observed[name.replace('logstd','observedlogstd')].iloc[375])<abs(original[name].iloc[375])
    quotes.loc[index[650],'ce_ltp']=np.nan
    unknown=contract_alpha2_ranks(quotes,changes,'observed_log_return')
    assert unknown.filter(regex='lag0$').loc[index[650]].isna().all()
    assert unknown.filter(regex='lag5$').loc[index[655]].isna().all()


def test_fixed_rank_price_std_matches_prices_and_masks_current_unknown():
    from backtest.provider_fixed_factors import contract_alpha2_ranks
    index=pd.date_range('2025-07-01 09:16',periods=700,freq='min',tz='Asia/Kolkata')
    t=np.arange(len(index),dtype=float)
    quotes=pd.DataFrame({'ce_ltp':(t%13)*2,'pe_ltp':t%17,
        'ce_volume':10+t%7,'pe_volume':12+t%11},index=index)
    changes=pd.DataFrame({'close_old_open_h5':np.sin(t),'close_close_old_open_h5':np.cos(t)},index=index)
    full=contract_alpha2_ranks(quotes,changes,'price_std')
    scale=quotes.ce_ltp.rolling(150,min_periods=120).std()+quotes.pe_ltp.rolling(150,min_periods=120).std()
    ratio=(quotes.ce_volume/quotes.ce_volume.rolling(10,min_periods=8).mean()+
        quotes.pe_volume/quotes.pe_volume.rolling(10,min_periods=8).mean())/2
    name='raw_close_old_open_h5_native_v1_b10_pricestd150_lag0'
    pd.testing.assert_series_equal(full[name],(changes.close_old_open_h5*ratio/scale).rename(name))
    quotes.loc[index[600],'ce_ltp']=np.nan
    unknown=contract_alpha2_ranks(quotes,changes,'price_std')
    assert unknown.filter(regex='lag0$').loc[index[600]].isna().all()
    assert unknown.filter(regex='lag5$').loc[index[605]].isna().all()
    assert np.isfinite(unknown[name].loc[index[601]])


def test_fixed_rank_variant_paths_preserve_default_and_separate_new_caches():
    import pytest
    from backtest.provider_fixed_factors import fixed_rank_variant_paths,OPENING_FIXED_RANK_CACHE,OUTPUT
    base=fixed_rank_variant_paths()
    assert base==(OPENING_FIXED_RANK_CACHE,OUTPUT/'opening_fixed_rank_chunks',OUTPUT/'opening_fixed_rank_design.json')
    observed=fixed_rank_variant_paths('observed_log_return');price=fixed_rank_variant_paths('price_std')
    assert len({base[0],observed[0],price[0]})==3
    assert len({base[1],observed[1],price[1]})==3
    assert len({base[2],observed[2],price[2]})==3
    assert observed[0].name=='provider_opening_fixed_contract_ranks_observed_log_return.csv.gz'
    assert price[0].name=='provider_opening_fixed_contract_ranks_price_std.csv.gz'
    with pytest.raises(ValueError,match='volatility'):fixed_rank_variant_paths('invalid')


def test_fixed_rank_five_minute_std_and_adjacent_rms_independent_numeric_causality():
    from backtest.provider_fixed_factors import contract_alpha2_ranks,fixed_rank_variant_paths
    base=pd.date_range('2025-07-01 09:16',periods=1000,freq='min',tz='Asia/Kolkata')
    # A genuine two-minute clock gap, followed later by an absent current quote.
    index=pd.DatetimeIndex([ts+(pd.Timedelta(minutes=2) if i>=400 else pd.Timedelta(0)) for i,ts in enumerate(base)])
    t=np.arange(len(index),dtype=float)
    quotes=pd.DataFrame({'ce_ltp':100*np.exp(.001*t+.03*np.sin(t/7)),
        'pe_ltp':90*np.exp(-.0005*t+.04*np.cos(t/9)),
        'ce_volume':10+t%31,'pe_volume':12+t%19},index=index)
    quotes.loc[index[500],'ce_ltp']=np.nan
    changes=pd.DataFrame({'close_old_open_h5':np.sin(t/23),
        'close_close_old_open_h5':np.cos(t/29)},index=index)
    for variant,tag,horizon in (('adjacent_five_minute_log_return','five_minute_logstd',5),
        ('adjacent_log_rms','adjacentlogrms',1)):
        actual=contract_alpha2_ranks(quotes,changes,variant)
        scales=[];ratios=[]
        for side in ('ce','pe'):
            prices=quotes[side+'_ltp'].to_numpy();values=np.full(len(prices),np.nan)
            for i in range(horizon,len(prices)):
                span=prices[i-horizon:i+1]
                known=np.isfinite(span).all() and (span>0).all()
                adjacent=all(index[j]-index[j-1]==pd.Timedelta(minutes=1) for j in range(i-horizon+1,i+1))
                if known and adjacent:values[i]=np.log(prices[i]/prices[i-horizon])
            returns=pd.Series(values,index=index)
            scales.append(np.sqrt(returns.pow(2).rolling(150,min_periods=120).mean())
                if variant=='adjacent_log_rms' else returns.rolling(150,min_periods=120).std())
            volume=quotes[side+'_volume'];ratios.append(volume/volume.rolling(10,min_periods=8).mean())
        factor=((ratios[0]+ratios[1])/2/(scales[0]+scales[1])).where(quotes.ce_ltp.notna()&quotes.pe_ltp.notna())
        for lag in (0,5):
            raw=changes.close_old_open_h5*factor.shift(lag)
            name=f'raw_close_old_open_h5_native_v1_b10_{tag}150_lag{lag}'
            pd.testing.assert_series_equal(actual[name],raw.rename(name))
            rank=name.replace('raw_','rank_',1)
            pd.testing.assert_series_equal(actual[rank],raw.rolling(300,min_periods=270).rank(pct=True).rename(rank))
        pd.testing.assert_frame_equal(actual.iloc[:850],contract_alpha2_ranks(quotes.iloc[:850],changes.iloc[:850],variant))
        carried=contract_alpha2_ranks(quotes.iloc[190:],changes.iloc[190:],variant)
        pd.testing.assert_frame_equal(actual.iloc[800:],carried.loc[index[800:]])
        assert actual.filter(regex='lag0$').loc[index[500]].isna().all()
        assert actual.filter(regex='lag5$').loc[index[505]].isna().all()
        assert variant in fixed_rank_variant_paths(variant)[0].name


def test_shared_fixed_rank_preparation_equals_separate_and_resumes_without_recalculation(tmp_path,monkeypatch):
    import json
    import backtest.provider_fixed_factors as fixed
    index=pd.date_range('2025-07-01 09:15',periods=700,freq='min',tz='Asia/Kolkata')
    t=np.arange(len(index),dtype=float);expiry=date(2025,7,3)
    bars=pd.DataFrame({'open':25000+np.sin(t/23)*30,'close':25002+np.cos(t/29)*20},index=index)
    bar_cache=tmp_path/'bars.csv.gz';bars.to_csv(bar_cache)
    opening=tmp_path/'opening.csv.gz'
    pd.DataFrame({'minute':index+pd.Timedelta(minutes=1),'expiry':expiry,'atm_strike':25000.}).to_csv(opening,index=False)
    q=pd.DataFrame({'ce_ltp':100*np.exp(.02*np.sin(t/7)),
        'pe_ltp':80*np.exp(.03*np.cos(t/9)),'ce_volume':20+t%31,'pe_volume':10+t%19},
        index=pd.MultiIndex.from_arrays([index+pd.Timedelta(minutes=1),[expiry]*700,[25000.]*700],names=['minute','expiry','strike']))
    blocks=[(date(2025,7,1),date(2025,7,2)),(date(2025,7,2),date(2025,7,3))]
    calls=[];supplements=[]
    def load(client,first,last,**kw):
        calls.append(first);sl=slice(0,600) if first==blocks[0][0] else slice(600,700)
        return bars.iloc[sl],q.iloc[sl],pd.DataFrame()
    def supplement(client,current,quotes,last,*args):
        supplements.append(last);return quotes,{'fixed_contracts':0}
    monkeypatch.setattr(fixed,'BAR_CACHE',bar_cache);monkeypatch.setattr(fixed,'OPENING_CACHE',opening)
    monkeypatch.setattr(fixed,'history_blocks',lambda:blocks)
    monkeypatch.setattr(fixed,'load_history',load);monkeypatch.setattr(fixed,'supplement_fixed_contracts',supplement)
    modes=('adjacent_five_minute_log_return','adjacent_log_rms')
    def root(path):
        path.mkdir(exist_ok=True);monkeypatch.setattr(fixed,'OUTPUT',path)
        monkeypatch.setattr(fixed,'OPENING_FIXED_RANK_CACHE',path/'provider_opening_fixed_contract_ranks.csv.gz')
    root(tmp_path/'separate')
    expected={}
    for mode in modes:
        fixed.prepare_opening_fixed_ranks(mode)
        expected[mode]=pd.read_csv(fixed.fixed_rank_variant_paths(mode)[0])
    assert len(calls)==4 and len(supplements)==4
    calls.clear();supplements.clear();root(tmp_path/'shared')
    fixed.prepare_opening_fixed_rank_variants(modes)
    assert len(calls)==2 and len(supplements)==2
    for mode in modes:
        destination,_,design=fixed.fixed_rank_variant_paths(mode)
        pd.testing.assert_frame_equal(expected[mode],pd.read_csv(destination))
        assert json.loads(design.read_text())['warmup_carry']==610
    # Resume only one missing mode/chunk; both loads remain necessary for carry.
    _,chunks,_=fixed.fixed_rank_variant_paths(modes[1])
    (chunks/f'{blocks[1][0]}_{blocks[1][1]}.csv.gz').unlink()
    original=fixed.contract_alpha2_ranks;computed=[]
    def calculate(quotes,changes,mode):computed.append(mode);return original(quotes,changes,mode)
    monkeypatch.setattr(fixed,'contract_alpha2_ranks',calculate)
    calls.clear();supplements.clear();fixed.prepare_opening_fixed_rank_variants(modes)
    assert len(calls)==2 and len(supplements)==2 and computed==[modes[1]]
    for mode in modes:pd.testing.assert_frame_equal(expected[mode],pd.read_csv(fixed.fixed_rank_variant_paths(mode)[0]))


def test_shared_fixed_rank_mode_validation_precedes_history_loading(monkeypatch):
    import pytest
    import backtest.provider_fixed_factors as fixed
    monkeypatch.setattr(fixed,'load_history',lambda *args,**kwargs:pytest.fail('Invalid modes must not load data'))
    for modes in ((),('price_std','price_std'),('unknown',),('price_std','observed_log_return','adjacent_log_rms')):
        with pytest.raises(ValueError):fixed.prepare_opening_fixed_rank_variants(modes)


def test_opening_full_fields_exact_clock_offsets_conflicts_and_absence():
    import backtest.provider_fixed_factors as fixed
    raw_index=pd.date_range('2025-07-01 10:15',periods=4,freq='min',tz='Asia/Kolkata')
    raw=pd.DataFrame({field:np.arange(4,dtype=float)+10 for field in fixed.OPENING_FULL_FIELDS},index=raw_index)
    raw.strike=25050.;atm=fixed.opening_full_field_rows(raw,1)
    assert atm.minute.iloc[0]==raw_index[0]+pd.Timedelta(minutes=1)
    labels=pd.DataFrame({'minute':atm.minute,'expiry':atm.expiry,'atm_strike':[25000.,24800.,25000.,25000.]})
    offsets,status=fixed.opening_full_field_offsets(labels,atm,1)
    assert offsets==[-1] and status.status.tolist()==['available','outside_initial_offset_bound','available','available']
    ce=atm.copy();pe=atm.copy();ce.strike=25000.;pe.strike=25000.
    ce.close=[101.,102.,103.,104.];pe.close=[201.,202.,203.,204.]
    wrong=ce.copy();wrong.strike=25050.;wrong.close=999.
    duplicate=ce.iloc[[2]].copy();duplicate.high+=1 # Exact contract conflict excluded.
    # Fourth PE quote absent; known CE must not supply a paired full-field row.
    joined=fixed.join_opening_full_fields(labels,{'ce':[ce,wrong,duplicate],'pe':[pe.iloc[:3]]})
    assert joined.both_exact_rows_available.tolist()==[True,False,False,False]
    assert joined.ce_close.iloc[0]==101. and joined.pe_close.iloc[0]==201.
    assert joined.ce_row_conflict.tolist()==[False,False,True,False]
    assert joined.ce_close.iloc[1:].isna().all() and joined.pe_close.iloc[1:].isna().all()
    absent=fixed.join_opening_full_fields(labels,{'ce':[ce],'pe':[]})
    assert not absent.both_exact_rows_available.any() and absent.ce_close.isna().all()
    # Moving a row one minute later cannot affect a prior decision's fields.
    assert joined.minute.min()>raw_index.min()


def test_opening_full_fields_partial_resume_fetches_only_needed_bounded_offsets(tmp_path,monkeypatch):
    import json
    import backtest.provider_fixed_factors as fixed
    blocks=[(date(2025,7,1),date(2025,7,2)),(date(2025,7,2),date(2025,7,3))]
    rows=[]
    for first,last in blocks:
        minute=pd.Timestamp(str(first)+' 10:16',tz='Asia/Kolkata')
        for expiry in fixed.expiries_for(first):rows.append({'minute':minute,'expiry':expiry,'atm_strike':25000.})
    opening=tmp_path/'opening.csv.gz';pd.DataFrame(rows).to_csv(opening,index=False)
    monkeypatch.setattr(fixed,'OUTPUT',tmp_path);monkeypatch.setattr(fixed,'OPENING_CACHE',opening)
    monkeypatch.setattr(fixed,'OPENING_FULL_FIELDS_CACHE',tmp_path/'full.csv.gz')
    monkeypatch.setattr(fixed,'history_blocks',lambda:blocks)
    class FakeClient:
        def __init__(self):self.calls=[];self.downloaded=0
        def request(self,endpoint,payload):
            assert endpoint=='rollingoption';self.calls.append(payload.copy());self.downloaded+=1
            assert payload['requiredData']==list(fixed.OPENING_FULL_FIELDS)
            assert payload['strike'] in ('ATM','ATM-1')
            minute=pd.Timestamp(payload['fromDate']+' 10:15',tz='Asia/Kolkata')
            strike=25050. if payload['strike']=='ATM' else 25000.
            raw={field:[10.] for field in fixed.OPENING_FULL_FIELDS};raw['strike']=[strike]
            raw['timestamp']=[int(minute.timestamp())]
            return {'data':{'ce' if payload['drvOptionType']=='CALL' else 'pe':raw}}
    client=FakeClient();first=fixed.prepare_opening_full_fields(client,limit_blocks=1)
    assert len(first)==2 and first.both_exact_rows_available.all() and len(client.calls)==8
    design=json.loads((tmp_path/'opening_full_fields_design.json').read_text())
    assert not design['complete'] and design['completed_blocks']==1
    client.calls.clear();complete=fixed.prepare_opening_full_fields(client)
    assert len(complete)==4 and complete.both_exact_rows_available.all() and len(client.calls)==8
    assert {call['fromDate'] for call in client.calls}=={'2025-07-02'}
    client.calls.clear();resumed=fixed.prepare_opening_full_fields(client)
    pd.testing.assert_frame_equal(complete,resumed)
    assert not client.calls
    design=json.loads((tmp_path/'opening_full_fields_design.json').read_text())
    assert design['complete'] and design['both_exact_rows_available']==4


def test_fixed_ohlc_contract_clock_matches_full108_factors_and_prefix():
    from backtest.provider_fixed_factors import (fixed_ohlc_contract_clock,
        fixed_ohlc_history_needs,contract_ohlc_factors)
    clock=pd.date_range('2025-07-01 09:16',periods=1800,freq='min',tz='Asia/Kolkata')
    t=np.arange(len(clock),dtype=float)
    quotes=pd.DataFrame(index=clock)
    for side,offset in (('ce',0),('pe',10)):
        o=90+offset+np.sin(t/17)
        c=o+np.sin(t/11)*.7
        for field,value in (('open',o),('close',c),('high',np.maximum(o,c)+.5),
                            ('low',np.minimum(o,c)-.5),('volume',30+t%23)):
            quotes[f'{side}_{field}']=value
    for positions in ([20,100,900],[500,510,1400]):
        visits=clock[positions]
        labels=pd.DataFrame({'minute':visits,'expiry':date(2025,7,3),'atm_strike':22000})
        needed=fixed_ohlc_history_needs(labels,clock)
        filtered=quotes.where(pd.Series(quotes.index.isin(needed.minute),index=clock),axis=0)
        # Exact-current quote missing at the last visit; lag5 still sees its
        # historical input. Another hole stays in the common clock.
        filtered.loc[visits[-1],'ce_close']=np.nan
        filtered.loc[clock[positions[-1]-12],'pe_volume']=np.nan
        bounded=fixed_ohlc_contract_clock(clock,visits)
        assert bounded.equals(clock[max(0,positions[0]-304):positions[-1]+1])
        if positions[0]==500:assert clock[950] in bounded and filtered.loc[clock[950]].isna().all()
        full=contract_ohlc_factors(filtered).loc[visits]
        trimmed=contract_ohlc_factors(filtered.loc[bounded]).loc[visits]
        assert full.shape==(3,108)
        pd.testing.assert_frame_equal(full.isna(),trimmed.isna())
        pd.testing.assert_frame_equal(full,trimmed,check_exact=True)
        assert trimmed.filter(regex='lag0$').iloc[-1].isna().all()
        assert trimmed.filter(regex='lag5$').iloc[-1].notna().all()
        prefix_clock=clock[:positions[1]+1]
        prefix_visits=visits[:2]
        prefix_labels=labels.iloc[:2]
        prefix_needs=fixed_ohlc_history_needs(prefix_labels,prefix_clock)
        prefix_quotes=quotes.loc[prefix_clock].where(pd.Series(prefix_clock.isin(prefix_needs.minute),index=prefix_clock),axis=0)
        prefix=contract_ohlc_factors(prefix_quotes.loc[fixed_ohlc_contract_clock(prefix_clock,prefix_visits)]).loc[prefix_visits]
        pd.testing.assert_frame_equal(trimmed.iloc[:2],prefix,check_exact=True)
    import pytest
    with pytest.raises(ValueError,match='absent'):fixed_ohlc_contract_clock(clock,[clock[-1]+pd.Timedelta(minutes=1)])
    with pytest.raises(ValueError,match='selected visits'):fixed_ohlc_contract_clock(clock,[])
    with pytest.raises(ValueError,match='unique and ordered'):fixed_ohlc_contract_clock(clock[::-1],clock[:1])


def test_fixed_ohlc_history_needs_union_uses305_clock_slots_and_retains_holes():
    from backtest.provider_fixed_factors import fixed_ohlc_history_needs
    clock=pd.date_range('2025-07-01 09:16',periods=600,freq='min',tz='Asia/Kolkata')
    labels=pd.DataFrame({'minute':[clock[500],clock[550]],'expiry':[date(2025,7,3)]*2,'atm_strike':[25000.]*2})
    needs=fixed_ohlc_history_needs(labels,clock)
    assert len(needs)==355 and needs.minute.min()==clock[196] and needs.minute.max()==clock[550]
    assert clock[300] in set(needs.minute) # No quote information may compress this clock.
    prefix=fixed_ohlc_history_needs(labels.iloc[:1],clock[:501])
    assert len(prefix)==305 and prefix.minute.max()==clock[500]


def test_fixed_ohlc_prep_previous_scope_new_strike_conflicts_gaps_lag_and_resume(tmp_path,monkeypatch):
    import json
    import backtest.provider_fixed_factors as fixed
    blocks=[(date(2025,7,1),date(2025,7,2)),(date(2025,7,2),date(2025,7,3))]
    raw_clock=pd.date_range('2025-07-01 09:15',periods=375,freq='min',tz='Asia/Kolkata').append(
        pd.date_range('2025-07-02 09:15',periods=375,freq='min',tz='Asia/Kolkata'))
    clock=raw_clock+pd.Timedelta(minutes=1);bars=pd.DataFrame({'open':25000.,'close':25000.},index=raw_clock)
    bar_cache=tmp_path/'bars.csv.gz';bars.to_csv(bar_cache)
    labels=[]
    for i,first in enumerate((blocks[0][0],blocks[1][0])):
        for expiry in fixed.expiries_for(first):
            for minute in clock[i*375:(i+1)*375]:labels.append({'minute':minute,'expiry':expiry,'atm_strike':25000.+200*i})
    opening=tmp_path/'opening.csv.gz';pd.DataFrame(labels).to_csv(opening,index=False)
    monkeypatch.setattr(fixed,'OUTPUT',tmp_path);monkeypatch.setattr(fixed,'BAR_CACHE',bar_cache)
    monkeypatch.setattr(fixed,'OPENING_CACHE',opening);monkeypatch.setattr(fixed,'OPENING_FIXED_OHLC_CACHE',tmp_path/'own.csv.gz')
    monkeypatch.setattr(fixed,'history_blocks',lambda:blocks)
    class FakeClient:
        def __init__(self):self.calls=[];self.downloaded=0;self.cached=0;self.cache={}
        def request(self,endpoint,payload):
            assert endpoint=='rollingoption' and payload['requiredData']==list(fixed.OPENING_FULL_FIELDS)
            key=json.dumps(payload,sort_keys=True);self.calls.append(payload.copy())
            if key in self.cache:self.cached+=1;return self.cache[key]
            self.downloaded+=1
            day=0 if payload['fromDate']=='2025-07-01' else 1
            offset=0 if payload['strike']=='ATM' else int(payload['strike'][3:])
            strike=25000.+200*day+50*offset;side=payload['drvOptionType'];code=payload['expiryCode']
            assert abs(offset)<=(10 if code==1 else 3)
            times=raw_clock[day*375:(day+1)*375];g=np.arange(day*375,(day+1)*375,dtype=float)
            o=(100. if side=='CALL' else 90.)+np.sin(g/7)+(strike-25000)/100
            c=o+.4*np.sin(g/11)
            raw={'timestamp':[int(ts.timestamp()) for ts in times],'open':o.tolist(),'high':(o+1).tolist(),
                'low':(o-1).tolist(),'close':c.tolist(),'volume':(20+g%31).tolist(),'strike':[strike]*375,
                'spot':[25000.+200*day]*375,'iv':[10.]*375,'oi':[1000.]*375}
            if day==1 and side=='CALL':
                for field in raw:raw[field].pop(100) # Missing quote stays a clock slot.
            if day==0 and side=='CALL' and code==1 and offset==4:
                for field in raw:raw[field].append(raw[field][300]+(1 if field=='high' else 0))
            response={'data':{'ce' if side=='CALL' else 'pe':raw}};self.cache[key]=response;return response
    client=FakeClient();first=fixed.prepare_opening_fixed_ohlc(client,limit_blocks=1)
    assert len(first)==750 and len(client.calls)==4
    design=json.loads((tmp_path/'opening_fixed_ohlc_design.json').read_text());assert not design['complete']
    client.calls.clear();complete=fixed.prepare_opening_fixed_ohlc(client)
    assert len(complete)==1500
    previous=[p for p in client.calls if p['fromDate']=='2025-07-01']
    assert len(previous)==6
    assert {p['strike'] for p in previous if p['expiryCode']==1}=={'ATM','ATM+4'}
    assert {p['strike'] for p in previous if p['expiryCode']==2}=={'ATM'} # Unsupported+4 remains unknown.
    current=complete.loc[(complete.minute>=clock[375])&(complete.expiry==fixed.expiries_for(blocks[1][0])[0])].set_index('minute')
    name='fixed_ohlc_garman_klass_300_native_b10_lag0'
    assert np.isfinite(current[name].iloc[0]) # Prior newly requested+4 supplies warmup.
    assert np.isnan(current[name].loc[clock[475]])
    assert np.isnan(current[name.replace('lag0','lag5')].loc[clock[480]])
    next_expiry=complete.loc[(complete.minute>=clock[375])&(complete.expiry==fixed.expiries_for(blocks[1][0])[1])]
    assert np.isnan(next_expiry[name].iloc[0]) # No synthetic unsupported history.
    details=json.loads((tmp_path/'opening_fixed_ohlc_chunks'/f'{blocks[1][0]}_{blocks[1][1]}.csv.gz.json').read_text())
    assert details['prior_clock_rows']==330 and details['exact_conflict_keys']['ce']==1
    assert details['support_statuses']['2025-07-01_2_ce']['outside_initial_offset_bound']>0
    # Partial resume rebuilds previous scope from raw payloads, with no carryfile.
    destination=tmp_path/'opening_fixed_ohlc_chunks'/f'{blocks[1][0]}_{blocks[1][1]}.csv.gz'
    destination.with_name(destination.name+'.json').unlink();client.calls.clear()
    resumed=fixed.prepare_opening_fixed_ohlc(client)
    pd.testing.assert_frame_equal(complete,resumed,check_exact=True)
    assert any(p['fromDate']=='2025-07-01' and p['strike']=='ATM+4' for p in client.calls)
    client.calls.clear();cached=fixed.prepare_opening_fixed_ohlc(client)
    pd.testing.assert_frame_equal(complete,cached,check_exact=True);assert not client.calls


def test_fixed_ohlc_offline_incomplete_chunk_is_retried_online(tmp_path,monkeypatch):
    import json
    import backtest.provider_fixed_factors as fixed
    first,last=date(2025,7,1),date(2025,7,2)
    raw_clock=pd.date_range('2025-07-01 09:15',periods=375,freq='min',tz='Asia/Kolkata')
    bars=pd.DataFrame({'open':25000.,'close':25001.},index=raw_clock);bar_cache=tmp_path/'bars.csv.gz';bars.to_csv(bar_cache)
    opening=tmp_path/'opening.csv.gz'
    pd.DataFrame({'minute':raw_clock+pd.Timedelta(minutes=1),'expiry':fixed.expiries_for(first)[0],'atm_strike':25000.}).to_csv(opening,index=False)
    monkeypatch.setattr(fixed,'OUTPUT',tmp_path);monkeypatch.setattr(fixed,'BAR_CACHE',bar_cache)
    monkeypatch.setattr(fixed,'OPENING_CACHE',opening);monkeypatch.setattr(fixed,'OPENING_FIXED_OHLC_CACHE',tmp_path/'own.csv.gz')
    monkeypatch.setattr(fixed,'history_blocks',lambda:[(first,last)])
    class OfflineClient:
        downloaded=0;cached=0
        def request(self,endpoint,payload):raise RuntimeError('Missing offline cache: rollingoption 2025-07-01')
    partial=fixed.prepare_opening_fixed_ohlc(OfflineClient(),offline=True)
    assert partial.filter(regex='^fixed_ohlc_').isna().all().all()
    design=json.loads((tmp_path/'opening_fixed_ohlc_design.json').read_text())
    assert not design['complete'] and design['computed_blocks']==1 and design['completed_blocks']==0
    assert not design['chunks'][0]['requests_complete']
    class OnlineClient:
        def __init__(self):self.downloaded=0;self.cached=0
        def request(self,endpoint,payload):
            self.downloaded+=1;t=np.arange(375,dtype=float);o=100+np.sin(t/9);c=o+.2*np.cos(t/7)
            raw={'timestamp':[int(ts.timestamp()) for ts in raw_clock],'open':o.tolist(),'close':c.tolist(),
                'high':(o+1).tolist(),'low':(o-1).tolist(),'volume':(20+t%31).tolist(),
                'strike':[25000.]*375,'spot':[25000.]*375,'iv':[10.]*375,'oi':[1000.]*375}
            return {'data':{'ce' if payload['drvOptionType']=='CALL' else 'pe':raw}}
    client=OnlineClient();complete=fixed.prepare_opening_fixed_ohlc(client)
    assert client.downloaded==2 and complete.filter(regex='^fixed_ohlc_').iloc[-1].notna().all()
    design=json.loads((tmp_path/'opening_fixed_ohlc_design.json').read_text())
    assert design['complete'] and design['computed_blocks']==design['completed_blocks']==1
    assert design['chunks'][0]['requests_complete']


def test_bulk_merge_deterministic_ties_and_exact_rank_aliases(tmp_path):
    import json
    from backtest.provider_price_bounds import merge_bulk_frontiers
    for shard,cid,values in ((0,'b',[.1,.2]),(1,'a',[.3,.4]),(2,'alias',[.1,.2])):
        directory=tmp_path/f'shard_{shard:02d}';directory.mkdir()
        (directory/'search_design.json').write_text(json.dumps({'tested_formula_recipes':1}))
        (directory/'frontier.json').write_text(json.dumps([{'candidate_id':cid,'objective':[5,8,-10]}]))
        np.savez_compressed(directory/f'candidate_{cid}.npz',minutes=[1,2],alpha=values,alpha2=[.1,.1])
    result=merge_bulk_frontiers(tmp_path)
    selected=json.loads((tmp_path/'frontier.json').read_text())
    assert [c['candidate_id'] for c in selected]==['a','alias']
    assert result['identical_rank_aliases']==['b'] and result['completed_recipes']==3
    assert not result['complete']
    for c in selected:assert (tmp_path/f'candidate_{c["candidate_id"]}.npz').exists()


def test_bulk_merge_deduplicates_signal_equivalents_but_retains_distinct_exit_policy(tmp_path):
    import json
    from backtest.provider_price_bounds import merge_bulk_frontiers
    for shard,cid,a,recipe in ((0,'a',[.9,.1],{}),(1,'b',[.95,.05],{}),
                               (2,'c',[.95,.05],{'profit_target_mode':'disabled'})):
        directory=tmp_path/f'shard_{shard:02d}';directory.mkdir()
        (directory/'search_design.json').write_text(json.dumps({'tested_formula_recipes':1}))
        candidate={'candidate_id':cid,'objective':[5,8,-10],'recipe':recipe}
        (directory/'frontier.json').write_text(json.dumps([candidate]))
        np.savez_compressed(directory/f'candidate_{cid}.npz',minutes=[1,2],alpha=a,alpha2=[.9,.1])
    result=merge_bulk_frontiers(tmp_path)
    selected=json.loads((tmp_path/'frontier.json').read_text())
    assert [c['candidate_id'] for c in selected]==['a','c']
    assert result['identical_signal_aliases']==[{'candidate_id':'b','representative':'a'}]


def test_bulk_scheduler_surfaces_failed_shard_without_retry(tmp_path,monkeypatch):
    import subprocess
    import pytest
    from types import SimpleNamespace
    import backtest.provider_price_bounds as bounds
    calls=[]
    def child(command,**kwargs):
        shard=int(command[command.index('--shard')+1]);calls.append(shard)
        assert kwargs['creationflags']==getattr(subprocess,'CREATE_NO_WINDOW',0)
        assert '--limit' in command
        return SimpleNamespace(returncode=7 if shard==3 else 0)
    monkeypatch.setattr(bounds,'OUT',tmp_path)
    monkeypatch.setattr(subprocess,'run',child)
    monkeypatch.setattr(bounds,'merge_bulk_frontiers',lambda root:pytest.fail('Failed scan must not merge as successful'))
    with pytest.raises(RuntimeError,match='exit_code.*7'):bounds.run_bulk_workers(2,1)
    assert sorted(calls)==list(range(16))
    assert (tmp_path/'bulk'/'worker_failures.json').exists()


def test_autonomous_replay_stops_before_scoring_later_chunks_without_official_settlement(tmp_path,monkeypatch):
    import backtest.provider_autonomous as autonomous
    from types import SimpleNamespace
    from backtest.engine import BacktestResult
    entry=pd.Timestamp('2025-11-28 10:15',tz='Asia/Kolkata')
    exit_ts=pd.Timestamp('2025-12-02 15:00',tz='Asia/Kolkata')
    source=pd.DataFrame([{'signal_id':'source','split':'fit','entry':entry,'exit':exit_ts,
        'entry_minute':entry,'exit_minute':exit_ts,'option_type':'CE','short_strike':26150.,
        'hedge_strike':26550.,'expiry':date(2025,12,2)}])
    idx=pd.DatetimeIndex(['2025-12-03 09:16'],tz='Asia/Kolkata')
    np.savez_compressed(tmp_path/'candidate_test.npz',minutes=idx.as_unit('ns').asi8,alpha=[.1],alpha2=[.1])
    monkeypatch.setattr(autonomous,'provider_trades',lambda:source)
    monkeypatch.setattr(autonomous,'history_blocks',lambda:[(date(2025,12,3),date(2025,12,4)),(date(2025,12,4),date(2025,12,5))])
    monkeypatch.setattr(autonomous,'DhanHistoryClient',lambda **kwargs:SimpleNamespace(cache_dir=tmp_path))
    monkeypatch.setattr(autonomous,'NSESettlementClient',lambda *args,**kwargs:SimpleNamespace(get=lambda expiry:None))
    loaded=[]
    def history(*args,**kwargs):
        loaded.append(args[1]);return pd.DataFrame(),pd.DataFrame(),pd.DataFrame()
    monkeypatch.setattr(autonomous,'load_history',history)
    monkeypatch.setattr(autonomous,'supplement_fixed_contracts',lambda *args:(pd.DataFrame(),{}))
    class Replay:
        def __init__(self,*args,settlement_loader,**kwargs):
            self.loader=settlement_loader;self.coverage_events=[];self.decisions=[]
        def run(self,**kwargs):
            self.loader(date(2025,12,2))
            return BacktestResult(last_decision=idx[0].to_pydatetime())
    monkeypatch.setattr(autonomous,'DhanReplay',Replay)
    import pytest
    with pytest.raises(RuntimeError,match='Official NSE settlement for 2025-12-02 is unavailable'):
        autonomous.run({'candidate_id':'test','recipe':{}},tmp_path)
    assert len(loaded)==1
    assert not (tmp_path/'full_autonomous_test_ledger'/'report.json').exists()


def autonomous_batch_fixture(tmp_path,monkeypatch):
    """Real quote-based engine: opposite spreads held over a chunk boundary."""
    import backtest.provider_autonomous as autonomous
    from types import SimpleNamespace
    entry=pd.Timestamp('2026-09-28 10:18',tz='Asia/Kolkata')
    exit_ts=pd.Timestamp('2026-09-29 09:27',tz='Asia/Kolkata')
    expiry=date(2026,9,29)
    source=pd.DataFrame([dict(signal_id=side,split='case_study',entry=entry,exit=exit_ts,
        entry_minute=entry,exit_minute=exit_ts,option_type=side,short_strike=23000.,
        hedge_strike=23400. if side=='CE' else 22600.,expiry=expiry,
        # Known synthetic comparison P&L: entry100 less exit5, four65-unit lots.
        pnl_reported=24700.) for side in ('CE','PE')])
    candidates=[dict(candidate_id='bear',recipe={}),
                dict(candidate_id='bull',recipe={'threshold_comparison':'bullish_inclusive'})]
    idx=pd.DatetimeIndex([entry,exit_ts])
    for candidate,value in zip(candidates,(.1,.9)):
        np.savez_compressed(tmp_path/f"candidate_{candidate['candidate_id']}.npz",
            minutes=idx.as_unit('ns').asi8,alpha=[value,value],alpha2=[value,value])
    blocks=[(date(2026,9,28),date(2026,9,29)),(date(2026,9,29),date(2026,9,30))]
    monkeypatch.setattr(autonomous,'provider_trades',lambda:source)
    monkeypatch.setattr(autonomous,'history_blocks',lambda:blocks)
    monkeypatch.setattr(autonomous,'DhanHistoryClient',lambda **kwargs:SimpleNamespace(cache_dir=tmp_path))
    # Settlement must not be needed: both positions close on quoted target hits.
    def settlement(expiry):raise AssertionError('Unexpected settlement request')
    monkeypatch.setattr(autonomous,'NSESettlementClient',lambda *args,**kwargs:SimpleNamespace(get=settlement))
    loaded=[];snapshots=[]
    def history(client,first,last,**kwargs):
        loaded.append(first);minute=entry if first==blocks[0][0] else exit_ts
        bars=pd.DataFrame({'open':[23000.],'close':[23000.]},index=[minute-pd.Timedelta(minutes=1)])
        prices=(120.,20.) if first==blocks[0][0] else (7.,2.)
        rows=[dict(minute=minute,expiry=expiry,strike=strike,
                   ce_ltp=prices[0] if strike==23000 else prices[1],
                   pe_ltp=prices[0] if strike==23000 else prices[1])
              for strike in (22600.,23000.,23400.)]
        quotes=pd.DataFrame(rows).set_index(['minute','expiry','strike']).sort_index()
        snapshots.append((bars,bars.copy(deep=True),quotes,quotes.copy(deep=True)))
        return bars,quotes,pd.DataFrame()
    monkeypatch.setattr(autonomous,'load_history',history)
    monkeypatch.setattr(autonomous,'supplement_fixed_contracts',lambda client,bars,options,*args:(options,{}))
    return autonomous,candidates,loaded,snapshots


def test_shared_chunk_batch_equals_real_engine_single_runs(tmp_path,monkeypatch):
    import json
    import gzip
    autonomous,candidates,loaded,snapshots=autonomous_batch_fixture(tmp_path,monkeypatch)
    single=tmp_path/'single';single.mkdir()
    batch=tmp_path/'batch';batch.mkdir()
    for candidate in candidates:
        for folder in (single,batch):
            (folder/f"candidate_{candidate['candidate_id']}.npz").write_bytes(
                (tmp_path/f"candidate_{candidate['candidate_id']}.npz").read_bytes())
        autonomous.run(candidate,single)
    assert len(loaded)==4
    loaded.clear()
    preparations=[]
    real_prepare=autonomous.prepare_option_quotes
    def prepare(quotes):
        preparations.append(quotes)
        return real_prepare(quotes)
    monkeypatch.setattr(autonomous,'prepare_option_quotes',prepare)
    targets=autonomous.run_batch(candidates,batch)
    assert len(loaded)==2
    assert len(preparations)==2  # Once per chunk, shared by both engines.
    for candidate,target in zip(candidates,targets):
        original=single/target.name
        for name in ('checkpoint.json','report.json'):
            assert json.loads((target/name).read_text())==json.loads((original/name).read_text())
        for name in ('trades.csv','source_trade_comparison.csv'):
            pd.testing.assert_frame_equal(pd.read_csv(target/name),pd.read_csv(original/name))
        for path in original.glob('*.csv.gz'):
            # Include empty coverage files; gzip wall-clock headers may differ.
            assert gzip.decompress(path.read_bytes())==gzip.decompress((target/path.name).read_bytes())
        trades=pd.read_csv(target/'trades.csv')
        assert len(trades)==1 and trades.iloc[0].exit_ts.startswith('2026-09-29 09:27')
        assert trades.iloc[0].option_type==('CE' if candidate['candidate_id']=='bear' else 'PE')
        assert trades.iloc[0].exit_reason=='Target'
    for bars,before_bars,quotes,before_quotes in snapshots:
        pd.testing.assert_frame_equal(bars,before_bars)
        pd.testing.assert_frame_equal(quotes,before_quotes)


def test_shared_chunk_resume_skips_committed_candidates_and_restores_carried_position(tmp_path,monkeypatch):
    import json
    autonomous,candidates,loaded,_=autonomous_batch_fixture(tmp_path,monkeypatch)
    complete=autonomous.run(candidates[0],tmp_path)
    partial=autonomous.run(candidates[1],tmp_path,limit_blocks=1)
    before=json.loads((partial/'checkpoint.json').read_text())
    assert before['completed_blocks']==1 and before['position']['option_type']=='PE'
    complete_checkpoint=(complete/'checkpoint.json').read_bytes()
    # An uncommitted output overwrite must not become the resumed trade history.
    (partial/'trades.csv').write_text('corrupt uncommitted output')
    loaded.clear()
    autonomous.run_batch(candidates,tmp_path)
    assert loaded==[date(2026,9,29)]
    assert (complete/'checkpoint.json').read_bytes()==complete_checkpoint
    after=json.loads((partial/'checkpoint.json').read_text())
    assert after['completed_blocks']==2 and after['position'] is None
    trades=pd.read_csv(partial/'trades.csv')
    assert len(trades)==1 and trades.iloc[0].option_type=='PE'
    assert trades.iloc[0].entry_ts.startswith('2026-09-28 10:18')
    assert trades.iloc[0].exit_ts.startswith('2026-09-29 09:27')


def test_shared_chunk_resume_rejects_changed_candidate_before_loading(tmp_path,monkeypatch):
    import pytest
    autonomous,candidates,loaded,_=autonomous_batch_fixture(tmp_path,monkeypatch)
    autonomous.run(candidates[0],tmp_path,limit_blocks=1)
    loaded.clear()
    changed={**candidates[0],'recipe':{'threshold_comparison':'inclusive'}}
    with pytest.raises(ValueError,match='Checkpoint candidate/config changed'):
        autonomous.run_batch([changed,candidates[1]],tmp_path)
    assert loaded==[]


def test_fit_replay_score_counts_carried_entry_and_ignores_uncommitted_or_later_results(tmp_path,monkeypatch):
    import json
    autonomous,candidates,loaded,_=autonomous_batch_fixture(tmp_path,monkeypatch)
    target=autonomous.run(candidates[0],tmp_path,limit_blocks=1)
    cutoff=date(2026,9,28)
    expected=autonomous.fit_replay_score(target,cutoff)
    assert expected['fit_source_trades']==2
    assert expected['fit_actual_exact_entries']==1
    assert expected['fit_actual_entries']==1 and expected['fit_actual_extra_entries']==0
    (target/'trades.csv').write_text('uncommitted broken output')
    (target/'source_trade_comparison.csv').write_text('uncommitted broken comparison')
    assert autonomous.fit_replay_score(target,cutoff)==expected
    state_path=target/'checkpoint.json';state=json.loads(state_path.read_text())
    later=dict(state['position']);later['entry_ts']='2026-09-29T10:18:00+05:30';later['exit_ts']='2026-09-29T14:00:00+05:30'
    state['trades']=[later];state_path.write_text(json.dumps(state))
    source=autonomous.provider_trades();future=source.iloc[:1].copy()
    future['signal_id']='later';future['entry']=pd.Timestamp('2026-09-29 10:18',tz='Asia/Kolkata');future['entry_minute']=future.entry
    monkeypatch.setattr(autonomous,'provider_trades',lambda:pd.concat([source,future],ignore_index=True))
    assert autonomous.fit_replay_score(target,cutoff)==expected


def test_fit_replay_score_rejects_uncovered_cutoff(tmp_path,monkeypatch):
    import pytest
    autonomous,candidates,loaded,_=autonomous_batch_fixture(tmp_path,monkeypatch)
    target=autonomous.run(candidates[0],tmp_path,limit_blocks=1)
    with pytest.raises(ValueError,match='whole fit period'):
        autonomous.fit_replay_score(target,date(2026,9,29))


def test_no_target_research_control_preserves_entry_and_holds_below_default_target(tmp_path,monkeypatch):
    import json
    autonomous,candidates,loaded,_=autonomous_batch_fixture(tmp_path,monkeypatch)
    control=autonomous.run(candidates[0],tmp_path)
    disabled={**candidates[0],'candidate_id':'no_target','recipe':{'profit_target_mode':'disabled'}}
    (tmp_path/'candidate_no_target.npz').write_bytes((tmp_path/'candidate_bear.npz').read_bytes())
    target=autonomous.run(disabled,tmp_path)
    normal=pd.read_csv(control/'trades.csv').iloc[0];held=pd.read_csv(target/'trades.csv').iloc[0]
    for name in ('entry_ts','option_type','sell_strike','buy_strike','units','net_credit','stop_loss','scheduled_exit'):
        assert normal[name]==held[name]
    assert normal.exit_reason=='Target' and pd.isna(held.exit_ts) and pd.isna(held.target)
    state=json.loads((target/'checkpoint.json').read_text())
    assert state['position']['target'] is None and state['config']['target_spread_value']==10
    # A completed resume must preserve the disabled target and committed state.
    before=(target/'checkpoint.json').read_bytes()
    autonomous.run(disabled,tmp_path)
    assert (target/'checkpoint.json').read_bytes()==before


def test_no_target_research_control_still_exits_at_stop_loss(tmp_path,monkeypatch):
    autonomous,candidates,loaded,_=autonomous_batch_fixture(tmp_path,monkeypatch)
    history=autonomous.load_history
    def stressed(client,first,last,**kwargs):
        bars,quotes,conflicts=history(client,first,last,**kwargs)
        if first==date(2026,9,29):
            quotes=quotes.copy()
            quotes.loc[quotes.index.get_level_values('strike')==23000.,'ce_ltp']=200.
            quotes.loc[quotes.index.get_level_values('strike')==23400.,'ce_ltp']=20.
        return bars,quotes,conflicts
    monkeypatch.setattr(autonomous,'load_history',stressed)
    disabled={**candidates[0],'candidate_id':'no_target','recipe':{'profit_target_mode':'disabled'}}
    (tmp_path/'candidate_no_target.npz').write_bytes((tmp_path/'candidate_bear.npz').read_bytes())
    target=autonomous.run(disabled,tmp_path)
    trade=pd.read_csv(target/'trades.csv').iloc[0]
    assert trade.exit_reason=='Stop loss' and pd.isna(trade.target)


def test_no_target_research_control_still_exits_when_scheduled_time_arrives(tmp_path,monkeypatch):
    autonomous,candidates,loaded,_=autonomous_batch_fixture(tmp_path,monkeypatch)
    history=autonomous.load_history
    def later(client,first,last,**kwargs):
        bars,quotes,conflicts=history(client,first,last,**kwargs)
        if first==date(2026,9,29):
            delta=pd.Timedelta(hours=5,minutes=33)
            bars=bars.copy();bars.index=bars.index+delta
            quotes=quotes.reset_index();quotes.minute=quotes.minute+delta
            quotes=quotes.set_index(['minute','expiry','strike']).sort_index()
        return bars,quotes,conflicts
    monkeypatch.setattr(autonomous,'load_history',later)
    disabled={**candidates[0],'candidate_id':'no_target','recipe':{'profit_target_mode':'disabled'}}
    (tmp_path/'candidate_no_target.npz').write_bytes((tmp_path/'candidate_bear.npz').read_bytes())
    target=autonomous.run(disabled,tmp_path)
    trade=pd.read_csv(target/'trades.csv').iloc[0]
    assert trade.exit_reason=='Time exit' and trade.exit_ts.startswith('2026-09-29 15:00')
    assert pd.isna(trade.target)


def test_shared_chunk_settlement_failure_preserves_other_candidates_commit(tmp_path,monkeypatch):
    import json
    import pytest
    from types import SimpleNamespace
    autonomous,candidates,loaded,_=autonomous_batch_fixture(tmp_path,monkeypatch)
    real_replay=autonomous.DhanReplay
    class SettlementFailureReplay(real_replay):
        def run(self,**kwargs):
            # Force the guarded lookup only for the second candidate. Its
            # absence must stop the batch before it commits or loads chunk 2.
            if self._indicator_frame().alpha.iloc[0]>.8:
                self.settlement_loader(date(2026,9,22))
            return super().run(**kwargs)
    monkeypatch.setattr(autonomous,'DhanReplay',SettlementFailureReplay)
    monkeypatch.setattr(autonomous,'NSESettlementClient',lambda *args,**kwargs:SimpleNamespace(get=lambda expiry:None))
    with pytest.raises(RuntimeError,match='Official NSE settlement for 2026-09-22 is unavailable'):
        autonomous.run_batch(candidates,tmp_path)
    assert loaded==[date(2026,9,28)]
    checkpoint=tmp_path/'full_autonomous_bear_ledger'/'checkpoint.json'
    assert json.loads(checkpoint.read_text())['completed_blocks']==1
    assert not (tmp_path/'full_autonomous_bull_ledger'/'checkpoint.json').exists()
    assert not (tmp_path/'full_autonomous_bull_ledger'/'report.json').exists()


def test_exchange_transition_and_holiday_expiry():
    assert expiries_for(date(2025,8,28))==[date(2025,8,28),date(2025,9,2)]
    assert expiries_for(date(2025,8,29))==[date(2025,9,2),date(2025,9,9)]
    assert expiries_for(date(2026,10,16))[0]==date(2026,10,19)
    assert ProviderCalendar().is_trading_day(date(2026,2,1))
    assert not ProviderCalendar().is_trading_day(date(2026,10,2))
    assert lot_size(date(2025,12,29),date(2025,12,30))==75
    assert lot_size(date(2025,12,29),date(2026,1,6))==65


def test_historical_clock_is_opt_in_and_capped_at_expiry():
    cfg=StrategyConfig(); historical=history_config(cfg); calendar=ProviderCalendar()
    assert time_exit_due(ist(2026,6,24,10,15),date(2026,6,30),calendar,cfg)==ist(2026,6,25,14,53)
    assert time_exit_due(ist(2026,6,24,10,15),date(2026,6,30),calendar,historical)==ist(2026,6,25,15,0)
    assert time_exit_due(ist(2026,6,30,10,15),date(2026,6,30),calendar,historical)==ist(2026,6,30,15,0)
    assert time_exit_due(ist(2026,7,1,10,15),date(2026,7,7),calendar,historical)==ist(2026,7,2,14,53)
    assert historical.time_exit==cfg.time_exit


def test_future_mutation_cannot_change_baseline_entry_parameters():
    bars=session_bars([date(2026,9,23),date(2026,9,24),date(2026,9,25),date(2026,9,28)])
    cut=1300
    future=bars.copy()
    future.iloc[cut+1:]=future.iloc[cut+1:]*3
    np.testing.assert_allclose(calculate_alpha(bars).iloc[:cut+1],calculate_alpha(future).iloc[:cut+1],equal_nan=True)
    rng=np.random.default_rng(42)
    panel=pd.DataFrame({'ce_volume':rng.uniform(1,1000,len(bars)), 'pe_volume':rng.uniform(1,1000,len(bars)),
                        'ce_return':rng.normal(0,.01,len(bars)),'pe_return':rng.normal(0,.01,len(bars))},index=bars.index)
    pc=bars.close.pct_change(5,fill_method=None)
    changed=panel.copy();changed.iloc[cut+1:]*=4
    np.testing.assert_allclose(calculate_alpha2(pc,panel).iloc[:cut+1],calculate_alpha2(pc,changed).iloc[:cut+1],equal_nan=True)


def entry_view():
    now=ist(2026,9,24,10,30)
    bars=pd.DataFrame({'open':[23020.],'close':[23040.]},index=[pd.Timestamp(now)-pd.Timedelta(minutes=1)])
    expiry=date(2026,9,29)
    chain=make_chain(now,expiry,23040.)
    return MarketView(now,bars,None,chain,[expiry],65,indicators=(.1,.1))


def test_strike_uses_last_completed_open_instead_of_chain_spot():
    view=entry_view(); engine=StrategyEngine(StrategyConfig(strike_reference='last_bar_open'),ProviderCalendar())
    result=engine.evaluate(view,None)
    assert result.action=='entry'
    assert result.position.sell_strike==23000 and result.position.buy_strike==23400
    assert result.position.spot_at_entry==23040  # current spot is still reported honestly
    assert result.diagnostics['strike_reference_spot']==23020
    legacy=StrategyEngine(StrategyConfig(strike_reference='spot'),ProviderCalendar()).evaluate(view,None)
    assert legacy.position.sell_strike==23050


def test_premium_eligibility_blocks_high_quote_and_accepts_boundary():
    view=entry_view(); key=(23000.,'CE')
    view.chain.quotes[key]=replace(view.chain.quotes[key],ltp=200.05)
    engine=StrategyEngine(StrategyConfig(max_short_premium=200,strike_reference='last_bar_open'),ProviderCalendar())
    assert engine.evaluate(view,None).reason=='short premium above maximum'
    view.chain.quotes[key]=replace(view.chain.quotes[key],ltp=200.)
    assert engine.evaluate(view,None).action=='entry'


def test_missing_open_reference_quote_does_not_move_the_strike():
    from backtest.dhan_replay import DhanReplay
    from tests.test_dhan_replay import sample
    bars,quotes=sample()
    minute=bars.index[1]+pd.Timedelta(minutes=1)
    quotes=quotes.drop((minute,date(2024,1,4),22000.))
    replay=DhanReplay(StrategyConfig(strike_reference='last_bar_open'),bars,quotes)
    chain=replay._chain_at(minute,date(2024,1,4),22050.)
    assert chain.quote(22000.,'CE').ltp is None
