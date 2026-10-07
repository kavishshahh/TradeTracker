import numpy as np
import pandas as pd
import pytest

from strategy.ranking import ts_rank, ts_rank_last


def test_matches_reference_implementation():
    rng = np.random.default_rng(0)
    s = pd.Series(rng.normal(size=300))
    got = ts_rank(s, 50)
    for t in range(49, 300, 17):
        assert got.iloc[t] == pytest.approx(ts_rank_last(s.values[t - 49:t + 1]))


def test_definition_rank_over_window():
    s = pd.Series([3.0, 1.0, 2.0, 5.0, 4.0])
    r = ts_rank(s, 3)
    assert r.iloc[:2].isna().all()
    assert r.iloc[2] == pytest.approx(2 / 3)     # 2 in [3,1,2] -> rank 2 of 3
    assert r.iloc[3] == pytest.approx(1.0)       # 5 is max of [1,2,5]
    assert r.iloc[4] == pytest.approx(2 / 3)     # 4 in [2,5,4]


def test_ties_use_average_rank():
    r = ts_rank(pd.Series([1.0, 1.0, 1.0]), 3)
    assert r.iloc[-1] == pytest.approx(2 / 3)


def test_bounds():
    s = pd.Series(np.arange(100, dtype=float))
    r = ts_rank(s, 10).dropna()
    assert (r <= 1).all() and (r >= 1 / 10).all()
    assert r.iloc[-1] == 1.0
    assert ts_rank(-s, 10).dropna().iloc[-1] == pytest.approx(0.1)


def test_no_future_values_used():
    rng = np.random.default_rng(1)
    s = pd.Series(rng.normal(size=200))
    base = ts_rank(s, 30)
    s2 = s.copy()
    s2.iloc[150:] = 1e9
    assert base.iloc[:150].equals(ts_rank(s2, 30).iloc[:150])


def test_invalid_window():
    with pytest.raises(ValueError):
        ts_rank(pd.Series([1.0]), 0)
