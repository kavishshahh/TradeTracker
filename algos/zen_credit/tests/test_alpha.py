from datetime import date

import numpy as np
import pandas as pd
import pytest

from strategy.alpha import calculate_alpha, forward_price_change, observed_price_change
from strategy.bars import complete_bars, resample_ohlc
from tests.conftest import ist, session_bars


def _bars(n=1200):
    return session_bars([date(2026, 9, 21), date(2026, 9, 22), date(2026, 9, 23), date(2026, 9, 24)])[:n]


def test_forward_change_formula():
    b = _bars()
    f = forward_price_change(b, 5)
    t = 100
    assert f.iloc[t] == pytest.approx((b["close"].iloc[t + 5] - b["close"].iloc[t]) / b["open"].iloc[t])
    assert f.iloc[-5:].isna().all()


def test_observed_change_is_forward_shifted_and_causal():
    b = _bars()
    o = observed_price_change(b, 5)
    t = 500
    assert o.iloc[t] == pytest.approx((b["close"].iloc[t] - b["close"].iloc[t - 5]) / b["open"].iloc[t - 5])
    assert not np.isnan(o.iloc[-1])


def test_live_alpha_equals_research_alpha_shifted():
    b = _bars()
    live = calculate_alpha(b, 800, 5, "live")
    research = calculate_alpha(b, 800, 5, "research")
    pd.testing.assert_series_equal(live.iloc[900:1100], research.shift(5).iloc[900:1100], check_names=False)


def test_alpha_range_and_warmup():
    b = _bars()
    a = calculate_alpha(b, 800, 5)
    # first valid 5-minute change at bar 5 -> 800 valid values at bar 804
    assert a.iloc[:804].isna().all() and not pd.isna(a.iloc[804])
    v = a.dropna()
    assert ((v > 0) & (v <= 1)).all()


def test_trending_up_gives_high_alpha():
    idx = pd.date_range(ist(2026, 9, 21, 9, 15), periods=900, freq="1min")
    close = pd.Series(np.linspace(23000, 23500, 900), index=idx)
    close.iloc[-5:] += np.linspace(5, 40, 5)            # sharp recent rise
    b = pd.DataFrame({"open": close.shift(1).fillna(23000), "high": close, "low": close, "close": close})
    assert calculate_alpha(b, 800, 5).iloc[-1] == 1.0


def test_invalid_mode():
    with pytest.raises(ValueError):
        calculate_alpha(_bars(), 800, 5, "future")


def test_complete_bars_drops_forming_bar():
    b = _bars()
    now = b.index[100] + pd.Timedelta(seconds=30)      # bar 100 still forming
    assert complete_bars(b, now).index[-1] == b.index[99]


def test_resample_5m_alignment():
    b = _bars(375)
    r = resample_ohlc(b, 5)
    assert r.index[0].strftime("%H:%M") == "09:15" and r.index[1].strftime("%H:%M") == "09:20"
    assert r["open"].iloc[0] == b["open"].iloc[0] and r["close"].iloc[0] == b["close"].iloc[4]
    assert len(r) == 75
