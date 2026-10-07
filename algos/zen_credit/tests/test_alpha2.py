from datetime import date

import numpy as np
import pandas as pd
import pytest

from strategy.alpha2 import (build_atm_panel, calculate_alpha2, nearest_strike, rolling_volatility,
                                 volume_ratio)
from tests.conftest import ist
from strategy.alpha import forward_price_change, observed_price_change
from strategy.ranking import ts_rank

EXP = date(2026, 9, 29)


def test_strategy01_native_opening_panel_roll_missing_quote_and_live_volume():
    from strategy.strategy_01_geometric_credit import panel_from_options,panel_from_snapshots
    minutes=pd.DatetimeIndex([ist(2026,9,24,10,0),ist(2026,9,24,10,1),
        ist(2026,9,24,10,2),ist(2026,9,24,10,3)])
    bars=pd.DataFrame({'open':[23125.,23160.,23160.,23160.],
        'close':[23200.,23100.,23100.,23100.]},index=minutes-pd.Timedelta(minutes=1))
    first=date(2026,9,24);second=date(2026,9,29)
    rows=[]
    for i,minute in enumerate(minutes):
        for expiry in (first,second):
            for strike in (23100.,23150.,23200.):
                if i==2 and strike==23150.:continue
                rows.append({'minute':minute,'expiry':expiry,'strike':strike,
                    'ce_ltp':100+10*i+(strike-23100)/10,'pe_ltp':90+5*i,
                    'ce_volume':20.+i,'pe_volume':30.+i,
                    'ce_cum_volume':1000.+100*i+(strike-23100)*20,
                    'pe_cum_volume':2000.+150*i+(strike-23100)*30})
    data=pd.DataFrame(rows);quotes=data.set_index(['minute','expiry','strike'])
    resolver=lambda day:[first,second]
    panel=panel_from_options(bars,quotes,resolver)
    assert panel.atm_strike.tolist()==[23100.,23150.,23150.,23150.]
    assert panel.ce_native_volume.iloc[0]==20. # Native candle volume known despite no predecessor.
    assert panel.ce_return.iloc[1]==pytest.approx(115/105-1) # Current23150 predecessor, not old23100ATM.
    assert panel.ce_native_volume.iloc[1]==21.
    assert np.isnan(panel.ce_ltp.iloc[2]) # MissingATM23150 is not substituted with23200.
    assert panel.ce_native_volume.iloc[3]==23. and np.isnan(panel.ce_return.iloc[3])
    live=panel_from_snapshots(bars,data,resolver)
    assert live.ce_native_volume.iloc[1]==100. and live.pe_native_volume.iloc[1]==150.
    assert live.ce_return.iloc[1]==panel.ce_return.iloc[1]
    assert np.isnan(live.ce_native_volume.iloc[3]) # Missing exact predecessor is unknown.


def test_strategy01_nearest_expiry_path_stitches_without_cross_contract_return():
    from strategy.strategy_01_geometric_credit import panel_from_snapshots
    minutes=pd.DatetimeIndex([ist(2026,9,24,15,30),ist(2026,9,25,9,16),ist(2026,9,25,9,17)])
    bars=pd.DataFrame({'open':23150.,'close':23150.},index=minutes-pd.Timedelta(minutes=1))
    rows=[]
    for i,minute in enumerate(minutes):
        expiry=date(2026,9,24) if i==0 else date(2026,9,29)
        rows.append({'minute':minute,'expiry':expiry,'strike':23150.,'ce_ltp':100.+i,
            'pe_ltp':90.+i,'ce_cum_volume':1000.+100*i,'pe_cum_volume':2000.+100*i})
    result=panel_from_snapshots(bars,pd.DataFrame(rows))
    assert result.expiry.tolist()==[date(2026,9,24),date(2026,9,29),date(2026,9,29)]
    assert np.isnan(result.ce_return.iloc[1]) and np.isnan(result.ce_native_volume.iloc[1])
    assert result.ce_return.iloc[2]==pytest.approx(102/101-1) and result.ce_native_volume.iloc[2]==100.


def test_strategy01_indicators_match_independent_geometric_log_return_formula():
    from strategy.strategy_01_geometric_credit import calculate_indicators
    rng=np.random.default_rng(29);index=pd.date_range(ist(2026,9,24,9,15),periods=1200,freq='min')
    bars=pd.DataFrame({'open':23000+rng.normal(0,10,1200).cumsum(),
        'close':23000+rng.normal(0,10,1200).cumsum()},index=index)
    panel=pd.DataFrame({'ce_native_volume':rng.uniform(10,100,1200),'pe_native_volume':rng.uniform(10,100,1200),
        'ce_return':rng.normal(0,.01,1200),'pe_return':rng.normal(0,.015,1200)},index=index+pd.Timedelta(minutes=1))
    # Recorded historical feed anomalies must not silently change the frozen trial.
    panel.loc[panel.index[600], 'ce_native_volume'] = -10.
    panel.loc[panel.index[700], ['ce_native_volume', 'pe_native_volume']] = -3.
    pc=(bars.close-bars.open.shift(5))/bars.open.shift(5);pc.index=panel.index
    multiplier=np.sqrt(panel.ce_native_volume/panel.ce_native_volume.rolling(10,min_periods=8).mean()*
        (panel.pe_native_volume/panel.pe_native_volume.rolling(10,min_periods=8).mean())).shift(5)
    vol=(np.log1p(panel.ce_return).rolling(150,min_periods=120).std(ddof=1)+
        np.log1p(panel.pe_return).rolling(150,min_periods=120).std(ddof=1)).shift(5)
    expected_raw=pc*multiplier/vol
    result=calculate_indicators(bars,panel)
    pd.testing.assert_series_equal(result.alpha,pc.rolling(800,min_periods=800).rank(method='average',pct=True).rename('alpha'))
    pd.testing.assert_series_equal(result.alpha2,expected_raw.rolling(300,min_periods=270).rank(method='average',pct=True).rename('alpha2'))
    pd.testing.assert_series_equal(result.raw,expected_raw.rename('raw'))


def test_strategy01_profile_and_registry_preserve_capital_margins_and_identity(cfg):
    from dataclasses import replace
    from data.market_calendar import HolidaySetCalendar
    from strategy.registry import apply_profile,create_engine,get_strategy
    custom=replace(cfg,capital=120000.,margin_per_lot_override=33000.,margin_to_width_ratio=2.5,
        expiry_day_margin_multiplier=1.5,volume_baseline_window=333,volatility_window=333)
    profile=apply_profile('strategy_01',custom)
    assert profile.capital==120000. and profile.margin_per_lot_override==33000.
    assert profile.margin_to_width_ratio==2.5 and profile.expiry_day_margin_multiplier==1.5
    assert profile.volume_baseline_window==10 and profile.volatility_window==150 and profile.target_spread_value==10.
    assert profile.historical_time_exit_start==date(2025,7,9) and profile.historical_time_exit_end==date(2026,6,30)
    assert apply_profile('description',custom)==custom and get_strategy('description') is None
    assert create_engine('strategy_01',custom,HolidaySetCalendar(set())).strategy_name=='strategy_01'
    assert create_engine('description',custom,HolidaySetCalendar(set())).strategy_name=='description'


def snap_rows(minutes, spot, ce_px, pe_px, ce_vol, pe_vol, strikes=(23100.0, 23150.0, 23200.0)):
    rows = []
    for i, m in enumerate(minutes):
        for k in strikes:
            rows.append({"minute": m, "expiry": EXP, "strike": k, "spot": spot[i],
                         "ce_ltp": ce_px[i] + (23150 - k) * 0.5, "pe_ltp": pe_px[i] - (23150 - k) * 0.5,
                         "ce_cum_volume": ce_vol[i], "pe_cum_volume": pe_vol[i]})
    return pd.DataFrame(rows)


def test_nearest_strike_and_tie():
    assert nearest_strike(23140, [23100, 23150, 23200]) == 23150
    assert nearest_strike(23125, [23100, 23150]) == 23100   # tie -> lower


def test_panel_volume_diff_and_same_strike_returns():
    m = [ist(2026, 9, 24, 10, 0), ist(2026, 9, 24, 10, 1), ist(2026, 9, 24, 10, 3)]
    df = snap_rows(m, [23140, 23145, 23160], [100, 110, 99], [90, 81, 90], [1000, 1300, 1900], [500, 900, 1100])
    p = build_atm_panel(df)
    assert np.isnan(p["ce_volume"].iloc[0])
    assert p["ce_volume"].iloc[1] == 300 and p["pe_volume"].iloc[1] == 400
    assert p["ce_return"].iloc[1] == pytest.approx(110 / 100 - 1)
    assert list(p.index) == [pd.Timestamp(ist(2026, 9, 24, 10, minute)) for minute in range(4)]
    assert p.loc[ist(2026, 9, 24, 10, 2)].isna().all()
    assert pd.isna(p.loc[m[2], "ce_volume"]) and pd.isna(p.loc[m[2], "ce_return"])
    assert p.loc[m[2], "atm_strike"] == 23150


def test_panel_resets_across_sessions_and_large_gaps():
    m = [ist(2026, 9, 24, 15, 29), ist(2026, 9, 25, 9, 15), ist(2026, 9, 25, 9, 30)]
    df = snap_rows(m, [23140] * 3, [100] * 3, [90] * 3, [5000, 100, 400], [5000, 100, 400])
    p = build_atm_panel(df)
    assert p["ce_volume"].isna().all()


def test_volume_ratio_and_volatility():
    v = pd.Series([10.0] * 300 + [40.0] * 5)
    vr = volume_ratio(v, 5, 300)
    assert vr.iloc[-1] == pytest.approx(40 / ((295 * 10 + 5 * 40) / 300))
    r = pd.Series(np.r_[np.zeros(299), 0.01])
    assert rolling_volatility(r, 300).iloc[-1] == pytest.approx(np.std(r.values, ddof=1))


def test_alpha2_components_and_sign():
    n = 700
    idx = pd.date_range(ist(2026, 9, 24, 9, 15), periods=n, freq="1min")
    rng = np.random.default_rng(3)
    panel = pd.DataFrame({"spot": 23150.0, "atm_strike": 23150.0,
                          "ce_volume": rng.uniform(50, 150, n), "pe_volume": rng.uniform(50, 150, n),
                          "ce_return": rng.normal(0, 0.01, n), "pe_return": rng.normal(0, 0.01, n)}, index=idx)
    pc = pd.Series(rng.normal(0, 1e-4, n), index=idx)
    pc.iloc[-1] = 0.01                                   # largest change in the window
    a2, comp = calculate_alpha2(pc, panel, 300, 5, 300, 300, return_components=True)
    assert a2.iloc[-1] == 1.0
    raw = comp["raw"].iloc[-1]
    assert raw == pytest.approx(comp["price_change"].iloc[-1] * comp["volume_ratio"].iloc[-1]
                                / comp["atm_volatility"].iloc[-1])
    pc.iloc[-1] = -0.01
    assert calculate_alpha2(pc, panel, 300, 5, 300, 300).iloc[-1] == pytest.approx(1 / 300, abs=1e-9)


def test_panel_rejects_mixed_expiries():
    m = [ist(2026, 9, 24, 10), ist(2026, 9, 24, 10, 1)]
    df = snap_rows(m, [23140] * 2, [100, 110], [90, 81], [100, 200], [100, 200])
    other = df.copy()
    other["expiry"] = date(2026, 10, 6)
    with pytest.raises(ValueError, match="one expiry"):
        build_atm_panel(pd.concat([df, other]))


def test_complete_forward_formula_delayed_equals_causal_implementation():
    """Delay the whole described alpha2, rather than mixing starting/current factors."""
    rng=np.random.default_rng(62);n=750;h=5
    idx=pd.date_range(ist(2026,9,24,9,15),periods=n,freq='min')
    price=23000*np.exp(np.cumsum(rng.normal(0,.0003,n)))
    bars=pd.DataFrame({'open':price*.9999,'close':price},index=idx)
    panel=pd.DataFrame({'ce_volume':rng.uniform(1,1000,n),'pe_volume':rng.uniform(1,1000,n),
        'ce_return':rng.normal(0,.01,n),'pe_return':rng.normal(0,.01,n)},index=idx)
    vr=(volume_ratio(panel.ce_volume,5,300)+volume_ratio(panel.pe_volume,5,300))/2
    vol=rolling_volatility(panel.ce_return,300)+rolling_volatility(panel.pe_return,300)
    research=ts_rank(forward_price_change(bars,h)*vr/vol,300,min_periods=270)
    actual,parts=calculate_alpha2(observed_price_change(bars,h),panel,return_components=True,factor_lag_bars=h)
    np.testing.assert_allclose(actual,research.shift(h),equal_nan=True)
    np.testing.assert_allclose(parts.volume_ratio,vr.shift(h),equal_nan=True)
    np.testing.assert_allclose(parts.atm_volatility,vol.shift(h),equal_nan=True)
    cut=650
    changed_bars=bars.copy();changed_bars.iloc[cut+1:]*=2
    changed_panel=panel.copy();changed_panel.iloc[cut+1:]*=7
    other=calculate_alpha2(observed_price_change(changed_bars,h),changed_panel,factor_lag_bars=h)
    np.testing.assert_allclose(actual.iloc[:cut+1],other.iloc[:cut+1],equal_nan=True)
