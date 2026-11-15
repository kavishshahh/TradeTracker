# Polymarket research scripts

Offline analysis behind the paper algos. Nothing here runs in the worker, touches Firestore or places
orders; everything uses Polymarket's and Binance's public data. Downloaded data goes to `research/data/`,
which is not committed.

Run from this folder with the worker's Python and the parent folder on the path (for `pmq`):

```powershell
cd polymarket\research
$env:PYTHONPATH = ".."
..\.venv\Scripts\python.exe fetch_updown.py 6 btc,eth
```

## Up/down markets: what was learned (15 Nov 2026)

1. **Buying the 70-90c leader has no edge, and neither does betting against it.** Prices are well
   calibrated: the leader wins 78% at 78c, about -2% per bet after fee and 1c; the other side is about
   -13% per bet. Same on 15-minute markets. (`analyze_reverse2.py`)
2. **`backtest_updown.py` is wrong and kept only as a record.** The saved tape is sorted inside each
   second, so its "next print" fill was the cheapest print of the next second (+5% per bet, not real).
3. **Trade-history timestamps are 3-4 s late.** Any backtest that compares that tape with Binance prices
   shows a fake profit; in `r2_sweep.py` 96% of 1,170 rules "made money", and `r4_decay.py` shows it
   vanishing when the fill is delayed 2 s. Do not trust tape + Binance backtests.
4. **Polymarket feed messages sometimes arrive seconds late**, so lead-lag measured in local receive
   time (`r5_leadlag.py`, `r6_tickbt.py`) is also unreliable. Use exchange timestamps.
5. **Latency edge, measured in exchange time (`r7_tickbt.py`, first 30 minutes only):** after a Binance
   perp move the Polymarket quote follows within about a second. Buying is positive only if the order
   arrives within roughly 150-300 ms of the Binance move, about zero at 300-500 ms, negative beyond.
   See `results/latency_30min_2026-11-15.txt`. Small sample; untested with real orders; Polymarket may
   delay taker orders.

## Files

| File | Purpose |
|---|---|
| `fetch_updown.py`, `fetch_updown15.py` | Resolved 5- and 15-minute up/down markets with every fill (the window length in days must be a multiple of the market length, e.g. `0.625`) |
| `fetch_binance_1s.py` | Binance 1-second closes for BTC and ETH |
| `build_sec.py`, `lab.py` | Per-second table (no reliance on print order inside a second) and shared helpers |
| `analyze_reverse.py`, `analyze_reverse2.py` | Leader vs the other side on the trade tape |
| `analyze_forward.py`, `analyze_forward2.py`, `updown_variants.py`, `crypto_robust.py` | Review of the version 1 paper bets (need a ledger export saved to `data/`) |
| `r1_info.py` ... `r4_decay.py` | Spot-vs-odds tests on the tape, and why they mislead |
| `record_ticks.py`, `ticks.py` | Tick recorder: Binance spot and perp quotes, Polymarket top of book and trades, with exchange timestamps |
| `r5_leadlag.py`, `r6_tickbt.py`, `r7_tickbt.py` | Lead-lag and latency backtests on the tick recording (`r7` is the one to trust) |
