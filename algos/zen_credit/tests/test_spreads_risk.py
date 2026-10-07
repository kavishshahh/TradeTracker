from datetime import date

import pytest

from data.providers.nse import parse_option_chain
from risk.position_sizing import allocated_capital, build_risk_plan, lots_for_capital, margin_per_lot, net_credit, spread_pnl
from strategy.signals import Signal
from strategy.spreads import atm_strike, build_spread, select_expiry, strike_interval
from tests.conftest import load_fixture

EXP = date(2026, 9, 29)


def test_strike_interval_from_nse_chain_fixture():
    chain = parse_option_chain(load_fixture("nse_option_chain_sample.json"), EXP)
    assert strike_interval(chain.strikes, around=chain.spot) == 50.0


def test_strike_interval_from_contract_info_near_money():
    strikes = [float(s) for s in load_fixture("nse_contract_info_sample.json")["strikePrice"]]
    assert strike_interval(strikes, around=23140) == 50.0


def test_atm_nearest_listed_strike():
    grid = [23000 + 50 * i for i in range(10)]
    assert atm_strike(23140.5, grid) == 23150
    assert atm_strike(23124.9, grid) == 23100
    assert atm_strike(23100, [23000, 23100, 23200]) == 23100     # 100-point grid


def test_build_spread_bullish_and_bearish():
    grid = [22000 + 50 * i for i in range(60)]
    bull = build_spread(Signal.BULLISH, 23140, grid, EXP, 400)
    assert (bull.option_type, bull.sell_strike, bull.buy_strike) == ("PE", 23150, 22750)
    bear = build_spread(Signal.BEARISH, 23140, grid, EXP, 400)
    assert (bear.option_type, bear.sell_strike, bear.buy_strike) == ("CE", 23150, 23550)


def test_build_spread_requires_listed_hedge():
    with pytest.raises(ValueError):
        build_spread(Signal.BULLISH, 23140, [23100, 23150, 23200], EXP, 400)
    with pytest.raises(ValueError):
        build_spread(Signal.NONE, 23140, [23150], EXP, 400)


def test_select_expiry_includes_same_day():
    exps = [date(2026, 9, 29), date(2026, 10, 6)]
    assert select_expiry(date(2026, 9, 29), exps) == date(2026, 9, 29)
    assert select_expiry(date(2026, 9, 30), exps) == date(2026, 10, 6)
    with pytest.raises(ValueError):
        select_expiry(date(2026, 10, 7), exps)


def test_credit_and_pnl():
    assert net_credit(107.15, 11.45) == 95.70
    assert spread_pnl(95.70, 70.85 - 65.35 + 65.35 - 5.5 - 5.5, 325) == pytest.approx((95.70 - 59.85) * 325)


def test_risk_plan_values(cfg):
    p = build_risk_plan(107.15, 11.45, 400, 65, False, cfg, date(2026, 9, 24))
    assert p.net_credit == 95.70
    assert p.normal_margin_per_lot == pytest.approx(2.25 * 400 * 65)
    assert p.lots == int(320000 // (2.25 * 400 * 65)) == 5
    assert p.units == 325
    assert p.max_profit == pytest.approx(95.70 * 325)
    assert p.max_loss == pytest.approx((400 - 95.70) * 325)
    assert p.stop_loss == pytest.approx(95.70 + 0.05 * 2.25 * 400)   # credit + 45 points
    assert p.target == 10.0
    assert p.gross_credit == pytest.approx(95.70 * 325)


def test_expiry_day_sizing_uses_higher_margin_but_same_stop(cfg):
    normal = build_risk_plan(60, 20, 400, 65, False, cfg, date(2026, 9, 24))
    exp_day = build_risk_plan(60, 20, 400, 65, True, cfg, date(2026, 9, 29))
    assert exp_day.lots < normal.lots
    assert exp_day.stop_loss == normal.stop_loss
    assert margin_per_lot(400, 65, True, cfg) == pytest.approx(2.25 * 400 * 65 * 1.54)


def test_margin_override(cfg):
    import dataclasses
    c = dataclasses.replace(cfg, margin_per_lot_override=64000.0)
    p = build_risk_plan(60, 20, 400, 65, False, c, date(2026, 9, 24))
    assert p.lots == 5 and p.stop_loss == pytest.approx(40 + 0.05 * 64000 / 65, abs=0.01)


def test_invalid_inputs(cfg):
    with pytest.raises(ValueError):
        build_risk_plan(-1, 2, 400, 65, False, cfg, date(2026, 9, 24))
    with pytest.raises(ValueError):
        build_risk_plan(10, 20, 400, 65, False, cfg, date(2026, 9, 24))       # debit, not credit
    with pytest.raises(ValueError):
        build_risk_plan(30, 20, 400, 0, False, cfg, date(2026, 9, 24))
    with pytest.raises(ValueError):
        lots_for_capital(1000, 0)


def test_monday_allocation_schedule_and_sizing(cfg):
    import dataclasses
    # The supplied-description default allocates full capital on every day.
    assert allocated_capital(date(2026,9,28),cfg)==320000
    # The previously inferred Monday schedule remains an explicit optional setting.
    cfg=dataclasses.replace(cfg,monday_capital_fraction=.8)
    assert allocated_capital(date(2026, 3, 30), cfg) == 320000
    assert allocated_capital(date(2026, 4, 6), cfg) == 256000
    assert allocated_capital(date(2026, 9, 28), cfg) == 256000
    assert allocated_capital(date(2026, 9, 29), cfg) == 320000
    monday = build_risk_plan(120, 20, 400, 65, False, cfg, date(2026, 9, 28))
    friday = build_risk_plan(120, 20, 400, 65, False, cfg, date(2026, 9, 25))
    assert (monday.lots, monday.units, monday.allocated_capital) == (4, 260, 256000)
    assert friday.lots == 5 and monday.stop_loss == friday.stop_loss
