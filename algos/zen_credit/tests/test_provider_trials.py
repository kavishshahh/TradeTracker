"""Trial price alignment, causal provisional ranks and checkpoint integrity."""
import csv
import numpy as np
import pandas as pd
from backtest.provider_trials import provisional_rank,price_change_series,repair_trial_schema,sampled_rank


def test_hysteresis_gate_arming_release_missing_session_and_prefix():
    from backtest.provider_price_bounds import hysteresis_rank_gate
    index=pd.date_range('2026-09-28 10:00',periods=10,freq='min',tz='Asia/Kolkata')
    raw=pd.Series([.8,.81,.7,.51,.5,.19,.3,.49,np.nan,.3],index=index)
    actual=hysteresis_rank_gate(raw,.5)
    np.testing.assert_equal(actual.state.to_numpy(),[0,1,1,1,0,-1,-1,-1,0,0])
    assert actual.arm_index.iloc[3]==1 and actual.armed_rank.iloc[3]==.81
    assert pd.isna(actual.gate.iloc[8]) and actual.arm_index.iloc[9]==-1
    pd.testing.assert_frame_equal(actual.iloc[:7],hysteresis_rank_gate(raw.iloc[:7],.5))
    changed=raw.copy();changed.iloc[7:]=.99
    pd.testing.assert_frame_equal(actual.iloc[:7],hysteresis_rank_gate(changed,.5).iloc[:7])
    boundary=pd.Series([.81,.6],index=pd.DatetimeIndex(['2026-09-28 15:30','2026-09-29 09:16'],tz='Asia/Kolkata'))
    assert hysteresis_rank_gate(boundary,.5,False).state.iloc[1]==1
    assert hysteresis_rank_gate(boundary,.5,True).state.iloc[1]==0


def test_complete_case_rank_compresses_only_accepted_rows_without_stale_values():
    from backtest.provider_price_bounds import complete_case_rank
    index=pd.date_range('2026-09-28 10:00',periods=8,freq='min',tz='Asia/Kolkata')
    raw=pd.Series([3.,100.,2.,100.,1.,4.,np.nan,2.],index=index)
    available=pd.Series([True,False,True,False,True,True,True,True],index=index)
    for weighted in (False,True):
        assert complete_case_rank(raw,pd.Series(False,index=index),3,weighted).isna().all()
        actual=complete_case_rank(raw,available,3,weighted)
        assert actual.iloc[[1,3,6]].isna().all()
        assert pd.notna(actual.iloc[4])
        pd.testing.assert_series_equal(actual.iloc[:6],complete_case_rank(raw.iloc[:6],available.iloc[:6],3,weighted))
        changed=raw.copy();changed.iloc[6:]=999.
        pd.testing.assert_series_equal(actual.iloc[:6],complete_case_rank(changed,available,3,weighted).iloc[:6])
    assert complete_case_rank(raw,available,3).iloc[4]==1/3


def test_return_innovation_excludes_current_preserves_missing_and_prefix():
    from backtest.provider_price_bounds import trailing_return_innovation
    index=pd.date_range('2026-09-28 10:00',periods=8,freq='min',tz='Asia/Kolkata')
    series=pd.Series([1.,2.,9.,4.,8.,3.,7.,6.],index=index)
    expected={'mean':4.-(1.+2.+9.)/3.,'median':4.-2.}
    for kind,value in expected.items():
        actual=trailing_return_innovation(series,3,kind,1)
        np.testing.assert_allclose(actual.iloc[3],value)
        pd.testing.assert_series_equal(actual.iloc[:6],trailing_return_innovation(series.iloc[:6],3,kind,1))
        changed=series.copy();changed.iloc[6:]=1000.
        pd.testing.assert_series_equal(actual.iloc[:6],trailing_return_innovation(changed,3,kind,1).iloc[:6])
        missing=series.copy();missing.iloc[2]=np.nan
        assert trailing_return_innovation(missing,3,kind,1).iloc[2:6].isna().all()


def test_weighted_rank_uniform_ties_missing_age_and_causal_prefix():
    from backtest.provider_price_bounds import weighted_observation_rank
    index=pd.date_range('2026-09-28 10:00',periods=9,freq='min',tz='Asia/Kolkata')
    series=pd.Series([3.,3.,2.,2.,np.nan,4.,1.,2.,3.],index=index)
    uniform=weighted_observation_rank(series,4,'uniform',minimum=3)
    pd.testing.assert_series_equal(uniform,series.rolling(4,min_periods=3).rank(method='average',pct=True))
    linear=weighted_observation_rank(series,4,'linear',minimum=3)
    assert linear.iloc[3]==.55
    # Row4 is unknown and keeps weight2 in this window; weights do not compact.
    assert linear.iloc[6]==4/8
    assert pd.isna(linear.iloc[4])
    for kind,half_life in [('linear',None),('exponential',2.)]:
        full=weighted_observation_rank(series,4,kind,half_life,3)
        pd.testing.assert_series_equal(full.iloc[:7],weighted_observation_rank(series.iloc[:7],4,kind,half_life,3))
        changed=series.copy();changed.iloc[7:]*=-20
        pd.testing.assert_series_equal(full.iloc[:7],weighted_observation_rank(changed,4,kind,half_life,3).iloc[:7])


def test_completed_body_return_excludes_opening_gaps_and_is_causal():
    from backtest.provider_price_bounds import completed_body_return
    index=pd.date_range('2026-09-28 10:00',periods=7,freq='min',tz='Asia/Kolkata')
    opening=np.array([100.,110.,120.,130.,140.,150.,160.]);close=opening+1
    bars=pd.DataFrame({'open':opening,'close':close},index=index)
    expected={'body_points':5/120.,'body_fraction':sum(1/opening[-5:]),
              'body_log_compound':np.prod(close[-5:]/opening[-5:])-1}
    # Endpoint includes large gaps; body sum contains exactly five +1 moves.
    assert (close[-1]-opening[-5])/opening[-5]>expected['body_points']
    for kind,value in expected.items():
        result=completed_body_return(bars,kind,5)
        np.testing.assert_allclose(result.iloc[-1],value)
        pd.testing.assert_series_equal(result.iloc[:6],completed_body_return(bars.iloc[:6],kind,5))
        changed=bars.copy();changed.iloc[6]*=9
        pd.testing.assert_series_equal(result.iloc[:6],completed_body_return(changed,kind,5).iloc[:6])
        missing=bars.copy();missing.loc[index[4],'close']=np.nan
        assert completed_body_return(missing,kind,5).iloc[4:].isna().all()


def test_volatility_definitions_sample_units_prefix_and_missing_coverage():
    from backtest.provider_trials import volatility_definition_panel
    index=pd.date_range('2026-09-28 10:00',periods=6,freq='min',tz='Asia/Kolkata')
    x=np.array([.01,-.03,.02,.04,-.01,.05])
    panel=pd.DataFrame({'ce_return':np.expm1(x),'pe_return':np.expm1(2*x),
        'ce_ltp':[100.,120.,90.,130.,110.,140.],
        'pe_ltp':[80.,100.,70.,120.,90.,130.]},index=index)
    scales=volatility_definition_panel(panel,5)
    assert len(scales)==8
    sample=x[-5:];variance=np.var(sample,ddof=1)
    np.testing.assert_allclose(scales['return_std_sum'].iloc[-1],3*np.sqrt(variance))
    np.testing.assert_allclose(scales['return_variance_sum'].iloc[-1],5*variance)
    np.testing.assert_allclose(scales['root_sum_return_variances'].iloc[-1],np.sqrt(5*variance))
    np.testing.assert_allclose(scales['return_rms_sum'].iloc[-1],3*np.sqrt(np.mean(sample**2)))
    np.testing.assert_allclose(scales['return_mean_abs_sum'].iloc[-1],3*np.mean(abs(sample)))
    prices=[panel[f'{side}_ltp'].to_numpy()[-5:] for side in ('ce','pe')]
    np.testing.assert_allclose(scales['price_std_sum'].iloc[-1],sum(np.std(p,ddof=1) for p in prices))
    np.testing.assert_allclose(scales['price_cv_sum'].iloc[-1],sum(np.std(p,ddof=1)/np.mean(p) for p in prices))
    np.testing.assert_allclose(scales['log_price_std_sum'].iloc[-1],sum(np.std(np.log(p),ddof=1) for p in prices))
    prefix=volatility_definition_panel(panel.iloc[:5],5)
    changed=panel.copy();changed.iloc[5]*=10
    perturbed=volatility_definition_panel(changed,5)
    for name in scales:
        pd.testing.assert_series_equal(scales[name].iloc[:5],prefix[name])
        pd.testing.assert_series_equal(scales[name].iloc[:5],perturbed[name].iloc[:5])
    absent=panel.copy();absent.iloc[2:5]=np.nan
    assert all(pd.isna(s.iloc[4]) for s in volatility_definition_panel(absent,5).values())


def test_performance_ledger_handles_all_open_positions_and_inclusive_ist_dates():
    from backtest.provider_autonomous import performance_ledger
    frame=pd.DataFrame({'entry_ts':[
        '2026-01-01T00:00:00+05:30','2026-01-31T23:59:59+05:30',
        '2026-02-01T00:00:00+05:30'],
        'exit_ts':[None,None,None], 'exit_observed_ts':[None,None,None],
        'pnl':[None,None,None]})
    result=performance_ledger(frame,'2026-01-01','2026-01-31')
    assert len(result)==2
    assert result.exit_ts.isna().all() and result.pnl.isna().all()
    assert performance_ledger(frame.iloc[:0],'2026-01-01','2026-01-31').empty


def test_performance_ledger_censors_settlement_not_observed_until_next_session():
    from backtest.provider_autonomous import performance_ledger
    from backtest.metrics import compute_period_performance
    frame=pd.DataFrame({'entry_ts':['2026-03-18T14:08:00+05:30'],
        'exit_ts':['2026-03-24T15:30:00+05:30'],
        'exit_observed_ts':['2026-03-25T09:16:00+05:30'],'pnl':[44768.75]})
    before=performance_ledger(frame,'2026-03-01','2026-03-24')
    assert before.exit_ts.isna().all() and before.pnl.isna().all()
    assert compute_period_performance(before,320000,'2026-03-01','2026-03-24')['open_trade_count']==1
    after=performance_ledger(frame,'2026-03-01','2026-03-25')
    assert after.pnl.sum()==44768.75


def test_performance_ledger_censors_future_exits_and_recovers_unmarked_carried_position():
    from backtest.provider_autonomous import performance_ledger
    from backtest.metrics import compute_period_performance
    frame=pd.DataFrame({'entry_ts':['2026-01-02T10:20:00+05:30','2026-01-03T10:20:00+05:30',
        '2026-02-02T10:20:00+05:30','2026-01-04T10:20:00+05:30'],
        'exit_ts':['2026-01-02T14:00:00+05:30','2026-02-03T14:00:00+05:30',
                   '2026-02-03T14:00:00+05:30','NaT'],
        'pnl':[100.,99999.,99999.,None],'unrealized_pnl':[None,99999.,99999.,None],
        'valuation_ts':[None,'2026-02-03T15:30:00+05:30','2026-02-03T15:30:00+05:30',None]})
    carried={'entry_ts':'2026-01-05T10:20:00+05:30'}
    ledger=performance_ledger(frame,'2026-01-01','2026-01-31',carried)
    result=compute_period_performance(ledger,320000,'2026-01-01','2026-01-31')
    assert result['total_pnl']==100. and result['trade_count']==1
    assert result['open_trade_count']==3 and result['open_mtm_pnl'] is None
    assert len(ledger)==4
    # An existing open entry is never duplicated by the carried-position record.
    assert len(performance_ledger(ledger,'2026-01-01','2026-01-31',carried))==4


def test_trial_performance_report_uses_common_dates_reported_zen_pnl_and_zero_months(tmp_path):
    import json
    from backtest.provider_autonomous import write_trial_performance
    trial=pd.DataFrame({'entry_ts':['2026-01-02T10:20:00+05:30'],
        'exit_ts':['2026-01-03T14:00:00+05:30'],'pnl':[100.]})
    source=pd.DataFrame({'entry':['2026-01-02T10:20:00+05:30','2025-12-31T10:20:00+05:30'],
        'exit':['2026-01-03T14:00:00+05:30','2026-01-02T14:00:00+05:30'],
        'pnl_reported':[50.,999.],'pnl_calculated':[800.,999.]})
    payload=write_trial_performance(tmp_path,trial,320000,'2026-01-01','2026-02-28',source=source)
    assert payload['performance']['total_pnl']==100.
    assert payload['zen_same_period']['total_pnl']==50.
    monthly=pd.read_csv(tmp_path/'performance_monthly.csv')
    assert monthly.pnl.tolist()==[100.,0.] and monthly.zen_pnl.tolist()==[50.,0.]
    assert monthly.excess_pnl_vs_zen.tolist()==[50.,0.]
    assert json.loads((tmp_path/'performance.json').read_text())['performance']['return_3m_pct'] is None


def test_ordinary_replay_performance_keeps_gross_fees_and_open_mtm_separate(tmp_path):
    from backtest.dhan_replay import write_replay_performance
    trades=pd.DataFrame({'entry_ts':['2026-01-02T10:20:00+05:30','2026-01-30T10:20:00+05:30'],
        'exit_ts':['2026-01-03T14:00:00+05:30','NaT'],'pnl':[20.,None],
        'pnl_after_modeled_fees':[-30.,None],'unrealized_pnl':[None,50.],
        'valuation_ts':[None,'2026-01-31T15:30:00+05:30']})
    result=write_replay_performance(tmp_path,trades,320000,'2026-01-01','2026-01-31')
    gross=result['gross_realized'];net=result['after_modeled_order_fees']
    assert gross['total_pnl']==20. and gross['win_rate_pct']==100.
    assert net['total_pnl']==-30. and net['win_rate_pct']==0.
    assert gross['open_mtm_pnl']==net['open_mtm_pnl']==50.
    assert gross['trade_count']==net['trade_count']==1
    monthly=pd.read_csv(tmp_path/'performance_monthly.csv')
    assert monthly.pnl.tolist()==[20.] and monthly.pnl_after_modeled_fees.tolist()==[-30.]


def test_period_performance_known_months_calendar_windows_cagr_and_realized_drawdown():
    import math,pytest,json
    from backtest.metrics import compute_period_performance
    # Leap-year boundaries: 1m lower Feb29, 3m lower Dec31, 6m lower Sep30.
    trades=pd.DataFrame({'exit_ts':['2023-10-01 10:00','2023-12-31 10:00','2024-01-01 10:00',
        '2024-02-29 10:00','2024-03-01 10:00','2024-03-31 10:00','2024-03-31 14:00'],
        'pnl':[3200.,-1600.,6400.,-3200.,3200.,0.,-1600.]})
    result=compute_period_performance(trades,320000,'2023-10-01','2024-03-31')
    assert result['observation_days']==183
    assert result['trade_count']==7 and result['winning_trades']==3
    assert result['losing_trades']==3 and result['breakeven_trades']==1
    assert result['win_rate_pct']==pytest.approx(300/7)
    assert result['total_pnl']==6400. and result['total_return_pct']==2.
    assert result['profit_factor']==2. and result['max_drawdown_rupees']==3200.
    assert result['max_drawdown_pct']==-1.
    assert result['cagr_pct']==pytest.approx(100*((1.02)**(365.25/183)-1))
    monthly=result['monthly'];assert [r['month'] for r in monthly]==['2023-10','2023-11','2023-12','2024-01','2024-02','2024-03']
    assert [r['pnl_rupees'] for r in monthly]==[3200.,0.,-1600.,6400.,-3200.,1600.]
    assert monthly[1]['trade_count']==0 and monthly[1]['win_rate_pct']==0.
    assert not any(r['partial_month'] for r in monthly)
    assert result['trailing']['1m']['total_pnl']==1600.
    assert result['trailing']['3m']['total_pnl']==4800.
    assert result['trailing']['6m']['total_pnl']==6400.
    assert all(w['available'] for w in result['trailing'].values())
    assert result['trailing']['1m']['lower_date_exclusive']=='2024-02-29'
    json.dumps(result,allow_nan=False)
    # Sparse trading cannot shorten the supplied observation duration.
    sparse=pd.DataFrame({'exit_ts':['2024-06-10 10:00'],'pnl':[32000.]})
    full_year=compute_period_performance(sparse,320000,'2024-01-01','2024-12-31')
    assert full_year['observation_days']==366
    assert full_year['cagr_pct']==pytest.approx(100*(1.1**(365.25/366)-1))
    assert full_year['profit_factor'] is None and full_year['profit_factor_status']=='no_losses'


def test_period_performance_ist_inclusive_bounds_partial_empty_open_and_short_observation():
    import pytest
    from backtest.metrics import compute_period_performance
    frame=pd.DataFrame({'exit_ts':['2024-03-14 18:30:00+00:00','2024-03-31 18:29:59+00:00',None],
        'pnl':[3200.,-1600.,float('nan')],'unrealized_pnl':[None,None,500.],
        'valuation_ts':[None,None,'2024-03-31 15:30:00+05:30']})
    result=compute_period_performance(frame,320000,'2024-03-15','2024-03-31')
    assert result['observation_days']==17 and result['trade_count']==2
    assert result['open_trade_count']==1 and result['open_mtm_pnl']==500.
    assert result['total_pnl']==1600. and result['ending_realized_value']==321600.
    assert result['monthly'][0]['partial_month']
    assert not any(w['available'] for w in result['trailing'].values())
    assert all(w['total_pnl'] is None for w in result['trailing'].values())
    frame.loc[2,'valuation_ts']='2024-03-30 15:30'
    stale=compute_period_performance(frame,320000,'2024-03-15','2024-03-31')
    assert stale['open_mtm_pnl'] is None and stale['open_mtm_known_trade_count']==0
    frame.loc[2,'valuation_ts']='2024-04-01 15:30'
    assert compute_period_performance(frame,320000,'2024-03-15','2024-03-31')['open_mtm_pnl'] is None
    empty=compute_period_performance(pd.DataFrame(),320000,'2024-01-15','2024-03-31')
    assert empty['trade_count']==0 and empty['total_pnl']==0. and empty['cagr_pct']==0.
    assert empty['max_drawdown_rupees']==0. and empty['open_mtm_pnl']==0.
    assert len(empty['monthly'])==3 and empty['monthly'][0]['partial_month']
    # Exactly observed dates Feb1..Mar31 cover the leap-date 1m window fully.
    assert compute_period_performance(pd.DataFrame(),320000,'2024-03-01','2024-03-31')['trailing']['1m']['available']
    # Same-timestamp net exits avoid an arbitrary intra-timestamp loss ordering.
    paired=pd.DataFrame({'exit_ts':['2024-03-15 10:00']*2,'pnl':[-100.,100.]})
    assert compute_period_performance(paired,320000,'2024-03-15','2024-03-31')['max_drawdown_rupees']==0.


def test_period_performance_rejects_invalid_closed_data_bounds_capital_and_nonpositive_equity():
    import pytest
    from backtest.metrics import compute_period_performance
    good=pd.DataFrame({'exit_ts':['2024-03-15 10:00'],'pnl':[100.]})
    for capital in (0.,-1.,float('nan'),float('inf'),'bad'):
        with pytest.raises(ValueError):compute_period_performance(good,capital,'2024-03-01','2024-03-31')
    for start,end in ((None,'2024-03-31'),('bad','2024-03-31'),('2024-04-01','2024-03-31')):
        with pytest.raises(ValueError):compute_period_performance(good,320000,start,end)
    for pnl in (None,'bad',float('inf')):
        bad=good.copy();bad['pnl']=pnl
        with pytest.raises(ValueError,match='P&L'):compute_period_performance(bad,320000,'2024-03-01','2024-03-31')
    for exit_value in ('bad','2024-02-29 23:59','2024-04-01 00:00'):
        bad=good.copy();bad['exit_ts']=exit_value
        with pytest.raises(ValueError):compute_period_performance(bad,320000,'2024-03-01','2024-03-31')
    with pytest.raises(ValueError):compute_period_performance(good.drop(columns='pnl'),320000,'2024-03-01','2024-03-31')
    bankrupt=good.copy();bankrupt['pnl']=-320000.
    result=compute_period_performance(bankrupt,320000,'2024-03-01','2024-03-31')
    assert result['cagr_pct']==-100. and result['cagr_status']=='defined'
    assert result['profit_factor']==0. and result['max_drawdown_pct']==-100.
    bankrupt['pnl']=-320001.
    result=compute_period_performance(bankrupt,320000,'2024-03-01','2024-03-31')
    assert result['cagr_pct'] is None and result['cagr_status']=='negative_ending_value'
    huge=good.copy();huge['pnl']=1e100
    assert compute_period_performance(huge,320000,'2024-03-15','2024-03-15')['cagr_status']=='numerical_overflow'


def test_exponential_sample_std_exact_weight_ages_missing_policy_and_prefix():
    import pytest
    from backtest.provider_trials import exponential_sample_std
    idx=pd.date_range('2025-07-01',periods=220,freq='min',tz='Asia/Kolkata')
    values=pd.Series(np.sin(np.arange(220)/7)*.03,index=idx)
    values.iloc[[15,80,150]]=np.nan
    actual=exponential_sample_std(values)
    for end in (119,149,150,180,219):
        sample=values.iloc[max(0,end-149):end+1].to_numpy()
        good=np.isfinite(sample);w=(149/151)**np.arange(len(sample)-1,-1,-1)
        if good.sum()<120:assert np.isnan(actual.iloc[end]);continue
        x=sample[good];w=w[good];mean=np.sum(w*x)/np.sum(w)
        expected=np.sqrt(np.sum(w*(x-mean)**2)/(np.sum(w)-np.sum(w*w)/np.sum(w)))
        assert actual.iloc[end]==pytest.approx(expected,rel=1e-14)
    # Current missing return follows the exact uniform control's omission policy.
    assert np.isfinite(actual.iloc[150])
    changed=values.copy();changed.iloc[180:]=1000.
    pd.testing.assert_series_equal(actual.iloc[:180],exponential_sample_std(changed).iloc[:180])
    # Finite slots retain ages; dropping a hole would shift historical weights.
    compact=exponential_sample_std(values.dropna()).reindex(idx)
    assert not np.isclose(actual.iloc[180],compact.iloc[180],rtol=1e-8)
    contaminated=values.copy();contaminated.iloc[151]=np.inf
    assert np.isfinite(exponential_sample_std(contaminated).iloc[151])
    all_unknown=pd.Series([np.nan]*200)
    assert exponential_sample_std(all_unknown).isna().all()
    stable=pd.Series(1e300*(1+np.sin(np.arange(160))*.01))
    assert np.isfinite(exponential_sample_std(stable).iloc[-1])
    assert exponential_sample_std(pd.Series([2.]*160)).iloc[-1]==0.
    with pytest.raises(ValueError):exponential_sample_std(values,150,151)


def test_weighted_components_changes_only_denominator_and_preserves_lag_and_unknown_volume():
    import backtest.provider_trials as t
    idx=pd.date_range('2025-07-01 09:15',periods=550,freq='min',tz='Asia/Kolkata')
    bars=pd.DataFrame({'open':25000.+np.arange(550)*.1,'close':25000.+np.sin(np.arange(550)/7)},index=idx)
    panel=pd.DataFrame({'ce_native_volume':100.+np.arange(550)%17,'pe_native_volume':200.+np.arange(550)%19,
        'ce_return':np.sin(np.arange(550)/7)*.01,'pe_return':np.cos(np.arange(550)/11)*.02},index=idx)
    panel.loc[idx[180],'ce_return']=np.nan;panel.loc[idx[200],'pe_native_volume']=np.nan
    recipe={'context':'continuous_near','volume_kind':'geometric_ratios','volume_short':1,'volume_baseline':10,
        'volatility':'log_return_150','factor_lag':5,'rank_window':300,'atm_reference':'last_completed_bar_open','profit_target_mode':'disabled'}
    alpha_recipe={'kind':'close_old_open','horizon':5,'rank_window':800}
    uniform=t.continuous_native_components(bars,panel,recipe,alpha_recipe)
    weighted=t.weighted_volatility_components(bars,panel,recipe,alpha_recipe)
    for key in ('volume_ratio_lagged','ce_volume_ratio_lagged','pe_volume_ratio_lagged','price_change'):
        pd.testing.assert_series_equal(uniform[key],weighted[key])
    sigma=t.exponential_sample_std(np.log1p(panel.ce_return))+t.exponential_sample_std(np.log1p(panel.pe_return))
    np.testing.assert_allclose(weighted.atm_volatility_lagged,sigma.shift(5),rtol=0,atol=0,equal_nan=True)
    assert np.isfinite(weighted.atm_volatility_lagged.iloc[185])
    assert np.isnan(weighted.raw2.iloc[205]) and np.isnan(weighted.alpha2.iloc[205])
    altered=panel.copy();altered.iloc[450:]=999.
    pd.testing.assert_frame_equal(weighted.iloc[:450],t.weighted_volatility_components(bars,altered,recipe,alpha_recipe).iloc[:450])


def test_weighted_screen_two_archives_order_exact_reference_gate_and_cli(tmp_path,monkeypatch):
    import json,pytest,sys
    import backtest.provider_trials as t
    root=tmp_path/'replication_trials';bulk=root/'bulk';bulk.mkdir(parents=True)
    reference='95fefedfcf057448';report=bulk/f'full_autonomous_{reference}_ledger';report.mkdir()
    idx=pd.date_range('2025-07-01 09:15',periods=550,freq='min',tz='Asia/Kolkata')
    bars=pd.DataFrame({'open':25000.+np.arange(550)*.1,'close':25000.+np.sin(np.arange(550)/7)},index=idx)
    panel=pd.DataFrame({'ce_native_volume':100.+np.arange(550)%17,'pe_native_volume':200.+np.arange(550)%19,
        'ce_return':np.sin(np.arange(550)/7)*.01,'pe_return':np.cos(np.arange(550)/11)*.02},index=idx)
    recipe={'context':'continuous_near','volume_kind':'geometric_ratios','volume_short':1,'volume_baseline':10,
        'volatility':'log_return_150','factor_lag':5,'rank_window':300,'atm_reference':'last_completed_bar_open','profit_target_mode':'disabled'}
    ar={'kind':'close_old_open','horizon':5,'rank_window':800};name='close_old_open_h5_r800'
    seed={'candidate_id':reference,'alpha':name,'alpha_recipe':ar,'recipe':recipe}
    (report/'report.json').write_text(json.dumps({'candidate':seed}))
    alpha=pd.Series(.9,index=idx);uniform=t.continuous_native_components(bars,panel,recipe,ar)
    archive=bulk/f'candidate_{reference}.npz'
    np.savez_compressed(archive,minutes=idx.as_unit('ns').asi8,alpha=alpha.to_numpy(),alpha2=uniform.alpha2.to_numpy())
    monkeypatch.setattr(t,'OUTPUT',tmp_path);monkeypatch.setattr(t,'context',lambda:(bars,None,None))
    monkeypatch.setattr(t,'load_alpha',lambda directory:{name:alpha})
    monkeypatch.setattr(t,'factor_contexts',lambda bars,opening:{'continuous_near':(panel,None)})
    class FakeScorer:
        def __init__(self,index):
            self.entries=np.array([180,500]);self.trades=pd.DataFrame({'signal_id':['a','b'],'entry':index[self.entries],
                'option_type':['PE','CE'],'direction':[1,-1]})
        def score(self,a,b):return {'fit_first_exact':1,'fit_direction_matches':2,'fit_signal_episodes':3},None
    monkeypatch.setattr(t,'Scorer',FakeScorer)
    t.weighted_volatility_screen();target=root/'weighted_volatility'
    frontier=json.loads((target/'frontier.json').read_text())
    assert [f['matched_role'] for f in frontier]==['weighted','uniform_control']
    assert len(list(target.glob('candidate_*.npz')))==2
    assert all(f['recipe']['profit_target_mode']=='disabled' for f in frontier)
    with np.load(target/f'candidate_{frontier[1]["candidate_id"]}.npz') as control:
        np.testing.assert_array_equal(control['alpha2'],uniform.alpha2)
    diagnostics=pd.read_csv(target/'source_entry_diagnostics.csv')
    assert len(diagnostics)==2 and 'weighted_raw2' in diagnostics and 'uniform_raw2' in diagnostics
    # A one-ULP mismatch is fatal, never silently normalized or tolerated.
    changed=uniform.alpha2.to_numpy().copy();last=np.flatnonzero(np.isfinite(changed))[-1]
    changed[last]=np.nextafter(changed[last],np.inf)
    np.savez_compressed(archive,minutes=idx.as_unit('ns').asi8,alpha=alpha.to_numpy(),alpha2=changed)
    with pytest.raises(ValueError,match='Unexplained reference control mismatch: alpha2'):t.weighted_volatility_screen()
    monkeypatch.setattr(sys,'argv',['provider_trials','--weighted-volatility-screen','--family','weighted_volatility'])
    with pytest.raises(SystemExit) as exc:t.main()
    assert exc.value.code==2


def test_opening_fixed_ohlc864_screen_exact_labels_final12_preapplied_lag_and_completion_gate(tmp_path,monkeypatch):
    import json,sys,pytest
    import backtest.provider_trials as trials
    import backtest.provider_fixed_factors as fixed
    import backtest.provider_price_bounds as bounds
    root=tmp_path/'replication_trials';root.mkdir()
    index=pd.date_range('2025-07-01 10:16',periods=30,freq='min',tz='Asia/Kolkata')
    bars=pd.DataFrame({'open':np.arange(30)+25000.,'close':np.arange(30)+25001.},index=index)
    labels=pd.concat([pd.DataFrame({'minute':index,'expiry':expiry,'atm_strike':25000.})
        for expiry in ('2025-07-03','2025-07-10')],ignore_index=True)
    names=('close_old_open_h5_r800','close_close_old_open_h5_r800')
    recipes={name:{'kind':name.split('_h5')[0],'horizon':5,'rank_window':800} for name in names}
    (root/'alpha_recipes.json').write_text(json.dumps(recipes))
    fields=labels.copy();columns={}
    for kind in ('intrabar_return_std','parkinson','garman_klass'):
        for window in (150,300):
            for volume in ('native','geometric_ratios','total_ratio'):
                for baseline in (10,15,20):
                    for lag in (0,5):
                        # Distinct lagged values already belong to current fixed
                        # contract; the screen must not shift them another5 rows.
                        columns[f'fixed_ohlc_{kind}_{window}_{volume}_b{baseline}_lag{lag}']=np.tile(np.arange(30)+1.+lag,2)
    fields=pd.concat([fields,pd.DataFrame(columns)],axis=1)
    first_column=next(iter(columns));fields.loc[20,first_column]=np.nan
    path=tmp_path/'factors.csv';fields.to_csv(path,index=False)
    monkeypatch.setattr(fixed,'OPENING_FIXED_OHLC_CACHE',path)
    monkeypatch.setattr(trials,'OUTPUT',tmp_path);monkeypatch.setattr(trials,'context',lambda:(bars,{},None))
    monkeypatch.setattr(trials,'load_alpha',lambda path:{name:pd.Series(.9,index=index) for name in names})
    monkeypatch.setattr(trials,'factor_contexts',lambda bars,opening:{'expiry_near':(labels,None)})
    calendar_calls=[]
    monkeypatch.setattr(bounds,'calendar_support_rank',lambda raw,closed_zero:calendar_calls.append(closed_zero) or raw)
    class FakeScorer:
        calls=0
        def __init__(self,index):
            self.entries=np.array([18,20,25]);self.trades=pd.DataFrame({'signal_id':['a','b','c'],
                'entry':index[self.entries],'option_type':['PE']*3,'direction':[1]*3})
        def score(self,a,b):
            FakeScorer.calls+=1
            return {'fit_first_exact':FakeScorer.calls,'fit_direction_matches':1,'fit_signal_episodes':1},None
    monkeypatch.setattr(trials,'Scorer',FakeScorer)
    seen=[];actual_rank=trials.selected_fixed_raw_ranks
    def rank(panel,clock,column):seen.append(panel.copy());return actual_rank(panel,clock,column)
    monkeypatch.setattr(trials,'selected_fixed_raw_ranks',rank)
    trials.opening_fixed_ohlc_screen()
    target=root/'opening_fixed_ohlc';design=json.loads((target/'search_design.json').read_text())
    assert FakeScorer.calls==864 and design['pairs']==864 and design['factor_columns']==108
    assert len(list(target.glob('candidate_*.npz')))==12 and len(pd.read_csv(target/'formula_trials.csv'))==864
    assert len(seen)==216 and calendar_calls==[True,True]
    # First spec lag0, then lag5; two rawrecipes per spec.
    expected=trials.price_change_series(bars,recipes[names[0]]).iloc[20]*(21.+5)
    assert np.isclose(seen[2].raw.iloc[20],expected)
    assert np.isnan(seen[0].raw.iloc[20])
    coverage=pd.read_csv(target/'source_factor_rank_coverage.csv')
    assert set(coverage.context)=={'continuous_near','expiry_near'}
    assert coverage.loc[coverage.factor_column.eq(first_column),'source_known_fixed_factor'].eq(2).all()
    assert coverage.source_known_rank.eq(0).all()  # No fake short window bypasses270 minimum.
    assert 'BEFORE selection' in design['factor_history'] and 'including next-expiry warmup' in design['rank_history']
    fields.iloc[:30].to_csv(path,index=False)
    with pytest.raises(ValueError,match='expected opening labels missing'):trials.opening_fixed_ohlc_screen()
    fields.to_csv(path,index=False)
    (tmp_path/'opening_fixed_ohlc_design.json').write_text(json.dumps({'complete':False}))
    with pytest.raises(ValueError,match='incomplete'):trials.opening_fixed_ohlc_screen()
    routed=[];monkeypatch.setattr(trials,'opening_fixed_ohlc_screen',lambda:routed.append(True))
    monkeypatch.setattr(sys,'argv',['provider_trials','--opening-fixed-ohlc-screen']);trials.main();assert routed==[True]
    monkeypatch.setattr(sys,'argv',['provider_trials','--opening-fixed-ohlc-screen','--opening-ohlc-screen'])
    with pytest.raises(SystemExit) as error:trials.main()
    assert error.value.code==2


def test_opening_option_ohlc_volatility_independent_numeric_prefix_and_current_validity():
    import pytest
    from backtest.provider_trials import opening_ohlc_volatility
    index=pd.date_range('2025-07-01 10:16',periods=10,freq='min',tz='Asia/Kolkata')
    panel=pd.DataFrame(index=index)
    for side,opening in (('ce',100.),('pe',50.)):
        panel[side+'_open']=opening;panel[side+'_high']=opening*1.2;panel[side+'_low']=opening*.8
        panel[side+'_close']=opening*(1+np.arange(10)*.01)
    panel.loc[index[5],'ce_high']=90.  # Invalid OHLC is unknown, not a zero range.
    panel.loc[index[7],'ce_low']=np.nan
    panel.loc[index[8],'pe_open']=0.
    panel.loc[index[9],'pe_high']=np.inf
    for kind in ('intrabar_return_std','parkinson','garman_klass'):
        actual=opening_ohlc_volatility(panel,kind,5);expected=[]
        for i in range(len(panel)):
            total=0.;current_valid=True
            for side in ('ce','pe'):
                samples=[]
                for j in range(max(0,i-4),i+1):
                    o,h,l,c=(float(panel[f'{side}_{field}'].iloc[j]) for field in ('open','high','low','close'))
                    valid=all(np.isfinite(v) and v>0 for v in (o,h,l,c)) and l<=min(o,c) and h>=max(o,c)
                    if j==i:current_valid=current_valid and valid
                    if valid:
                        samples.append((c-o)/o if kind=='intrabar_return_std' else
                            np.log(h/l)**2/(4*np.log(2)) if kind=='parkinson' else
                            .5*np.log(h/l)**2-(2*np.log(2)-1)*np.log(c/o)**2)
                total+=np.std(samples,ddof=1) if kind=='intrabar_return_std' and len(samples)>=4 else (
                    np.sqrt(np.mean(samples)) if len(samples)>=4 else np.nan)
            expected.append(total if current_valid else np.nan)
        np.testing.assert_allclose(actual,expected,equal_nan=True)
        for stop in (4,7,10):
            pd.testing.assert_series_equal(actual.iloc[:stop],opening_ohlc_volatility(panel.iloc[:stop],kind,5))
        assert actual.iloc[[5,7,8,9]].isna().all()
    for kind,window in (('unknown',5),('parkinson',1),('parkinson',True)):
        with pytest.raises(ValueError):opening_ohlc_volatility(panel,kind,window)


def test_opening_option_ohlc_exact_join_rejects_wrong_contract_and_preserves_volumes():
    import pytest
    from backtest.provider_trials import attach_exact_opening_ohlc
    index=pd.date_range('2025-07-01 10:16',periods=3,freq='min',tz='Asia/Kolkata')
    panel=pd.DataFrame({'expiry':['2025-07-03']*3,'atm_strike':[25000.]*3,
        'ce_native_volume':[1.,2.,3.],'pe_native_volume':[4.,5.,6.]},index=index)
    fields=pd.DataFrame({'minute':index,'expiry':['2025-07-03','2025-07-03','2025-07-10'],
        'atm_strike':[25000.,25050.,25000.],'ce_native_volume':[999.]*3})
    for side in ('ce','pe'):
        for field in ('open','high','low','close'):fields[f'{side}_{field}']=10.
    joined=attach_exact_opening_ohlc(panel,fields)
    assert joined.ce_open.iloc[0]==10. and joined.ce_open.iloc[1:].isna().all()
    np.testing.assert_array_equal(joined.ce_native_volume,panel.ce_native_volume)
    assert 'ce_open' not in panel
    with pytest.raises(pd.errors.MergeError):attach_exact_opening_ohlc(panel,pd.concat([fields,fields.iloc[:1]]))


def test_opening_option_ohlc_screen1134_pairs_final12_and_cli(tmp_path,monkeypatch):
    import json,sys,pytest
    import backtest.provider_trials as trials
    import backtest.provider_fixed_factors as fixed
    import backtest.provider_price_bounds as bounds
    root=tmp_path/'replication_trials';root.mkdir()
    index=pd.date_range('2025-07-01 10:16',periods=30,freq='min',tz='Asia/Kolkata')
    bars=pd.DataFrame({'open':np.arange(30)+25000.,'close':np.arange(30)+25001.},index=index)
    recipes={name:{'kind':name.split('_h5')[0],'horizon':5,'rank_window':800} for name in trials.BULK_ALPHAS}
    (root/'alpha_recipes.json').write_text(json.dumps(recipes))
    original=pd.DataFrame({'minute':index,'expiry':['2025-07-03']*30,'atm_strike':[25000.]*30,
        'ce_native_volume':np.arange(30)+1.,'pe_native_volume':np.arange(30)+2.},index=index)
    fields=original.reset_index(drop=True).copy()
    for side in ('ce','pe'):
        fields[side+'_open']=100.;fields[side+'_high']=110.;fields[side+'_low']=90.;fields[side+'_close']=105.
    fields.loc[2,'atm_strike']=25050.;fields.loc[4,'ce_high']=90.
    path=tmp_path/'fields.csv';fields.to_csv(path,index=False)
    monkeypatch.setattr(fixed,'OPENING_FULL_FIELDS_CACHE',path)
    monkeypatch.setattr(trials,'OUTPUT',tmp_path);monkeypatch.setattr(trials,'context',lambda:(bars,{},None))
    monkeypatch.setattr(trials,'load_alpha',lambda path:{name:pd.Series(.5,index=index) for name in trials.BULK_ALPHAS})
    monkeypatch.setattr(trials,'factor_contexts',lambda bars,opening:{'continuous_near':(original,None)})
    calendar_calls=[]
    monkeypatch.setattr(bounds,'calendar_support_rank',lambda raw,closed_zero:calendar_calls.append(closed_zero) or raw)
    class FakeScorer:
        calls=0
        def __init__(self,index):
            self.entries=np.array([0,2,4]);self.trades=pd.DataFrame({'signal_id':['a','b','c'],'entry':index[self.entries]})
        def score(self,a,b):
            FakeScorer.calls+=1
            return {'fit_first_exact':FakeScorer.calls,'fit_direction_matches':1,'fit_signal_episodes':1},None
    monkeypatch.setattr(trials,'Scorer',FakeScorer)
    trials.opening_ohlc_screen()
    target=root/'opening_ohlc_volatility';design=json.loads((target/'search_design.json').read_text())
    assert FakeScorer.calls==1134 and design['pairs']==1134
    assert len(pd.read_csv(target/'formula_trials.csv'))==1134 and len(list(target.glob('candidate_*.npz')))==12
    assert design['source_entries_both_current_ohlc_valid']==1 and calendar_calls==[True,True]
    assert 'not own-contract' in design['history_policy'] and 'assumes' in design['calendar_policy']
    assert pd.read_csv(target/'source_entry_ohlc_coverage.csv').both_current_ohlc_valid.sum()==1
    routed=[];monkeypatch.setattr(trials,'opening_ohlc_screen',lambda:routed.append(True))
    monkeypatch.setattr(sys,'argv',['provider_trials','--opening-ohlc-screen']);trials.main();assert routed==[True]
    monkeypatch.setattr(sys,'argv',['provider_trials','--opening-ohlc-screen','--iv-screen'])
    with pytest.raises(SystemExit) as error:trials.main()
    assert error.value.code==2


def test_full_opening_iv_screen_630_pairs_preserves_native_volumes_and_final12_archives(tmp_path,monkeypatch):
    import json
    import backtest.provider_trials as trials
    import backtest.provider_fixed_factors as fixed
    import backtest.provider_price_bounds as bounds
    directory=tmp_path/'replication_trials';directory.mkdir()
    index=pd.date_range('2025-07-01 10:16',periods=30,freq='min',tz='Asia/Kolkata')
    bars=pd.DataFrame({'open':np.arange(30)+25000.,'close':np.arange(30)+25001.},index=index)
    recipes={name:{'kind':name.split('_h5')[0],'horizon':5,'rank_window':800} for name in trials.BULK_ALPHAS}
    (directory/'alpha_recipes.json').write_text(json.dumps(recipes))
    bank={name:pd.Series(np.linspace(.1,.9,30),index=index) for name in trials.BULK_ALPHAS}
    panel=pd.DataFrame({'minute':index,'expiry':['2025-07-03']*30,'atm_strike':[25000.]*30,
        'ce_native_volume':np.arange(30)+1.,'pe_native_volume':np.arange(30)+2.,'ce_iv':[999.]*30,'pe_iv':[999.]*30},index=index)
    fields=panel.reset_index(drop=True).copy();fields['ce_iv']=10.;fields['pe_iv']=15.
    fields.loc[2,'atm_strike']=25050.;fields.loc[4,'ce_iv']=np.inf;fields.loc[6,'pe_iv']=np.nan
    fields['ce_native_volume']=99999.;fields['pe_native_volume']=99999.
    path=tmp_path/'opening.csv';fields.to_csv(path,index=False)
    monkeypatch.setattr(fixed,'OPENING_FULL_FIELDS_CACHE',path)
    monkeypatch.setattr(trials,'OUTPUT',tmp_path)
    monkeypatch.setattr(trials,'context',lambda:(bars,{},None))
    monkeypatch.setattr(trials,'load_alpha',lambda directory:bank)
    monkeypatch.setattr(trials,'factor_contexts',lambda bars,opening:{'continuous_near':(panel,None)})
    calendar_calls=[]
    monkeypatch.setattr(bounds,'calendar_support_rank',lambda raw,closed_zero:calendar_calls.append(closed_zero) or raw)
    captured=[];original_scale=trials.implied_volatility_scale
    def scale(joined,kind,window):captured.append(joined.copy());return original_scale(joined,kind,window)
    monkeypatch.setattr(trials,'implied_volatility_scale',scale)
    class FakeScorer:
        calls=0
        def __init__(self,index):
            self.entries=np.array([0,2,4,6])
            self.trades=pd.DataFrame({'signal_id':['a','b','c','d'],'entry':index[self.entries]})
        def score(self,alpha,beta):
            FakeScorer.calls+=1
            return {'fit_first_exact':FakeScorer.calls,'fit_direction_matches':1,'fit_signal_episodes':1},None
    monkeypatch.setattr(trials,'Scorer',FakeScorer)
    trials.implied_volatility_screen(opening_complete=True)
    target=directory/'implied_volatility_opening_complete'
    design=json.loads((target/'search_design.json').read_text())
    assert design['pairs']==630 and FakeScorer.calls==630 and len(design['alpha_names'])==7
    assert design['coverage']['last_completed_bar_open']['source_entries_with_both_iv']==1
    assert len(list(target.glob('candidate_*.npz')))==12
    assert len(pd.read_csv(target/'formula_trials.csv'))==630
    source_coverage=pd.read_csv(target/'source_entry_iv_coverage.csv')
    assert len(source_coverage)==4 and source_coverage.both_current_iv_known.sum()==1
    assert calendar_calls==[True,True]
    assert 'assumption' in design['calendar_policy'] and design['rank_policy']['strict_thresholds']==[.8,.2]
    assert captured[0].ce_iv.iloc[[2,4]].isna().all() and np.isnan(captured[0].pe_iv.iloc[6])
    assert original_scale(captured[0],'level').iloc[[2,4,6]].isna().all()
    np.testing.assert_array_equal(captured[0].ce_native_volume,panel.ce_native_volume)
    np.testing.assert_array_equal(captured[0].pe_native_volume,panel.pe_native_volume)
    assert panel.ce_iv.eq(999).all()  # Original panel is not mutated.


def test_legacy_iv_screen_keeps900_pairs_and_original_candidate_identity(tmp_path,monkeypatch):
    import json,hashlib
    import backtest.provider_trials as trials
    directory=tmp_path/'replication_trials';directory.mkdir()
    index=pd.date_range('2025-07-01 10:16',periods=3,freq='min',tz='Asia/Kolkata')
    bars=pd.DataFrame({'open':[25000.]*3,'close':[25001.]*3},index=index)
    panel=pd.DataFrame({'minute':index,'expiry':['2025-07-03']*3,'atm_strike':[25000.]*3,
        'ce_native_volume':[1.]*3,'pe_native_volume':[2.]*3,'ce_iv':[10.]*3,'pe_iv':[15.]*3},index=index)
    cache=tmp_path/'fields.csv';panel.reset_index(drop=True).to_csv(cache,index=False)
    recipes={name:{'kind':name.split('_h5')[0],'horizon':5,'rank_window':800} for name in trials.BULK_ALPHAS}
    (directory/'alpha_recipes.json').write_text(json.dumps(recipes))
    monkeypatch.setattr(trials,'OUTPUT',tmp_path);monkeypatch.setattr(trials,'FEATURE_CACHE',cache)
    monkeypatch.setattr(trials,'context',lambda:(bars,{'near':panel},None))
    monkeypatch.setattr(trials,'load_alpha',lambda directory:{name:pd.Series(.5,index=index) for name in trials.BULK_ALPHAS})
    monkeypatch.setattr(trials,'factor_contexts',lambda bars,opening:{'continuous_near':(panel,None)})
    class FakeScorer:
        def __init__(self,index):self.entries=np.array([0])
        def score(self,a,b):return {'fit_first_exact':1,'fit_direction_matches':1,'fit_signal_episodes':1},None
    monkeypatch.setattr(trials,'Scorer',FakeScorer)
    monkeypatch.setattr(trials.np,'savez_compressed',lambda *args,**kwargs:None)
    trials.implied_volatility_screen()
    target=directory/'implied_volatility';rows=pd.read_csv(target/'formula_trials.csv')
    assert len(rows)==900
    first=rows.iloc[0];recipe=json.loads(first.recipe)
    assert 'alpha_rank_support' not in recipe
    assert recipe['input_policy']=='exact-minute-expiry-strike-IV;positive-both;current-IV-required;no-fill'
    expected=hashlib.sha256(json.dumps({'alpha':trials.BULK_ALPHAS[0],'recipe':recipe},sort_keys=True).encode()).hexdigest()[:16]
    assert first.candidate_id==expected and recipe['atm_reference']=='last_completed_bar_close'


def test_iv_opening_full_cli_and_explicit_calendar_zero_ties(monkeypatch):
    import sys,pytest
    import backtest.provider_trials as trials
    from backtest.provider_price_bounds import calendar_support_rank
    routed=[];monkeypatch.setattr(trials,'implied_volatility_screen',lambda **kwargs:routed.append(kwargs))
    monkeypatch.setattr(sys,'argv',['provider_trials','--iv-opening-full-screen']);trials.main()
    assert routed==[{'opening_complete':True}]
    monkeypatch.setattr(sys,'argv',['provider_trials','--iv-opening-full-screen','--iv-screen'])
    with pytest.raises(SystemExit) as error:trials.main()
    assert error.value.code==2
    index=pd.DatetimeIndex(['2025-07-01 16:00','2025-07-02 09:16','2025-07-02 09:17'],tz='Asia/Kolkata')
    rank=calendar_support_rank(pd.Series([np.nan,0.,np.nan],index=index),closed_zero=True)
    assert rank.iloc[1]==400.5/800 and np.isnan(rank.iloc[2])


def test_source_joint_fill_scan_requires_both_exact_contracts_and_ranges():
    from types import SimpleNamespace
    from datetime import date
    from backtest.provider_research import source_joint_fill_scan
    index=pd.date_range('2025-07-09 10:14',periods=3,freq='min',tz='Asia/Kolkata')
    trade=SimpleNamespace(signal_id='exact',entry=index[1]+pd.Timedelta(seconds=20),expiry=date(2025,7,10),
        option_type='CE',short_strike=25000.,hedge_strike=25400.,short_entry=6.,hedge_entry=2.)
    short=pd.DataFrame({'strike':[25000.]*3,'low':[5.,5.,5.],'high':[7.,7.,7.]},index=index)
    hedge=pd.DataFrame({'strike':[25400.,25350.,25400.],'low':[1.,1.,3.],'high':[3.,3.,4.]},index=index)
    rows=source_joint_fill_scan([short,hedge],index,trade,'entry','event_day')
    assert [r['joint_fill_range_match'] for r in rows]==[True,False,False]
    assert [r['both_exact_known'] for r in rows]==[True,False,True]
    assert rows[1]['hedge_status']=='candle_unavailable'
    assert rows[0]['distance_seconds_from_source']==-80.
    assert rows[0]['candle_end']==index[1]
    assert rows[2]['hedge_fill_distance_outside']==1.
    duplicated=source_joint_fill_scan([short,short,hedge],index,trade,'entry','event_day')
    assert not any(r['joint_fill_range_match'] for r in duplicated)
    assert duplicated[0]['short_status']=='duplicate_exact_candle'


def test_source_candle_offsets_and_exact_contract_extraction():
    from backtest.provider_research import source_candle_offset, source_candle_extract
    assert source_candle_offset(25500, 25000, 1) == (10, None)
    assert source_candle_offset(24850, 25000, 2) == (-3, None)
    assert source_candle_offset(25550, 25000, 1)[1] == 'outside_supported_offset'
    assert source_candle_offset(24800, 25000, 2)[1] == 'outside_supported_offset'
    assert source_candle_offset(25025, 25000, 1)[1] == 'strike_not_on_atm_grid'
    assert source_candle_offset(25000, np.nan, 1)[1] == 'atm_strike_unknown'
    minute = pd.Timestamp('2025-07-09 10:15', tz='Asia/Kolkata')
    frame = pd.DataFrame({'strike': [25000.], 'open':[4.], 'low':[3.], 'high':[5.], 'close':[4.],
        'volume':[100.], 'iv':[12.], 'oi':[200.], 'spot':[25020.]}, index=[minute])
    assert source_candle_extract(frame, minute, 25400, 4)['status'] == 'returned_strike_mismatch'
    row = source_candle_extract(frame, minute, 25000, 6)
    assert row['fill_range_flag'] == 'outside_range' and row['fill_distance_outside'] == 1.
    assert row['strike'] == 25000 and row['volume'] == 100 and row['iv'] == 12
    assert source_candle_extract(frame, minute-pd.Timedelta(minutes=1), 25000, 4)['status'] == 'candle_unavailable'
    assert source_candle_extract(pd.concat([frame, frame]), minute, 25000, 4)['status'] == 'duplicate_exact_candle'


def test_source_candle_audit_both_legs_event_prior_and_checkpoint_resume(tmp_path, monkeypatch):
    import json
    from datetime import date
    import backtest.provider_research as research
    tz='Asia/Kolkata'
    entry=pd.Timestamp('2025-07-09 10:15:20',tz=tz); exit_ts=pd.Timestamp('2025-07-09 15:30:10',tz=tz)
    trades=pd.DataFrame([{'signal_id':'test', 'entry':entry, 'exit':exit_ts, 'expiry':date(2025,7,10),
        'option_type':'CE', 'short_strike':25000., 'hedge_strike':25400.,
        'short_entry':4., 'hedge_entry':2., 'short_exit':4., 'hedge_exit':2.}])
    monkeypatch.setattr(research,'OUTPUT',tmp_path)
    monkeypatch.setattr(research,'provider_trades',lambda:trades)
    class Client:
        cached=0;downloaded=0
        def __init__(self):self.calls=[]
        def request(self,endpoint,payload):
            assert endpoint=='rollingoption' and payload['expiryCode']==1
            assert payload['requiredData']==research.SOURCE_CANDLE_FIELDS
            assert payload['drvOptionType']=='CALL'
            # A pending source row is saved before the first network request.
            assert (tmp_path/'source_leg_candles.csv').exists()
            self.calls.append(payload);self.cached+=1
            strike=25400. if payload['strike']=='ATM+8' else 25000.
            times=pd.DatetimeIndex([entry.floor('min')-pd.Timedelta(minutes=1),entry.floor('min'),exit_ts.floor('min')-pd.Timedelta(minutes=1)])
            raw={field:[value]*3 for field,value in {'strike':strike,'open':3.,'high':5.,'low':1.,'close':3.,'volume':100.,'iv':12.,'oi':200.,'spot':25010.}.items()}
            raw['timestamp']=(times.tz_convert('UTC').as_unit('ns').asi8//10**9).tolist()
            return {'data':{'ce':raw}}
    client=Client(); offline=Client()
    research.source_candles(limit=1,client=client,offline_client=offline)
    partial=pd.read_csv(tmp_path/'source_leg_candles.csv')
    assert len(partial)==1 and partial.iloc[0].event_status=='available'
    research.source_candles(client=client,offline_client=offline)
    frame=pd.read_csv(tmp_path/'source_leg_candles.csv')
    assert len(frame)==4 and set(frame.leg)=={'short','hedge'}
    assert set(frame.loc[frame.event=='entry','event_status'])=={'available'}
    assert set(frame.loc[frame.event=='exit','event_status'])=={'outside_session'}
    assert set(frame.prior_status)=={'available'}
    hedge=frame.loc[(frame.leg=='hedge')&(frame.event=='entry')].iloc[0]
    assert hedge.event_offset==8 and hedge.event_strike==25400
    assert all(p['strike']=='ATM+8' for p in client.calls)
    assert all(p['fromDate']=='2025-07-09' and p['toDate']=='2025-07-10' for p in client.calls)
    before=len(client.calls)+len(offline.calls)
    research.source_candles(client=client,offline_client=offline)
    assert len(client.calls)+len(offline.calls)==before
    summary=json.loads((tmp_path/'source_leg_candles_coverage.json').read_text())
    assert summary['processed_leg_events']==summary['expected_leg_events']==4
    assert summary['completed_this_run']==0


def test_prior_observation_rank_matches_independent_finite_reference():
    from backtest.provider_price_bounds import prior_observation_rank
    values = pd.Series([np.nan, 2., 2., 4., 1., np.inf, 2., 0., -np.inf, 5., 2.])
    for window, fraction in ((4, 1.), (4, .5), (1, 1.), (300, .9)):
        expected = []
        for i, current in enumerate(values):
            history = values.iloc[max(0, i-window):i].to_numpy()
            history = history[np.isfinite(history)]
            known = len(history)
            expected.append((sum(history<current)+.5*sum(history==current))/known
                if np.isfinite(current) and known >= int(np.ceil(window*fraction)) else np.nan)
        result = prior_observation_rank(values, window, fraction)
        np.testing.assert_array_equal(result.to_numpy(), expected)
        assert result.index.equals(values.index)
    assert np.isnan(prior_observation_rank(pd.Series([2.]), 1).iloc[0])
    # Current itself is absent: a value above all past observations ranks1.
    assert prior_observation_rank(pd.Series([1., 2., 3.]), 2).iloc[-1] == 1.


def test_prior_observation_rank_prefix_causality_coverage_and_ties():
    from backtest.provider_price_bounds import prior_observation_rank
    rng = np.random.default_rng(773)
    values = pd.Series(rng.integers(-2, 3, size=1000).astype(float))
    values.iloc[[0, 35, 200, 600, 901]] = np.nan
    for window, fraction in ((800, 1.), (300, .9)):
        full = prior_observation_rank(values, window, fraction)
        for stop in (100, 500, 999):
            np.testing.assert_array_equal(prior_observation_rank(values.iloc[:stop], window, fraction), full.iloc[:stop])
        assert np.isnan(full.iloc[901])
    tied = prior_observation_rank(pd.Series([2., 2., 2., 2.]), 3)
    assert tied.iloc[-1] == .5
    beta = pd.Series(np.ones(301)); beta.iloc[:30] = np.nan
    assert prior_observation_rank(beta, 300, .9).iloc[-1] == .5
    beta.iloc[30] = np.nan
    assert np.isnan(prior_observation_rank(beta, 300, .9).iloc[-1])


def test_prior_observation_rank_rejects_invalid_parameters():
    import pytest
    from backtest.provider_price_bounds import prior_observation_rank
    for window in (0, -1, 1.5, True):
        with pytest.raises(ValueError):prior_observation_rank(pd.Series([1.]), window)
    for fraction in (0., -1., 1.1, np.nan, np.inf):
        with pytest.raises(ValueError):prior_observation_rank(pd.Series([1.]), 2, fraction)


def test_fixed_rank_screen_variants_use_distinct_inputs_outputs_and_preserve_ids(tmp_path,monkeypatch):
    import json,hashlib
    import backtest.provider_trials as trials
    import backtest.provider_fixed_factors as fixed
    import backtest.provider_price_bounds as bounds
    index=pd.date_range('2025-07-01 10:15',periods=3,freq='min',tz='Asia/Kolkata')
    bars=pd.DataFrame({'open':[10.,11.,12.],'close':[11.,12.,13.]},index=index)
    directory=tmp_path/'replication_trials';directory.mkdir()
    names=('close_old_open_h5_r800','close_close_old_open_h5_r800')
    recipes={name:{'kind':name.split('_h5')[0],'horizon':5,'rank_window':800} for name in names}
    (directory/'alpha_recipes.json').write_text(json.dumps(recipes))
    bank={name:pd.Series(np.nan,index=index) for name in names}
    monkeypatch.setattr(trials,'OUTPUT',tmp_path)
    monkeypatch.setattr(trials,'context',lambda:(bars,None,None))
    monkeypatch.setattr(trials,'load_alpha',lambda path:bank)
    monkeypatch.setattr(trials,'price_change_series',lambda bars,recipe:pd.Series(np.nan,index=index))
    monkeypatch.setattr(bounds,'calendar_support_rank',lambda raw,closed_zero:raw)
    class FakeScorer:
        def __init__(self,idx):self.entries=np.array([0,1])
        def score(self,a,b):return {'fit_first_exact':1,'fit_direction_matches':2,'fit_signal_episodes':3},None
    monkeypatch.setattr(trials,'Scorer',FakeScorer)
    actual_read=pd.read_csv;seen=[]
    for variant,tag in (('adjacent_log_return','logstd'),('observed_log_return','observedlogstd'),('price_std','pricestd'),
        ('adjacent_five_minute_log_return','five_minute_logstd'),('adjacent_log_rms','adjacentlogrms')):
        cache=tmp_path/f'{variant}.csv.gz'
        panel=pd.DataFrame({'minute':index,'expiry':['2025-07-03']*3,'atm_strike':[25000.]*3})
        for kind in ('close_old_open','close_close_old_open'):
            for baseline in (10,15,20):
                for window in (150,300):
                    for lag in (0,5):
                        panel[f'rank_{kind}_h5_native_v1_b{baseline}_{tag}{window}_lag{lag}']=[.1,np.nan,.9]
                        panel[f'raw_{kind}_h5_native_v1_b{baseline}_{tag}{window}_lag{lag}']=[1.,np.nan,3.]
        panel.to_csv(cache,index=False)
        monkeypatch.setattr(fixed,'fixed_rank_variant_paths',lambda value,cache=cache:(cache,tmp_path/'chunks',tmp_path/'design.json'))
        def read(path,*args,**kwargs):seen.append(path);return actual_read(path,*args,**kwargs)
        monkeypatch.setattr(trials.pd,'read_csv',read)
        trials.opening_fixed_rank_screen(variant)
        suffix='' if variant=='adjacent_log_return' else '_'+variant
        target=directory/f'opening_fixed_rank{suffix}'
        design=json.loads((target/'search_design.json').read_text())
        assert design['pairs']==48 and design['source']==str(cache)
        assert design['volatility_kind']==variant
        assert set(design['source_rank_coverage'].values())=={1}
        candidate=json.loads((target/'frontier.json').read_text())[0]
        assert tag in candidate['recipe']['beta_cache_column']
        if variant=='adjacent_log_return':
            assert 'fixed_rank_volatility' not in candidate['recipe']
            base=candidate['alpha'].removesuffix('_'+candidate['recipe']['alpha_rank_support'])
            original_id=hashlib.sha256(json.dumps({'alpha':base,'recipe':candidate['recipe']},sort_keys=True).encode()).hexdigest()[:16]
            assert candidate['candidate_id']==original_id
        else:assert candidate['recipe']['fixed_rank_volatility']==variant
    assert all((tmp_path/f'{v}.csv.gz') in seen for v in ('adjacent_log_return','observed_log_return','price_std',
        'adjacent_five_minute_log_return','adjacent_log_rms'))
    trials.opening_fixed_selected_raw_screen('adjacent_log_rms')
    target=directory/'opening_fixed_selected_raw_adjacent_log_rms'
    design=json.loads((target/'search_design.json').read_text())
    assert design['pairs']==96 and set(design['source_rank_coverage'].values())=={0}
    frontier=json.loads((target/'frontier.json').read_text())
    assert len(list(target.glob('candidate_*.npz')))==len(frontier)==12
    assert all(c['recipe']['beta_raw_cache_column'].startswith('raw_') for c in frontier)
    assert all(c['recipe']['beta_rank_order']=='opening_atm_selected_raw_then_rank' for c in frontier)


def test_fixed_rank_screen_cli_routes_variant_and_rejects_orphan_flag(monkeypatch):
    import sys,pytest
    import backtest.provider_trials as trials
    routed=[];monkeypatch.setattr(trials,'opening_fixed_rank_screen',routed.append)
    monkeypatch.setattr(sys,'argv',['provider_trials','--opening-fixed-rank-screen','--fixed-rank-volatility','price_std'])
    trials.main();assert routed==['price_std']
    monkeypatch.setattr(sys,'argv',['provider_trials','--opening-fixed-rank-screen'])
    trials.main();assert routed==['price_std','adjacent_log_return']
    monkeypatch.setattr(sys,'argv',['provider_trials','--fixed-rank-volatility','observed_log_return'])
    with pytest.raises(SystemExit) as error:trials.main()
    assert error.value.code==2
    monkeypatch.setattr(trials,'opening_fixed_selected_raw_screen',routed.append)
    monkeypatch.setattr(sys,'argv',['provider_trials','--opening-fixed-selected-raw-screen','--fixed-rank-volatility','price_std'])
    trials.main();assert routed[-1]=='price_std'


def test_autonomous_cli_lists_fixed_rank_variant_families(monkeypatch,capsys):
    import sys,pytest
    import backtest.provider_autonomous as autonomous
    monkeypatch.setattr(sys,'argv',['provider_autonomous','--help'])
    with pytest.raises(SystemExit) as error:autonomous.main()
    assert error.value.code==0
    help_text=capsys.readouterr().out
    assert 'opening_fixed_rank_observed_log_return' in help_text
    assert 'opening_fixed_rank_price_std' in help_text
    assert 'opening_fixed_rank_adjacent_five_minute_log_return' in help_text
    assert 'opening_fixed_rank_adjacent_log_rms' in help_text
    assert 'opening_fixed_selected_raw_adjacent_log_rms' in help_text


def test_selected_fixed_raw_rank_chronology_expiry_warmup_and_missing_no_fill(monkeypatch):
    import backtest.provider_trials as trials
    from datetime import date
    index=pd.date_range('2025-07-01 09:16',periods=375,freq='min',tz='Asia/Kolkata').append(
        pd.date_range('2025-07-02 09:16',periods=375,freq='min',tz='Asia/Kolkata'))
    expiry1=date(2025,7,3);expiry2=date(2025,7,10)
    monkeypatch.setattr(trials,'expiries_for',lambda day:(expiry1,expiry2) if day==date(2025,7,1) else (expiry2,date(2025,7,17)))
    a=pd.Series(np.sin(np.arange(750)/7),index=index)
    b=pd.Series(np.cos(np.arange(750)/13)+5,index=index)
    column='raw_test';panel=pd.concat([pd.DataFrame({'minute':index,'expiry':expiry1,column:a.to_numpy()}),
        pd.DataFrame({'minute':index,'expiry':expiry2,column:b.to_numpy()})],ignore_index=True)
    # Omitted observation must occupy an unknown clock slot, never compress.
    panel=panel.loc[~((panel.minute==index[450])&(panel.expiry==expiry2))]
    b.loc[index[450]]=np.nan
    result=trials.selected_fixed_raw_ranks(panel.sample(frac=1,random_state=3),index,column)
    chosen=a.where(index.date==date(2025,7,1),b)
    expected=chosen.rolling(300,min_periods=270).rank(pct=True)
    pd.testing.assert_series_equal(result['continuous_near'],expected,check_names=False)
    per=a.rolling(300,min_periods=270).rank(pct=True).where(index.date==date(2025,7,1),
        b.rolling(300,min_periods=270).rank(pct=True))
    pd.testing.assert_series_equal(result['expiry_near'],per,check_names=False)
    assert all(v.loc[index[450]]!=v.loc[index[450]] for v in result.values())
    assert abs(result['continuous_near'].iloc[375]-result['expiry_near'].iloc[375])>.01
    prefix=trials.selected_fixed_raw_ranks(panel[panel.minute<=index[600]],index[:601],column)
    for key in result:pd.testing.assert_series_equal(result[key].iloc[:601],prefix[key])


def test_current_selected_contract_factor_lag_differs_from_lagging_previous_atm_path():
    from backtest.provider_fixed_factors import contract_alpha2_ranks
    index=pd.date_range('2025-07-01 09:16',periods=750,freq='min',tz='Asia/Kolkata');t=np.arange(750,dtype=float)
    changes=pd.DataFrame({'close_old_open_h5':1.,'close_close_old_open_h5':1.},index=index)
    def frame(offset):return pd.DataFrame({'ce_ltp':100*np.exp(.03*np.sin(t/(7+offset))),
        'pe_ltp':80*np.exp(.02*np.cos(t/(9+offset))),
        'ce_volume':10+(t%(31+offset))**2,'pe_volume':12+t%(19+offset)},index=index)
    a=contract_alpha2_ranks(frame(0),changes);b=contract_alpha2_ranks(frame(4),changes)
    pick=(t//40)%2==0;name='raw_close_old_open_h5_native_v1_b10_logstd150_lag'
    current=a[name+'5'].where(pick,b[name+'5'])
    previous=a[name+'0'].where(pick,b[name+'0']).shift(5)
    valid=current.notna()&previous.notna()
    assert (current[valid]-previous[valid]).abs().max()>.01


def test_bulk_grid_is_finite_disjoint_and_includes_only_completed_five_bar_alphas():
    import json
    from backtest.provider_trials import bulk_grid,bulk_manifest,BULK_ALPHAS
    identities=set()
    for shard in range(16):
        pairs=list(bulk_grid(shard))
        assert len(pairs)==9600
        current={(alpha,json.dumps(recipe,sort_keys=True)) for alpha,recipe in pairs}
        assert len(current)==9600 and not identities.intersection(current)
        identities.update(current)
        manifest=bulk_manifest(shard)
        assert manifest['formula_recipes_per_shard']==1920
        assert all(recipe['input_policy']==manifest['input_policy'] and recipe['atm_reference']=='last_completed_bar_open' for _,recipe in pairs)
    assert len(identities)==153600
    assert len(BULK_ALPHAS)==5 and all(name.endswith('_h5_r800') and 'current_open' not in name.replace('close_close_current_open','completed') for name in BULK_ALPHAS)


def test_implied_volatility_requires_exact_contract_and_current_known_values():
    import pytest
    from backtest.provider_trials import attach_exact_implied_volatility, implied_volatility_scale
    index = pd.date_range('2025-07-01 10:16', periods=5, freq='min', tz='Asia/Kolkata')
    panel = pd.DataFrame({'expiry': ['2025-07-03']*5, 'atm_strike': [25000.]*5}, index=index)
    fields = pd.DataFrame({'minute': index.tz_convert('UTC'), 'expiry': ['2025-07-03']*5,
                          'atm_strike': [25000., 25050., 25000., 25000., 25000.],
                          'ce_iv': [10., 11., 0., 13., 14.], 'pe_iv': [15., 16., 17., 18., 19.]})
    joined = attach_exact_implied_volatility(panel, fields)
    assert joined.index.equals(index)
    assert np.isnan(joined.ce_iv.iloc[1])  # Different ATM strike cannot supply IV.
    level = implied_volatility_scale(joined, 'level')
    assert level.iloc[0] == 25 and level.iloc[3] == 31
    assert level.iloc[1:3].isna().all()  # Missing and zero current IV fail closed.
    for kind in ('level', 'mean', 'std'):
        full = implied_volatility_scale(joined, kind, 2)
        for end in range(1, len(joined)+1):
            pd.testing.assert_series_equal(full.iloc[:end], implied_volatility_scale(joined.iloc[:end], kind, 2))
        assert full.iloc[1:3].isna().all()
    with pytest.raises(pd.errors.MergeError):
        attach_exact_implied_volatility(panel, pd.concat([fields, fields.iloc[:1]]))
    for kind, window in [('future', 2), ('mean', 0)]:
        with pytest.raises(ValueError):
            implied_volatility_scale(joined, kind, window)


def test_completed_spot_volatility_is_causal_and_excludes_session_gap_when_requested():
    import pytest
    from backtest.provider_price_bounds import completed_spot_volatility
    index = pd.DatetimeIndex(['2025-07-01 15:28', '2025-07-01 15:29', '2025-07-01 15:30',
                             '2025-07-02 09:16', '2025-07-02 09:17', '2025-07-02 09:18',
                             '2025-07-02 09:19'], tz='Asia/Kolkata')
    close = np.array([100., 101., 100., 150., 151., 150., 152.])
    bars = pd.DataFrame({'close': close, 'high': close+1, 'low': close-1}, index=index)
    for kind in ('return_std', 'intraday_return_std', 'atr_fraction'):
        for lag in (0, 1):
            full = completed_spot_volatility(bars, kind, 2, lag)
            for end in range(1, len(bars)+1):
                pd.testing.assert_series_equal(full.iloc[:end], completed_spot_volatility(bars.iloc[:end], kind, 2, lag))
    normal = completed_spot_volatility(bars, 'return_std', 2)
    intraday = completed_spot_volatility(bars, 'intraday_return_std', 2)
    assert normal.iloc[3] > .1
    assert intraday.iloc[3:5].isna().all()
    missing = bars.copy(); missing.loc[index[-1], 'close'] = np.nan
    assert np.isnan(completed_spot_volatility(missing, 'atr_fraction', 2).iloc[-1])
    for kind, window, lag in [('future', 2, 0), ('return_std', True, 0), ('return_std', 2, -1)]:
        with pytest.raises(ValueError):
            completed_spot_volatility(bars, kind, window, lag)


def test_opening_fixed_factor_cache_uses_exact_opening_strike_and_carries_history(tmp_path, monkeypatch):
    from datetime import date
    from backtest import provider_fixed_factors as fixed
    index = pd.date_range('2025-07-01 10:15', periods=30, freq='min', tz='Asia/Kolkata')
    bars = pd.DataFrame({'open': 25000., 'close': 25050.}, index=index)
    bar_path = tmp_path/'bars.csv'; bars.to_csv(bar_path)
    minute = index+pd.Timedelta(minutes=1); expiry = date(2025, 7, 3)
    labels = pd.DataFrame({'minute': minute, 'expiry': expiry, 'atm_strike': 25000.})
    open_path = tmp_path/'opening.csv'; labels.to_csv(open_path, index=False)
    close_path = tmp_path/'closing.csv'; labels.assign(atm_strike=25050.).to_csv(close_path, index=False)
    rows = [{'minute': ts, 'expiry': expiry, 'strike': strike,
             'ce_ltp': 100.+i if strike == 25000. else 100.,
             'pe_ltp': 200.-i if strike == 25000. else 200.,
             'ce_volume': 10.+i if strike == 25000. else 10.,
             'pe_volume': 20.+2*i if strike == 25000. else 20.}
            for i, ts in enumerate(minute) for strike in (25000., 25050.)]
    quotes = pd.DataFrame(rows).set_index(['minute', 'expiry', 'strike']).sort_index()
    chunks = [(date(2025, 7, 1), date(2025, 7, 2)), (date(2025, 7, 2), date(2025, 7, 3))]
    def load(client, first, last, **kwargs):
        part = bars.iloc[:10] if first == chunks[0][0] else bars.iloc[10:]
        keep = part.index+pd.Timedelta(minutes=1)
        return part, quotes.loc[quotes.index.get_level_values('minute').isin(keep)], pd.DataFrame()
    reports = tmp_path/'reports'; reports.mkdir()
    for key, value in {'BAR_CACHE': bar_path, 'FEATURE_CACHE': close_path, 'OPENING_CACHE': open_path,
                      'FIXED_CACHE': tmp_path/'close_fixed.csv.gz',
                      'OPENING_FIXED_CACHE': tmp_path/'open_fixed.csv.gz', 'OUTPUT': reports}.items():
        monkeypatch.setattr(fixed, key, value)
    monkeypatch.setattr(fixed, 'history_blocks', lambda: chunks)
    monkeypatch.setattr(fixed, 'load_history', load)
    monkeypatch.setattr(fixed, 'supplement_fixed_contracts', lambda client, current, q, *args: (q, {}))
    fixed.main(opening_fixed=True)
    result = pd.read_csv(fixed.OPENING_FIXED_CACHE)
    assert result.atm_strike.eq(25000.).all() and len(result) == 30
    volume = pd.Series(10.+np.arange(30))
    expected = volume/volume.rolling(10, min_periods=8).mean()
    np.testing.assert_allclose(result.fixed_volume_ratio_1_10, expected, equal_nan=True)
    assert np.isfinite(result.fixed_log_return_10.iloc[10])  # Uses prior chunk's own-contract history.
    fixed.main()
    closing = pd.read_csv(fixed.FIXED_CACHE)
    assert closing.atm_strike.eq(25050.).all()
    assert closing.fixed_volume_ratio_1_20.dropna().eq(1.).all()
    pd.testing.assert_frame_equal(result, pd.read_csv(fixed.OPENING_FIXED_CACHE))


def test_bulk_pruning_preserves_finalists_replayed_arrays_and_unrecognized_files(tmp_path,monkeypatch):
    import pytest
    import backtest.provider_trials as trials
    monkeypatch.setattr(trials,'OUTPUT',tmp_path)
    root=tmp_path/'replication_trials'/'bulk';directory=root/'shard_00';directory.mkdir(parents=True)
    ids=['a'*16,'b'*16,'c'*16]
    for cid in ids:(directory/f'candidate_{cid}.npz').write_bytes(b'test')
    unknown=directory/'candidate_notes.npz';unknown.write_bytes(b'keep')
    (root/f'full_autonomous_{ids[1]}_ledger').mkdir()
    trials.prune_bulk_archives(directory,[{'candidate_id':ids[0]}])
    assert (directory/f'candidate_{ids[0]}.npz').exists()
    assert (directory/f'candidate_{ids[1]}.npz').exists()
    assert not (directory/f'candidate_{ids[2]}.npz').exists() and unknown.exists()
    with pytest.raises(ValueError):trials.prune_bulk_archives(tmp_path,[])


def test_research_equality_semantics_agree_with_replay_and_do_not_widen_cutoffs():
    from backtest.provider_trials import threshold_config
    from config import StrategyConfig
    from strategy.signals import evaluate_signal,Signal
    from datetime import datetime
    from utils.time import IST
    ts=datetime(2026,9,30,10,33,tzinfo=IST);base=StrategyConfig()
    assert evaluate_signal(.1,.2,ts,base)==Signal.NONE
    inclusive=threshold_config(base,'inclusive')
    assert evaluate_signal(.1,.2,ts,inclusive)==Signal.BEARISH
    assert evaluate_signal(.8,.9,ts,inclusive)==Signal.BULLISH
    assert evaluate_signal(.1,np.nextafter(.2,np.inf),ts,inclusive)==Signal.NONE
    assert evaluate_signal(np.nextafter(.8,-np.inf),.9,ts,inclusive)==Signal.NONE
    assert base.bullish_threshold==.8 and base.bearish_threshold==.2
    lower_only=threshold_config(base,'bearish_inclusive')
    assert evaluate_signal(.8,.9,ts,lower_only)==Signal.NONE
    assert evaluate_signal(.1,.2,ts,lower_only)==Signal.BEARISH


def test_current_price_is_ranked_only_against_completed_history():
    history=pd.Series([.1,.4,.2,.3,.6])
    current=pd.Series([.2,.2,.5,.4,.1])
    result=provisional_rank(history,current,w=4)
    assert result.iloc[2]==1.
    assert result.iloc[3]==.875  # history .4,.2,.3 and current .4: averaged tie rank 3.5/4
    assert result.iloc[4]==.25
    future_history=history.copy();future_history.iloc[4]=1000
    future_current=current.copy();future_current.iloc[4]=-1000
    np.testing.assert_allclose(result.iloc[:4],provisional_rank(future_history,future_current,w=4).iloc[:4],equal_nan=True)


def test_completed_price_smoothers_are_causal_and_preserve_absent_observations():
    import pytest
    from backtest.provider_price_bounds import completed_smoothed_price
    bars=pd.DataFrame({'open':np.arange(100.,164.),'close':np.arange(101.,165.)})
    changed=bars.copy();changed.iloc[40:]*=3
    specs=[('close',None),('weighted_open_close',.25),('weighted_open_close',.5),
        ('weighted_open_close',.75),('ema',2),('ema',3),('ema',5),
        ('mean',2),('mean',3),('mean',5),('median',3),('median',5)]
    for kind,parameter in specs:
        result=completed_smoothed_price(bars,kind,parameter)
        mutated=completed_smoothed_price(changed,kind,parameter)
        pd.testing.assert_series_equal(result.iloc[:40],mutated.iloc[:40])
        absent=bars.copy();absent.loc[39,'close']=np.nan
        assert pd.isna(completed_smoothed_price(absent,kind,parameter).iloc[39])
    np.testing.assert_allclose(completed_smoothed_price(bars,'weighted_open_close',.25),bars.open+.25)
    for kind,parameter in [('weighted_open_close',-1),('weighted_open_close',np.nan),('ema',1),('future',3)]:
        with pytest.raises(ValueError):completed_smoothed_price(bars,kind,parameter)


def test_calendar_rank_zero_assumption_preserves_regular_holes_and_causal_prefix():
    import pytest
    from backtest.provider_price_bounds import calendar_support_rank
    idx=pd.DatetimeIndex(['2026-10-02 15:30','2026-10-05 09:16','2026-10-05 09:17',
        '2026-10-05 09:18','2026-10-05 09:19','2026-10-05 09:20','2026-10-05 09:21','2026-10-05 09:22'],tz='Asia/Kolkata')
    raw=pd.Series([.1,.2,np.nan,.3,.4,.5,.6,.7],index=idx)
    # October2 is a holiday: its supplied value is still never overwritten.
    zero=calendar_support_rank(raw,5,closed_zero=True,min_observations=2)
    assert zero.iloc[1]==1.  # four explicit closed-period zeros plus a positive return
    assert zero.iloc[2:7].isna().all()  # regular-session missing return is not zero-filled
    assert zero.iloc[7]==1.
    observed=calendar_support_rank(raw,5,min_observations=2)
    assert pd.isna(observed.iloc[1]) and observed.iloc[3]==1.
    pd.testing.assert_series_equal(zero,calendar_support_rank(raw.tz_convert('UTC'),5,True,2).tz_convert('Asia/Kolkata'))
    future=raw.copy();future.iloc[5:]*=-100
    pd.testing.assert_series_equal(zero.iloc[:5],calendar_support_rank(future,5,True,2).iloc[:5])
    with pytest.raises(ValueError):calendar_support_rank(raw.iloc[::-1],5)
    with pytest.raises(ValueError):calendar_support_rank(raw,5,closed_zero='yes')


def test_forward_from_open_reference_delayed_five_bars():
    idx=pd.date_range('2026-09-28 10:15',periods=12,freq='min',tz='Asia/Kolkata')
    bars=pd.DataFrame({'open':np.arange(100.,112.),'close':np.arange(100.5,112.5)},index=idx)
    actual=price_change_series(bars,{'kind':'close_old_open','horizon':5})
    research=(bars.close.shift(-5)-bars.open)/bars.open
    np.testing.assert_allclose(actual,research.shift(5),equal_nan=True)
    assert actual.iloc[-1]==(111.5-106)/106


def test_trial_schema_upgrade_preserves_old_and_new_rows(tmp_path):
    path=tmp_path/'formula_trials.csv'
    with path.open('w',newline='') as stream:
        writer=csv.writer(stream)
        writer.writerow(['recipe_id','rank_window','fit_matches'])
        writer.writerow(['{"version":1}',300,12])
        writer.writerow(['{"version":2}',300,'same_as_alpha_v2',14])
    repair_trial_schema(path)
    data=pd.read_csv(path)
    assert data.fit_matches.tolist()==[12,14]
    assert data.price_change.tolist()==['legacy_close_close_h5','same_as_alpha_v2']
    assert (tmp_path/'formula_trials_schema1.csv').exists()
    before=path.read_bytes();repair_trial_schema(path)
    assert path.read_bytes()==before


def test_sampled_rank_uses_only_strictly_earlier_samples_without_double_count():
    h=pd.Series([.1,9.,.3,8.,.5,7.]);mask=np.array([True,False,True,False,True,False])
    current=pd.Series([.2,.2,.4,.2,.4,.6])
    actual=sampled_rank(h,current,mask,3)
    assert np.isnan(actual.iloc[2])  # today's sample cannot become its own history
    assert actual.iloc[3]==2/3  # prior sampled .1,.3; current .2
    assert actual.iloc[4]==1.  # prior sampled .1,.3; current .4
    assert actual.iloc[5]==1.  # prior sampled .3,.5; current .6
    changed=h.copy();changed.iloc[4:]=1000
    np.testing.assert_allclose(actual.iloc[:5],sampled_rank(changed,current,mask,3).iloc[:5],equal_nan=True)


def test_sampled_rank_every_bar_matches_normal_rank_and_missing_fails_closed():
    h=pd.Series([1.,2.,2.,4.,3.,np.nan,7.])
    expected=h.rolling(3,min_periods=3).rank(pct=True)
    actual=sampled_rank(h,h,np.ones(len(h),dtype=bool),3)
    np.testing.assert_allclose(expected,actual,equal_nan=True)


def test_premium_masks_and_replay_agree_on_side_expiry_missing_and_boundaries():
    from backtest.provider_trials import premium_eligibility,apply_research_gates
    from strategy.engine import EngineResult
    from types import SimpleNamespace
    idx=pd.DatetimeIndex(['2026-09-28 10:18','2026-09-28 10:19','2026-09-29 10:18',
        '2026-09-29 10:19','2026-09-29 10:20','2026-09-29 10:21'],tz='Asia/Kolkata')
    expiry=pd.Timestamp('2026-09-29').date()
    quotes=pd.DataFrame({'expiry':[expiry]*6,'ce_ltp':[40,200.05,20,19.95,np.nan,0],
        'pe_ltp':[39.95,40,19.95,20,np.nan,0]},index=idx)
    candidate={'recipe':{'premium_gate':{'normal_day_min':40,'expiry_day_min':20,'maximum':200}}}
    allowed=premium_eligibility(idx,candidate,quotes)
    np.testing.assert_array_equal(allowed,[[False,True],[True,False],[False,True],[True,False],[False,False],[False,False]])
    replay=SimpleNamespace(engine=SimpleNamespace(evaluate=lambda view,position:view.proposal))
    apply_research_gates(replay,candidate)
    for i,ts in enumerate(idx):
        for col,side in enumerate(('pe_ltp','ce_ltp')):
            p=SimpleNamespace(expiry=expiry,entry_ts=ts,sell_price=quotes.iloc[i][side])
            proposal=EngineResult('entry',position=p)
            result=replay.engine.evaluate(SimpleNamespace(proposal=proposal),None)
            assert (result.action=='entry')==allowed[i,col]
            if allowed[i,col]:assert result is proposal
            else:assert result.position is None
    missing=idx.append(pd.DatetimeIndex(['2026-09-29 10:22'],tz=idx.tz))
    assert not premium_eligibility(missing,candidate,quotes)[-1].any()
    exit_result=EngineResult('exit','target')
    assert replay.engine.evaluate(SimpleNamespace(proposal=exit_result),object()) is exit_result


def test_premium_scoring_rejects_only_the_relevant_direction(monkeypatch):
    import backtest.provider_trials as trials
    idx=pd.date_range('2025-07-09 10:15',periods=4,freq='min',tz='Asia/Kolkata')
    source=pd.DataFrame({'entry_minute':idx[[0,2]],'exit_minute':idx[[1,3]],
        'direction':[1,-1],'split':['fit','fit']})
    monkeypatch.setattr(trials,'provider_trades',lambda:source)
    scorer=trials.Scorer(idx);a=np.array([.9,.9,.1,.1])
    base,raw=scorer.score(a)
    allowed=np.array([[False,True],[True,False],[False,True],[False,True]])
    gated,signal=scorer.score(a,allowed=allowed)
    assert base['fit_direction_matches']==2 and gated['fit_direction_matches']==1
    assert gated['fit_available']==2
    np.testing.assert_array_equal(raw,[1,1,-1,-1])
    np.testing.assert_array_equal(signal,[0,1,-1,-1])


def test_entry_crossings_use_observed_prior_ranks_and_fail_closed_after_missing():
    from backtest.provider_trials import entry_event_mask
    a=np.array([np.nan,.9,.9,.1,.1,.1,.9,.9])
    b=np.array([.9,.9,.95,.9,.1,.1,.9,.9])
    joint=entry_event_mask(a,b,'joint')
    assert joint[:,0].tolist()==[False,False,False,False,False,False,True,False]
    assert joint[:,1].tolist()==[False,False,False,False,True,False,False,False]
    assert not entry_event_mask(a,b,'alpha')[4].any()
    assert entry_event_mask(a,b,'alpha2')[4,1]
    assert not entry_event_mask(a,b,'both')[4].any()
    assert entry_event_mask(a,b,'both')[6,0]
    np.testing.assert_array_equal(joint[:6],entry_event_mask(a[:6],b[:6],'joint'))
    a[6:]=.1;b[6:]=.1
    np.testing.assert_array_equal(joint[:6],entry_event_mask(a,b,'joint')[:6])
    assert entry_event_mask(a,b,'level') is None
    strict=entry_event_mask([.1,.1,.1],[.21,.2,.2],'joint')
    inclusive=entry_event_mask([.1,.1,.1],[.21,.2,.2],'joint','bearish_inclusive')
    assert not strict.any() and inclusive[:,1].tolist()==[False,True,False]


def test_entry_crossing_replay_keeps_exit_and_position_decisions_unchanged():
    from backtest.provider_trials import apply_research_gates,entry_event_mask
    from strategy.engine import EngineResult
    from types import SimpleNamespace
    idx=pd.date_range('2026-09-28 10:15',periods=4,freq='min',tz='Asia/Kolkata')
    indicators=pd.DataFrame({'alpha':[.9,.9,.1,.1],'alpha2':[.7,.9,.1,.1]},index=idx)
    replay=SimpleNamespace(engine=SimpleNamespace(evaluate=lambda view,position:view.proposal),
        _indicator_frame=lambda:indicators)
    apply_research_gates(replay,{'recipe':{'entry_event':'joint'}})
    expected=entry_event_mask(indicators.alpha,indicators.alpha2,'joint')
    for i,ts in enumerate(idx):
        for col,side in enumerate(('PE','CE')):
            proposal=EngineResult('entry',position=SimpleNamespace(option_type=side))
            result=replay.engine.evaluate(SimpleNamespace(now=ts,proposal=proposal),None)
            assert (result.action=='entry')==expected[i,col]
    exit_result=EngineResult('exit','stop')
    assert replay.engine.evaluate(SimpleNamespace(proposal=exit_result),object()) is exit_result


def test_ratio_of_volume_means_differs_from_mean_of_minute_ratios():
    from backtest.provider_trials import cross_volume_multiplier
    ce=pd.Series([2.,8.,0.,np.nan,4.]);pe=pd.Series([8.,8.,4.,4.,0.])
    direct=cross_volume_multiplier(ce,pe,'literal_put_call',2,20)
    mean=cross_volume_multiplier(ce,pe,'mean_put_call',2,20)
    assert direct.iloc[1]==1.6 and mean.iloc[1]==2.5
    assert np.isnan(mean.iloc[2]) and np.isnan(direct.iloc[3])
    reciprocal=cross_volume_multiplier(ce,pe,'literal_reciprocal_put_call',1,20)
    assert reciprocal.iloc[0]==2.125 and reciprocal.iloc[1]==1.
    assert reciprocal.iloc[2:].isna().all()
    prefix=cross_volume_multiplier(ce[:3],pe[:3],'mean_put_call',2,20)
    np.testing.assert_allclose(prefix,mean.iloc[:3],equal_nan=True)


def test_normalized_put_call_ratio_uses_trailing_baseline_and_missing_denominator():
    from backtest.provider_trials import cross_volume_multiplier
    ce=pd.Series([2.,2.,2.,2.]);pe=pd.Series([2.,4.,6.,8.])
    normalized=cross_volume_multiplier(ce,pe,'put_call_ratio',1,3)
    assert np.isnan(normalized.iloc[1])
    assert normalized.iloc[2]==1.5 and normalized.iloc[3]==4/3
    inverse=cross_volume_multiplier(ce,pe,'call_put_ratio',1,3)
    assert np.isclose(inverse.iloc[2],(1/3)/((1+.5+1/3)/3))
    assert cross_volume_multiplier(pd.Series([0.,0.]),pd.Series([1.,2.]),'literal_put_call',1,3).isna().all()


def test_cumulative_components_use_contract_totals_and_keep_native_volume_for_audit():
    from backtest.provider_trials import continuous_native_components
    idx=pd.date_range('2026-09-28 09:16',periods=370,freq='min',tz='Asia/Kolkata')
    n=np.arange(len(idx),dtype=float)
    bars=pd.DataFrame({'open':23000+n,'close':23001+n+np.sin(n)},index=idx)
    p=pd.DataFrame({'ce_native_volume':100.,'pe_native_volume':200.,
        'ce_contract_cumulative_volume':(n+1)**2,'pe_contract_cumulative_volume':3*(n+1),
        'ce_return':np.sin(n)/100,'pe_return':np.cos(n)/100},index=idx)
    recipe={'context':'continuous_near','volume_kind':'contract_cumulative',
        'volume_short':1,'volume_baseline':20,'volatility':'same_return_300',
        'factor_lag':5,'rank_window':300}
    ar={'kind':'close_old_open','horizon':5}
    actual=continuous_native_components(bars,p,recipe,ar)
    j=320;prior=j-5
    expected=(p.ce_contract_cumulative_volume.iloc[prior]/p.ce_contract_cumulative_volume.iloc[prior-19:prior+1].mean()
        +p.pe_contract_cumulative_volume.iloc[prior]/p.pe_contract_cumulative_volume.iloc[prior-19:prior+1].mean())/2
    assert np.isclose(actual.volume_ratio_lagged.iloc[j],expected)
    assert actual.ce_native_volume_lagged.iloc[j]==100.
    assert actual.ce_input_volume_lagged.iloc[j]==p.ce_contract_cumulative_volume.iloc[prior]
    absent=p.copy();absent.loc[idx[prior],'ce_contract_cumulative_volume']=np.nan
    assert np.isnan(continuous_native_components(bars,absent,recipe,ar).raw2.iloc[j])
    future=p.copy();future.loc[idx[j]:,['ce_contract_cumulative_volume','pe_contract_cumulative_volume']]=999999.
    pd.testing.assert_frame_equal(actual.iloc[:j],continuous_native_components(bars,future,recipe,ar).iloc[:j])


def test_contract_session_average_uses_elapsed_minutes_resets_day_and_preserves_missing():
    from backtest.provider_trials import contract_session_mean
    idx=pd.DatetimeIndex(['2026-09-28 09:16','2026-09-28 09:17','2026-09-28 09:18',
        '2026-09-29 09:16','2026-09-29 09:17','2026-09-29 16:00'],tz='Asia/Kolkata')
    p=pd.DataFrame({'ce_contract_cumulative_volume':[10.,40.,np.nan,0.,8.,999.]},index=idx)
    expected=np.array([10.,20.,np.nan,0.,4.,np.nan])
    np.testing.assert_allclose(contract_session_mean(p,'ce'),expected,equal_nan=True)
    # Expiry-grouped panels use minute columns and a row index, with identical semantics.
    long=p.reset_index(names='minute')
    np.testing.assert_allclose(contract_session_mean(long,'ce'),expected,equal_nan=True)


def test_session_average_components_distinguish_trailing_average_from_current_flow_ratio():
    from backtest.provider_trials import continuous_native_components
    idx=pd.date_range('2026-09-28 09:16',periods=370,freq='min',tz='Asia/Kolkata')
    n=np.arange(len(idx),dtype=float)
    bars=pd.DataFrame({'open':23000+n,'close':23001+n+np.sin(n)},index=idx)
    p=pd.DataFrame({'ce_native_volume':100.,'pe_native_volume':200.,
        'ce_contract_cumulative_volume':(n+1)**2,'pe_contract_cumulative_volume':3*(n+1),
        'ce_return':np.sin(n)/100,'pe_return':np.cos(n)/100},index=idx)
    recipe={'context':'continuous_near','volume_kind':'contract_session_mean',
        'volume_short':1,'volume_baseline':20,'volatility':'same_return_300',
        'factor_lag':0,'rank_window':300}
    ar={'kind':'close_old_open','horizon':5};j=320
    average=continuous_native_components(bars,p,recipe,ar)
    assert np.isclose(average.volume_ratio_lagged.iloc[j],((j+1)/np.arange(j-18,j+2).mean()+1)/2)
    flow=continuous_native_components(bars,p,{**recipe,'volume_kind':'native_over_session_mean'},ar)
    assert np.isclose(flow.volume_ratio_lagged.iloc[j],(100/(j+1)+200/3)/2)
    absent=p.copy();absent.loc[idx[j],'ce_contract_cumulative_volume']=np.nan
    assert np.isnan(continuous_native_components(bars,absent,{**recipe,'volume_kind':'native_over_session_mean'},ar).raw2.iloc[j])


def test_rank_conventions_handle_ties_endpoints_and_missing_causally():
    from backtest.provider_price_bounds import rank_conventions
    s=pd.Series([1.,2.,2.,4.,np.nan,3.,0.])
    r=rank_conventions(s,3,1.)
    expected={'average_pct':2.5/3,'minimum_pct':2/3,'maximum_pct':1.,
        'average_zero_one':.75,'empirical_strict':1/3,'empirical_mid':2/3}
    for name,value in expected.items():
        assert np.isclose(r[name].iloc[2],value)
        assert r[name].iloc[4:7].isna().all()
    assert r['average_zero_one'].iloc[3]==1.
    minimum=rank_conventions(pd.Series([2.,3.,1.]),3)
    assert minimum['average_zero_one'].iloc[-1]==0.
    partial=rank_conventions(s,3,2/3)
    assert np.isnan(partial['average_pct'].iloc[4])  # current input missing
    assert partial['average_pct'].iloc[5]==.5
    future=s.copy();future.iloc[3:]=999.
    changed=rank_conventions(future,3)
    for name in r:pd.testing.assert_series_equal(r[name].iloc[:3],changed[name].iloc[:3])


def test_signal_signatures_deduplicate_ranks_but_preserve_policy_and_chronological_scope():
    from datetime import date
    from backtest.provider_trials import signal_sequence_signature
    idx=pd.date_range('2026-02-28 23:58',periods=4,freq='min',tz='Asia/Kolkata')
    candidate={'recipe':{}};a=[.9,.1,np.nan,.9];b=[.95,.05,.5,.95]
    equivalent=[.85,.15,.5,.85]
    signature=signal_sequence_signature(idx,a,b,candidate)
    assert signal_sequence_signature(idx,equivalent,b,candidate)==signature
    assert signal_sequence_signature(idx,a,b,{'recipe':{'profit_target_mode':'disabled'}})!=signature
    assert signal_sequence_signature(idx,a,b,{'recipe':{'reentry_after_exit':True}})!=signature
    assert signal_sequence_signature(idx,a,b,{'recipe':{'premium_gate':{'normal_day_min':20,'expiry_day_min':20,'maximum':200}}})!=signature
    changed=[.9,.1,np.nan,.1]
    cutoff=date(2026,2,28)
    assert signal_sequence_signature(idx,a,b,candidate,cutoff)==signal_sequence_signature(idx.tz_convert('UTC'),a,b,candidate,cutoff)
    assert signal_sequence_signature(idx,a,b,candidate,cutoff)==signal_sequence_signature(idx,changed,b,candidate,cutoff)
    assert signal_sequence_signature(idx,a,b,candidate)!=signal_sequence_signature(idx,changed,b,candidate)
    assert signal_sequence_signature(idx,[.2]*4,[.1]*4,candidate)!=signal_sequence_signature(idx,[.2]*4,[.1]*4,{'recipe':{'threshold_comparison':'inclusive'}})
    assert signal_sequence_signature(idx,[.9]*4,[.9]*4,candidate)!=signal_sequence_signature(idx,[.9]*4,[.9]*4,{'recipe':{'entry_event':'joint'}})


def test_expiry_transforms_match_original_for_rolling_ranks_volatility_and_group_edges():
    from backtest.provider_trials import ExpiryFactorTransforms
    for labels in (['a']*5+['b']*5,['a','b']*5):
        series=pd.Series([1.,np.nan,3.,4.,5.,10.,11.,np.nan,13.,14.])
        groups=series.groupby(labels,sort=False).groups
        transforms=ExpiryFactorTransforms(series.index,groups)
        for fn in (lambda s:s.shift(1),lambda s:s.rolling(3,min_periods=2).mean(),
                   lambda s:s.rolling(3,min_periods=2).std(),
                   lambda s:s.rolling(3,min_periods=2).rank(pct=True)):
            expected=pd.Series(np.nan,index=series.index)
            for ids in groups.values():expected.loc[ids]=fn(series.loc[ids]).to_numpy()
            pd.testing.assert_series_equal(transforms.transform(series,fn),expected)
        assert (transforms.slices is not None)==(labels[1]=='a')


def test_factor_lag_cache_preserves_expiry_edges_missing_values_and_source_identity():
    from backtest.provider_trials import FactorLagCache
    calls=[]
    groups=pd.Series(['a','a','a','b','b','b'])
    def grouped(s,fn):
        calls.append(1)
        return s.groupby(groups,sort=False).transform(fn)
    source=pd.Series([1.,np.nan,3.,4.,5.,6.])
    cache=FactorLagCache(grouped,max_entries=2)
    first=cache.shift(source,'simple',1)
    pd.testing.assert_series_equal(first,source.groupby(groups,sort=False).shift(1))
    assert np.isnan(first.iloc[3]) and np.isnan(first.iloc[2])
    assert cache.shift(source,'simple',1) is first and len(calls)==1
    other=cache.shift(source*2,'log',1)
    assert other.iloc[4]==8.
    pd.testing.assert_series_equal(cache.shift(source,'simple',0),source)
    assert len(cache.values)==2
    pd.testing.assert_series_equal(cache.shift(source,'simple',1),first)
    assert len(calls)==4


def test_rolling_mean_cache_separates_sources_coverage_and_enforces_memory_bound():
    from backtest.provider_trials import RollingMeanCache
    calls=[]
    def grouped(s,fn):calls.append(1);return fn(s)
    s=pd.Series([1.,np.nan,3.,4.,5.]);cache=RollingMeanCache(grouped,max_bytes=80)
    a=cache.mean(s,('native','ce'),3,3)
    assert cache.mean(s,('native','ce'),3,3) is a
    pd.testing.assert_series_equal(a,s.rolling(3,min_periods=3).mean())
    b=cache.mean(s,('native','ce'),3,2)
    assert np.isnan(a.iloc[2]) and b.iloc[2]==2.
    other=cache.mean(s*2,('native','pe'),3,2)
    assert other.iloc[-1]==8.
    assert cache.bytes<=80 and len(calls)==3
    # First result was evicted; recomputation is exact and missing stays missing.
    pd.testing.assert_series_equal(cache.mean(s,('native','ce'),3,3),a)
    assert cache.hits==1 and cache.misses==4


def test_batch_scores_match_scalar_with_missing_boundaries_overlaps_and_chronological_splits(monkeypatch):
    import backtest.provider_trials as t
    idx=pd.DatetimeIndex([])
    for day in ('2025-07-09','2026-03-02','2026-07-01','2026-09-28'):
        part=pd.date_range(day+' 10:10',periods=20,freq='min',tz='Asia/Kolkata')
        idx=part if not len(idx) else idx.append(part)
    source=pd.DataFrame({'entry_minute':idx[[7,8,28,48,68]],'exit_minute':idx[[15,12,32,52,72]],
        'direction':[1,-1,1,-1,-1],'split':['fit','fit','validation','evaluation','case_study']})
    monkeypatch.setattr(t,'provider_trades',lambda:source)
    q=t.Scorer(idx);rng=np.random.default_rng(81)
    choices=np.array([np.nan,.1,.2,np.nextafter(.2,0),.5,.8,np.nextafter(.8,1),.9])
    a=rng.choice(choices,size=(8,len(idx)));b=rng.choice(choices,size=a.shape)
    for comparison in ('strict','inclusive','bearish_inclusive','bullish_inclusive'):
        metrics,signal=q.score_batch(a,b,comparison)
        for i in range(len(a)):
            expected,old=q.score(a[i],b[i],comparison)
            assert metrics[i]==expected
            np.testing.assert_array_equal(signal[i],old)
