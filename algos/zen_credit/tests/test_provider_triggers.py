"""Causal research features and direction transforms must not use future data."""
from datetime import date
import json
import numpy as np
import pandas as pd
import pytest
from backtest import provider_triggers as research
from tests.conftest import session_bars


def test_expanded_variables_are_unchanged_by_future_mutation():
    bars=session_bars([date(2026,9,21),date(2026,9,22),date(2026,9,23),date(2026,9,24),date(2026,9,25)])
    bars.index+=pd.Timedelta(minutes=1)
    rng=np.random.default_rng(44)
    panels={}
    for prefix in ('near','next'):
        p=pd.DataFrame(index=bars.index)
        for side in ('ce','pe'):
            p[f'{side}_ltp']=rng.uniform(50,150,len(bars))
            p[f'{side}_native_volume']=rng.uniform(100,1000,len(bars))
            p[f'{side}_return']=rng.normal(0,.01,len(bars))
            p[f'{side}_return_with_overnight']=p[f'{side}_return']
            p[f'{side}_oi']=rng.uniform(1000,10000,len(bars))
            p[f'{side}_iv']=rng.uniform(10,20,len(bars))
        p['atm_strike']=23000.;p['expiry']='2026-09-29'
        panels[prefix]=p
    original,_,_=research.build_variables(bars,panels)
    cut=900
    changed=bars.copy();changed.iloc[cut+1:]*=2
    changed_panels={k:v.copy() for k,v in panels.items()}
    for panel in changed_panels.values():
        cols=panel.select_dtypes(include='number').columns
        panel.loc[panel.index[cut+1:],cols]*=3
    rebuilt,_,_=research.build_variables(changed,changed_panels)
    np.testing.assert_allclose(original.iloc[:cut+1],rebuilt.iloc[:cut+1],equal_nan=True)
    expected=(bars.close-bars.close.shift(5))/bars.open.shift(5)
    np.testing.assert_allclose(original.documented_price_change,expected,rtol=1e-6,equal_nan=True)


def test_direction_transform_distinguishes_levels_from_strength():
    frame=pd.DataFrame({'signed':[.2],'rank':[.1],'unsigned':[2.]})
    meta={'kinds':{'signed':'signed','rank':'rank','unsigned':'unsigned'}}
    result=research.directional_matrix(frame,meta,np.array([0,0]),np.array([1,-1]))
    np.testing.assert_allclose(result,[[.2,.1,2.],[-.2,.9,2.]])


@pytest.mark.parametrize('unit',['us','ns'])
def test_cache_timestamp_units_are_preserved(tmp_path,monkeypatch,unit):
    index=pd.date_range('2026-09-28 10:15',periods=2,freq='min',tz='Asia/Kolkata').as_unit(unit)
    cache=tmp_path/'features.npz'
    np.savez_compressed(cache,minutes=index.asi8,values=np.array([[1.],[2.]],dtype=np.float32))
    (tmp_path/'variable_definitions.json').write_text(json.dumps({'definitions':{'value':'test'},'kinds':{'value':'signed'}}))
    monkeypatch.setattr(research,'CACHE',cache);monkeypatch.setattr(research,'OUT',tmp_path)
    frame,_=research.load_variables()
    assert frame.index[0]==index[0]
    assert frame.index[1]-frame.index[0]==pd.Timedelta(minutes=1)
