import numpy as np
import pandas as pd
from backtest.provider_fixed_factors import contract_factors


def _fixed_ohlc_test_series():
    index=pd.date_range('2025-07-01 09:16',periods=370,freq='min',tz='Asia/Kolkata')
    t=np.arange(370);series=pd.DataFrame(index=index)
    for side,o,body in (('ce',100.,.01*np.sin(t/7)),('pe',50.,.02*np.cos(t/9))):
        series[side+'_open']=o;series[side+'_high']=o*1.1;series[side+'_low']=o*.9
        series[side+'_close']=o*(1+body)
    series['ce_volume']=100+(t%7)*10.;series['pe_volume']=200+(t%11)*15.
    return series


def test_contract_ohlc108_factors_independent_numeric_own_volume_and_lag():
    from backtest.provider_fixed_factors import contract_ohlc_factors
    series=_fixed_ohlc_test_series();actual=contract_ohlc_factors(series)
    assert len(actual.columns)==108 and actual.index.equals(series.index)
    position=350
    for kind in ('intrabar_return_std','parkinson','garman_klass'):
        for window in (150,300):
            denominator=0.
            for side in ('ce','pe'):
                part=series.iloc[position-window+1:position+1]
                o,h,l,c=(part[f'{side}_{field}'].to_numpy() for field in ('open','high','low','close'))
                denominator+=np.std((c-o)/o,ddof=1) if kind=='intrabar_return_std' else np.sqrt(np.mean(
                    np.log(h/l)**2/(4*np.log(2)) if kind=='parkinson' else
                    .5*np.log(h/l)**2-(2*np.log(2)-1)*np.log(c/o)**2))
            for baseline in (10,15,20):
                history=series.iloc[position-baseline+1:position+1]
                ce=series.ce_volume.iloc[position]/np.mean(history.ce_volume)
                pe=series.pe_volume.iloc[position]/np.mean(history.pe_volume)
                multipliers={'native':(ce+pe)/2,'geometric_ratios':np.sqrt(ce*pe),
                    'total_ratio':(series.ce_volume.iloc[position]+series.pe_volume.iloc[position])/
                        np.mean(history.ce_volume+history.pe_volume)}
                for volume_kind,multiplier in multipliers.items():
                    name=f'fixed_ohlc_{kind}_{window}_{volume_kind}_b{baseline}_lag0'
                    assert np.isclose(actual[name].iloc[position],multiplier/denominator)
                    lagged=name.removesuffix('lag0')+'lag5'
                    pd.testing.assert_series_equal(actual[lagged],actual[name].shift(5),check_names=False)
    for stop in (100,210,351):
        pd.testing.assert_frame_equal(actual.iloc[:stop],contract_ohlc_factors(series.iloc[:stop]))


def test_contract_ohlc_unknown_clock_slots_invalid_quotes_and_overnight_gap_are_not_filled():
    from backtest.provider_fixed_factors import contract_ohlc_factors
    series=_fixed_ohlc_test_series();altered=series.copy()
    altered.iloc[320,altered.columns.get_loc('ce_volume')]=-1.
    altered.iloc[321,altered.columns.get_loc('ce_high')]=80.
    altered.iloc[322]=np.nan
    altered.iloc[323,altered.columns.get_loc('pe_volume')]=np.inf
    factors=contract_ohlc_factors(altered);columns=[c for c in factors if c.endswith('lag0')]
    assert factors.loc[altered.index[320:324],columns].isna().all().all()
    lagged=[c for c in factors if c.endswith('lag5')]
    assert factors.loc[altered.index[325:329],lagged].isna().all().all()
    pd.testing.assert_frame_equal(factors.iloc[:320],contract_ohlc_factors(series).iloc[:320])
    missing=series.copy();missing.iloc[100:150]=np.nan
    with_slots=contract_ohlc_factors(missing)
    assert with_slots.index.equals(series.index) and with_slots.iloc[149].isna().all()
    name='fixed_ohlc_parkinson_150_native_b10_lag0'
    assert np.isnan(with_slots[name].iloc[180])  # 50 unknown rows occupy150 clock slots.
    assert np.isfinite(contract_ohlc_factors(missing.dropna())[name].loc[series.index[180]])
    # OHLC estimators use within-candle changes, so an overnight premium jump
    # is not a spurious close-to-close return or a fabricated quote.
    jumped=series.copy();jumped.index=series.index[:200].append(
        pd.date_range('2025-07-02 09:16',periods=170,freq='min',tz='Asia/Kolkata'))
    price_columns=[c for c in series.columns if not c.endswith('volume')]
    jumped.loc[jumped.index[200]:,price_columns]*=10
    result=contract_ohlc_factors(jumped);baseline=contract_ohlc_factors(series)
    np.testing.assert_allclose(result.to_numpy(),baseline.to_numpy(),equal_nan=True)


def test_contract_ohlc_factors_reject_invalid_common_clock_or_missing_fields():
    import pytest
    from backtest.provider_fixed_factors import contract_ohlc_factors
    series=_fixed_ohlc_test_series()
    for invalid in (series.iloc[::-1],pd.concat([series,series.iloc[:1]]),series.reset_index(drop=True)):
        with pytest.raises(ValueError):contract_ohlc_factors(invalid)
    with pytest.raises(ValueError):contract_ohlc_factors(series.drop(columns='ce_open'))


def test_contract_ohlc_factor_overflow_remains_unknown_before_lag(monkeypatch):
    import backtest.provider_trials as trials
    from backtest.provider_fixed_factors import contract_ohlc_factors
    series=_fixed_ohlc_test_series()
    monkeypatch.setattr(trials,'opening_ohlc_volatility',lambda panel,kind,window:
        pd.Series(np.nextafter(0.,1.),index=panel.index))
    with np.errstate(over='ignore'):
        result=contract_ohlc_factors(series)
    assert not np.isinf(result.to_numpy()).any()
    assert result.isna().all().all()  # Positive but tiny denominator cannot create known infinite factors.


def test_fixed_contract_window_does_not_mix_other_strikes_or_fill_missing_quotes():
    idx=pd.date_range('2026-09-28 09:16',periods=50,freq='min',tz='Asia/Kolkata')
    p=pd.DataFrame({'ce_ltp':100+np.arange(50)*.1,'pe_ltp':80+np.arange(50)*.2,
        'ce_volume':np.arange(50)+10.,'pe_volume':np.arange(50)+20.},index=idx)
    actual=contract_factors(p)
    expected=(p.ce_volume.iloc[11:31].mean(),p.pe_volume.iloc[11:31].mean())
    assert actual.fixed_volume_ratio_1_20.iloc[30]==(p.ce_volume.iloc[30]/expected[0]+p.pe_volume.iloc[30]/expected[1])/2
    assert np.isclose(actual.fixed_price_std_20.iloc[30],p.ce_ltp.iloc[11:31].std()+p.pe_ltp.iloc[11:31].std())
    missing=p.copy();missing.loc[idx[25:30],['ce_ltp','pe_ltp','ce_volume','pe_volume']]=np.nan
    assert np.isnan(contract_factors(missing).fixed_volume_ratio_1_20.iloc[30])
    future=p.copy();future.loc[idx[40]:]=999999
    pd.testing.assert_frame_equal(actual.iloc[:40],contract_factors(future).iloc[:40])


def test_fixed_returns_exclude_overnight_jump():
    idx=pd.date_range('2026-09-28 15:10',periods=20,freq='min',tz='Asia/Kolkata').append(
        pd.date_range('2026-09-29 09:16',periods=20,freq='min',tz='Asia/Kolkata'))
    p=pd.DataFrame({'ce_ltp':[100.]*20+[200.]*20,'pe_ltp':[80.]*20+[150.]*20,
        'ce_volume':10.,'pe_volume':20.},index=idx)
    factors=contract_factors(p)
    assert factors.fixed_same_return_20.iloc[-1]==0.


def test_opening_atm_panel_uses_lower_tie_same_contract_and_no_future_prices():
    from backtest.provider_fixed_factors import opening_atm_features
    from backtest.provider_calendar import expiries_for
    idx=pd.date_range('2026-09-28 09:15',periods=3,freq='min',tz='Asia/Kolkata')
    bars=pd.DataFrame({'open':[23024.,23025.,23026.],'close':[23040.,23040.,23010.]},index=idx)
    minutes=idx+pd.Timedelta(minutes=1);expiries=expiries_for(idx[0].date())
    rows=[]
    for i,minute in enumerate(minutes):
        for expiry in expiries:
            for strike,base in ((23000.,100.),(23050.,200.)):
                rows.append({'minute':minute,'expiry':expiry,'strike':strike,'ce_ltp':base+i*10,
                    'pe_ltp':base*.8+i*5,'ce_volume':20+i,'pe_volume':30+i})
    quotes=pd.DataFrame(rows).set_index(['minute','expiry','strike'])
    result=opening_atm_features(bars,quotes)
    near=result.loc[result.expiry.eq(expiries[0])].reset_index(drop=True)
    assert near.atm_strike.tolist()==[23000.,23000.,23050.]
    assert np.isnan(near.ce_return.iloc[0])
    assert np.isclose(near.ce_return.iloc[2],220/210-1)  # previous SAME 23050, not previously selected 23000
    missing=quotes.drop((minutes[2],expiries[0],23050.))
    absent=opening_atm_features(bars,missing)
    assert absent.loc[absent.expiry.eq(expiries[0])].ce_ltp.isna().iloc[-1]
    future=bars.copy();future.iloc[2]=90000
    future_quotes=quotes.copy();future_quotes.loc[(minutes[2],slice(None),slice(None)),:]=99999
    changed=opening_atm_features(future,future_quotes)
    pd.testing.assert_frame_equal(result.loc[result.minute<minutes[2]].reset_index(drop=True),
        changed.loc[changed.minute<minutes[2]].reset_index(drop=True))


def cumulative_fixture():
    from backtest.provider_calendar import expiries_for
    idx=pd.date_range('2026-09-28 09:15',periods=3,freq='min',tz='Asia/Kolkata').append(
        pd.date_range('2026-09-29 09:15',periods=3,freq='min',tz='Asia/Kolkata'))
    bars=pd.DataFrame({'open':[23000.,23000.,23050.]*2},index=idx)
    rows=[]
    for i,minute in enumerate(idx+pd.Timedelta(minutes=1)):
        for expiry in expiries_for(minute.date()):
            for strike,scale in ((23000.,1.),(23050.,10.)):
                rows.append({'minute':minute,'expiry':expiry,'strike':strike,
                    'ce_volume':scale*(i%3),'pe_volume':scale*(i%3+1)})
    return bars,pd.DataFrame(rows).set_index(['minute','expiry','strike'])


def test_contract_cumulative_tracks_same_strike_resets_day_and_accepts_zero():
    from backtest.provider_fixed_factors import contract_cumulative_features
    bars,quotes=cumulative_fixture()
    result=contract_cumulative_features(bars,quotes)
    near=result.iloc[:len(bars)]
    assert near.ce_contract_cumulative_volume.tolist()==[0.,1.,30.,0.,1.,30.]
    assert near.pe_contract_cumulative_volume.tolist()==[1.,3.,60.,1.,3.,60.]
    assert near.ce_cumulative_prefix_complete.all()
    assert near.pe_cumulative_prefix_complete.all()


def test_contract_cumulative_missing_or_negative_prefix_remains_unknown_per_leg():
    from backtest.provider_fixed_factors import contract_cumulative_features
    bars,quotes=cumulative_fixture()
    key=quotes.index[quotes.index.get_level_values('strike')==23050.][0]
    invalid=quotes.copy();invalid.loc[key,'ce_volume']=-1
    result=contract_cumulative_features(bars,invalid)
    assert np.isnan(result.ce_contract_cumulative_volume.iloc[2])
    assert not result.ce_cumulative_prefix_complete.iloc[2]
    assert result.pe_contract_cumulative_volume.iloc[2]==60.
    assert result.ce_contract_cumulative_volume.iloc[5]==30.
    missing=contract_cumulative_features(bars,quotes.drop(key))
    assert np.isnan(missing.ce_contract_cumulative_volume.iloc[2])
    assert np.isnan(missing.pe_contract_cumulative_volume.iloc[2])


def test_contract_cumulative_future_changes_cannot_change_earlier_prefixes():
    from backtest.provider_fixed_factors import contract_cumulative_features
    bars,quotes=cumulative_fixture()
    actual=contract_cumulative_features(bars,quotes)
    cutoff=bars.index[2]+pd.Timedelta(minutes=1)
    changed=quotes.copy();changed.loc[changed.index.get_level_values('minute')>=cutoff,:]=999999.
    future=contract_cumulative_features(bars,changed)
    pd.testing.assert_frame_equal(actual.loc[actual.minute<cutoff].reset_index(drop=True),
        future.loc[future.minute<cutoff].reset_index(drop=True))
