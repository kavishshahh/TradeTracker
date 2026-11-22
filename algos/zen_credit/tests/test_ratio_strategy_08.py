"""ratio_strategy_08: R4's signal and execution, short strike 50 points in the money."""
from dataclasses import fields
from datetime import date

import numpy as np
import pandas as pd
import pytest

from data.market_calendar import HolidaySetCalendar
from strategy import registry
from strategy import ratio_strategy_03_fluxer as s3
from strategy import ratio_strategy_04_fluxer_tuned as s4
from strategy import ratio_strategy_08_fluxer_itm as s8
from strategy.signals import Signal
from strategy.spreads import build_spread
from tests.conftest import ist
from tests.test_ratio_strategy_03 import EXPIRY, _bars, _daily_bars


def test_profile_differs_from_r4_only_in_the_short_strike():
    r4, r8 = registry.apply_profile("ratio_strategy_04"), registry.apply_profile("ratio_strategy_08")
    changed = {f.name for f in fields(r4) if getattr(r4, f.name) != getattr(r8, f.name)}
    assert changed == {"short_strike_otm_points"}
    assert r8.short_strike_otm_points == -50 and r4.short_strike_otm_points == 0
    assert s8.STRATEGY_NAME == "ratio_strategy_08" and "ratio_strategy_08" in registry.strategy_names()
    assert s8.panel_from_snapshots is s3.panel_from_snapshots and s4.calculate_indicators is s3.calculate_indicators


def test_put_spreads_keep_the_realised_volatility_cap(monkeypatch):
    """The cap was removed when the strategy was listed and restored on 22 Nov 2026 (see the strategy file)."""
    assert s8.calculate_indicators is s3.calculate_indicators and s8.PUT_RV_MAX == s3.PUT_RV_MAX == 16.0
    assert any(line.startswith("Put spreads need 21 completed sessions") for line in s8.LIMITATIONS)
    monkeypatch.setattr(s3, "SMOOTH_WINDOW", 1)
    monkeypatch.setattr(s3, "RANK_WINDOW", 20)
    monkeypatch.setattr(s3, "RANK_MIN_PERIODS", 10)
    rng = np.random.default_rng(5)
    sigma = 0.015                                                    # about 24% annualised
    signs = np.where(np.arange(24) % 2 == 0, 1.0, -1.0)
    bars, _ = _daily_bars(signs * sigma + rng.normal(0, sigma / 10, 24))
    clock = bars.index + pd.Timedelta(minutes=1)
    steps = np.arange(len(clock), dtype=float)
    panel = pd.DataFrame({"skew": s3.SKEW_PUT_MIN + 1 + steps / 100, "iv_ce_atm": 13.0}, index=clock)
    wild = s8.calculate_indicators(bars, panel).iloc[-2:]              # put skew, but volatility above the cap
    assert (wild["rv"] > s8.PUT_RV_MAX).all() and (wild["gate"] == 0.0).all() and (wild["alpha2"] == 0.5).all()
    free = s3.calculate_indicators(bars, panel, put_rv_max=None).iloc[-2:]      # research replays can still lift it
    assert (free["gate"] == 1.0).all() and (free["alpha2"] > s3.BULLISH_RANK).all()
    early = s8.calculate_indicators(bars.iloc[:6], panel.iloc[:6])   # no volatility history yet: no put spread
    assert early["rv"].isna().all() and (early["gate"] == 0.0).all()


def test_build_spread_moves_the_short_strike_into_the_money():
    strikes = [float(k) for k in range(23000, 25050, 50)]
    call = build_spread(Signal.BEARISH, 24010.0, strikes, EXPIRY, 400, -50)
    put = build_spread(Signal.BULLISH, 24010.0, strikes, EXPIRY, 400, -50)
    assert (call.option_type, call.sell_strike, call.buy_strike) == ("CE", 23950.0, 24350.0)
    assert (put.option_type, put.sell_strike, put.buy_strike) == ("PE", 24050.0, 23650.0)
    flat = build_spread(Signal.BEARISH, 24010.0, strikes, EXPIRY, 400)
    assert (flat.sell_strike, flat.buy_strike) == (24000.0, 24400.0)                     # default unchanged
    out = build_spread(Signal.BULLISH, 24010.0, strikes, EXPIRY, 400, 100)
    assert (out.sell_strike, out.buy_strike) == (23900.0, 23500.0)
    with pytest.raises(ValueError, match="short strike 23950.0 not listed"):
        build_spread(Signal.BEARISH, 24010.0, [k for k in strikes if k != 23950.0], EXPIRY, 400, -50)


def test_engine_sells_one_step_in_the_money_with_r4_risk_levels():
    from data.providers.base import OptionChainSnapshot, OptionQuote
    from strategy.engine import MarketView
    cfg = registry.apply_profile("ratio_strategy_08")
    engine = registry.create_engine("ratio_strategy_08", cfg, HolidaySetCalendar(set()), max_data_age_seconds=None,
                                    require_quotes=False)
    bars = _bars([date(2026, 9, 24)]).iloc[:5]
    atm = float(s3.atm_strike(bars["open"].iloc[-1]))

    def view(now, indicators):
        chain = OptionChainSnapshot("NIFTY", EXPIRY, now, float(bars["close"].iloc[-1]))
        for k in np.arange(atm - 1000, atm + 1050, 50):
            ce = max(5.0, 150.0 - (k - atm) / 4.0)
            pe = max(5.0, 150.0 + (k - atm) / 4.0)
            chain.quotes[(float(k), "CE")] = OptionQuote(float(k), "CE", ce, ce, ce, None)
            chain.quotes[(float(k), "PE")] = OptionQuote(float(k), "PE", pe, pe, pe, None)
        return MarketView(now=now, spot_bars=bars, snapshots=None, chain=chain, expiries=[EXPIRY], lot_size=65,
                          indicators=indicators)

    assert engine.evaluate(view(ist(2026, 9, 24, 11, 0), (0.05, 0.05)), None).reason == "outside signal window"
    call = engine.evaluate(view(ist(2026, 9, 24, 12, 0), (0.05, 0.05)), None)
    assert call.action == "entry" and call.position.option_type == "CE"
    assert (call.position.sell_strike, call.position.buy_strike) == (atm - 50, atm + 350)
    credit = call.position.net_credit
    assert credit == pytest.approx(162.5 - 62.5)
    assert call.position.stop_loss == pytest.approx(credit + 50) and call.position.target == pytest.approx(credit * 0.6)
    put = engine.evaluate(view(ist(2026, 9, 24, 12, 0), (0.95, 0.95)), None)
    assert put.action == "entry" and (put.position.sell_strike, put.position.buy_strike) == (atm + 50, atm - 350)
    assert put.position.exit_due == ist(2026, 9, 29, 14, 57)
