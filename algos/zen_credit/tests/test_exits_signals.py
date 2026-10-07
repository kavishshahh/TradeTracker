from datetime import date

from risk.exits import EXPIRY, STOP_LOSS, TARGET, TIME_EXIT, evaluate_exit, time_exit_due
from strategy.signals import Signal, evaluate_signal, in_signal_window
from tests.conftest import ist


def test_time_exit_next_trading_day(cfg, calendar):
    due = time_exit_due(ist(2026, 9, 24, 10, 15), date(2026, 9, 29), calendar, cfg)
    assert due == ist(2026, 9, 25, 14, 53)


def test_time_exit_skips_weekend_and_holiday(cfg, calendar):
    assert time_exit_due(ist(2026, 9, 25, 10, 15), date(2026, 9, 29), calendar, cfg) == ist(2026, 9, 28, 14, 53)
    # 2 Oct 2026 is a holiday in the fixture calendar
    assert time_exit_due(ist(2026, 10, 1, 10, 15), date(2026, 10, 6), calendar, cfg) == ist(2026, 10, 5, 14, 53)


def test_time_exit_same_day_on_expiry(cfg, calendar):
    assert time_exit_due(ist(2026, 9, 29, 11, 0), date(2026, 9, 29), calendar, cfg) == ist(2026, 9, 29, 14, 53)


def test_exit_priority_and_levels():
    due = ist(2026, 9, 25, 14, 53)
    exp = date(2026, 9, 29)
    now = ist(2026, 9, 25, 11, 0)
    assert evaluate_exit(now, 141.0, 140.7, 10, due, exp).reason == STOP_LOSS
    assert evaluate_exit(now, 9.5, 140.7, 10, due, exp).reason == TARGET
    assert evaluate_exit(now, 60.0, 140.7, 10, due, exp) is None
    assert evaluate_exit(ist(2026, 9, 25, 14, 53), 60.0, 140.7, 10, due, exp).reason == TIME_EXIT
    assert evaluate_exit(ist(2026, 9, 25, 14, 53), 150.0, 140.7, 10, due, exp).reason == STOP_LOSS
    assert evaluate_exit(ist(2026, 9, 30, 9, 20), None, 140.7, 10, due, exp).reason == EXPIRY


def test_signal_thresholds(cfg):
    t = ist(2026, 9, 24, 10, 30)
    assert evaluate_signal(0.81, 0.9, t, cfg) == Signal.BULLISH
    assert evaluate_signal(0.8, 0.9, t, cfg) == Signal.NONE          # strict ">"
    assert evaluate_signal(0.1, 0.19, t, cfg) == Signal.BEARISH
    assert evaluate_signal(0.1, 0.2, t, cfg) == Signal.NONE
    assert evaluate_signal(0.9, 0.1, t, cfg) == Signal.NONE
    assert evaluate_signal(float("nan"), 0.9, t, cfg) == Signal.NONE


def test_signal_window_inclusive_bounds(cfg):
    assert in_signal_window(ist(2026, 9, 24, 10, 15), cfg)
    assert in_signal_window(ist(2026, 9, 24, 14, 15), cfg)
    assert not in_signal_window(ist(2026, 9, 24, 10, 14, 59), cfg)
    assert not in_signal_window(ist(2026, 9, 24, 14, 16), cfg)
    assert evaluate_signal(0.95, 0.95, ist(2026, 9, 24, 9, 30), cfg) == Signal.NONE
