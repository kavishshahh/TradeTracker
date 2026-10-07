import numpy as np
import pandas as pd
from datetime import date
from backtest.provider_exit_trials import margin_requirement,margin_shortfall,premium_target,profit_trigger,requires_expiry_uplift,rank_exit_trigger


def test_lock_arms_then_waits_for_return_to_floor():
    p=np.array([.03,.101,.13,.119,.100,.09])
    assert profit_trigger(p,'floor',.1).tolist()==[False,False,False,False,True,True]
    assert profit_trigger(p,'hard',.1).tolist()==[False,True,True,True,True,False]


def test_trail_uses_only_previously_observed_peak_and_ignores_missing_quote():
    p=np.array([.11,.2,np.nan,.16,.14])
    assert profit_trigger(p,'trail',.1,trail_fraction=.25).tolist()==[False,False,False,False,True]
    prefix=profit_trigger(p[:3],'trail',.1,trail_fraction=.25)
    assert np.array_equal(prefix,profit_trigger(p,'trail',.1,trail_fraction=.25)[:3])


def test_expiry_margin_shortfall_can_coexist_with_profitable_spread():
    required=margin_requirement(113000.,130,np.array([23000.,23100.]),'multiplier',1.5)
    assert np.all(required==169500.)
    deficit=margin_shortfall(required,120000.,np.array([10000.,14254.]))
    assert np.all(deficit>0)
    # Extra deposited funds change the possible broker outcome, not the signal.
    assert np.all(margin_shortfall(required,180000.,np.array([10000.,14254.]))<0)


def test_additional_elm_is_not_a_fixed_margin_multiplier():
    estimate=margin_requirement(113000.,130,np.array([23000.,24000.]),'additional_elm')
    assert np.allclose(estimate,[172800.,175400.])


def test_unknown_marked_equity_stays_unknown():
    deficit=margin_shortfall([170000.,170000.],120000.,[np.nan,10000.])
    assert np.isnan(deficit[0]) and deficit[1]==40000.


def test_expiry_day_entry_is_not_uplifted_twice_and_preexpiry_exit_is_excluded():
    expiry=date(2026,9,29)
    assert requires_expiry_uplift(date(2026,9,28),expiry,expiry)
    assert not requires_expiry_uplift(expiry,expiry,expiry)
    assert not requires_expiry_uplift(date(2026,9,25),expiry,date(2026,9,28))


def test_premium_target_does_not_replace_missing_hedge_with_zero():
    path=pd.DataFrame({'short':[13.95,12.,np.nan],'net':[11.5,np.nan,np.nan],'gross':[16.4,np.nan,np.nan]})
    assert premium_target(path,'net',10).tolist()==[False,False,False]
    assert premium_target(path,'gross',15).tolist()==[False,False,False]
    assert premium_target(path,'short',15).tolist()==[True,True,False]
    assert not premium_target(path,'none',0).any()


def test_rank_exit_waits_for_persistence_and_missing_rank_breaks_run():
    a=np.array([.9,.7,.6,np.nan,.7,.6,.5,.95])
    b=np.array([.9,.7,.6,.6,.7,.6,.5,.95])
    hit=rank_exit_trigger(a,b,1,'both',.8,3)
    assert hit.tolist()==[False,False,False,False,False,False,True,False]
    # A future rank mutation must not affect the already observed trigger.
    a[-1]=0.;b[-1]=0.
    np.testing.assert_array_equal(hit[:-1],rank_exit_trigger(a,b,1,'both',.8,3)[:-1])
    np.testing.assert_array_equal(hit[:6],rank_exit_trigger(a[:6],b[:6],1,'both',.8,3))


def test_rank_exit_reverses_support_for_bearish_spread():
    a=np.array([.1,.6,.9]);b=np.array([.1,.3,.9])
    assert rank_exit_trigger(a,b,-1,'either',.5).tolist()==[False,True,True]
    assert rank_exit_trigger(a,b,-1,'both',.5).tolist()==[False,False,True]
    assert not rank_exit_trigger(a,b,-1,'none',0).any()
