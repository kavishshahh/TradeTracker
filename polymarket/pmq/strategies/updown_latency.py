"""5-minute up/down latency rule (paper).

Polymarket's quotes follow the Binance perpetual by a few hundred milliseconds. When the perp moves
sharply, buy the matching side (Up after a rise, Down after a fall) before the quote follows, and
hold to the result.

Evidence (research/r7_tickbt.py, 50 minutes of tick data on 15 Nov 2026, exchange timestamps;
profit measured against the quote 5 s later, fee included, cents per share):
  perp moved 2 bp in 200 ms: +2.9c if the order arrives 150 ms after the move, +1.2c at 300 ms, 0 at 500 ms
  perp moved 1 bp in 200 ms: +0.9c at 150 ms, -0.3c at 300 ms
The worker in Singapore sees a Binance move after ~40 ms and needs ~90 ms to reach Polymarket.
Small sample, one evening. Not tested with real orders; Polymarket may delay taker orders.

How the paper fill works (latency_algo.py): the order is a limit at the ask the worker last saw
(plus `max_chase`). It "arrives" `order_delay_ms` after the worker received the Binance move, and
fills only if the ask in Polymarket's book at that moment (by Polymarket's own timestamps) is still
within the limit. Otherwise nothing is bought.

This class only describes the markets and parameters; it never trades through on_snapshot.
"""
from ..core import Strategy
from .updown_leader import WINDOW, window_start


class UpDownLatency(Strategy):
    origin = "tick research on Binance perp vs Polymarket quotes"
    latency_rule = True         # traded by latency_algo.LatencyTrader, not by the snapshot loop
    always_stream = True
    max_new_per_10min = 8
    min_order_usd = 1.0
    backtest_buckets = []
    market_query = dict(kind="updown5m", coins=["btc", "eth"])
    params = dict(move_bp=2.0, look_ms=200, order_delay_ms=100, binance_age_ms=40, max_signal_age_ms=400,
                  max_chase=0.01, lo=0.10, hi=0.90, max_spread=0.05, min_seconds_in=5, min_seconds_left=20,
                  stake_frac=0.05)

    def universe(self, m, now):
        start = window_start(m)
        return start is not None and start - 600 <= now < start + WINDOW


class UpDownLatency2bp(UpDownLatency):
    name = "updown_latency_2bp"
    description = "5-minute BTC/ETH up/down: when the Binance perp moves 2 bp in 200 ms, buy the matching side before Polymarket's quote follows."


class UpDownLatency1bp(UpDownLatency):
    name = "updown_latency_1bp"
    description = "Same rule with a smaller trigger: the Binance perp moves 1 bp in 200 ms."
    params = dict(UpDownLatency.params, move_bp=1.0)
