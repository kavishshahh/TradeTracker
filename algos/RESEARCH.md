# NIFTY credit spread strategy

This repository runs historical backtests and records virtual forward-test trades.
The first selectable strategy is the completed profit trial `732629f0bd6093de`.
It does not place broker orders. Zen Credit's private implementation remains unverified.

## Strategy 01 — geometric volume credit spreads

Start with `zen_credit/strategy/strategy_01_geometric_credit.py`: its top comments
explain the formula, triggers, parameter values, exits and monthly backtest statistics.
`zen_credit/strategy/registry.py` selects implementations; future strategies get their
own Python file and registry entry. Shared risk, data and service code stays shared.

Reference backtest: **9 July 2025–1 October 2026**, capital **₹320,000**:
254 closed trades, **57.87% wins**, **₹668,382 gross realized profit**, **149.77%
CAGR equivalent**. Trailing 1/3/6 month returns: **−7.55% / 26.35% / 95.49%**.
Realized drawdown: **41.50%**. One open trade is excluded from those returns.
Missing option quotes make these results provisional; costs and broker liquidation
are not modeled. This trial does not reproduce Zen Credit and is not proven superior.

Run this strategy from `zen_credit/`:

```powershell
..\.venv\Scripts\python.exe -B -u -m backtest.dhan_replay --strategy strategy_01 --start 2026-09-28 --end 2026-10-01 --exit-tail-days 0 --offline --output ..\reports\strategy_01_last_week
```

Each replay writes its trade ledger, win rate, monthly profit/loss, CAGR equivalent
and trailing returns. A short replay cannot supply 1/3/6 month returns; those are
reported as unavailable until sufficient history exists.

For virtual forward testing, set `STRATEGY_NAME=strategy_01` in the root `.env`
(this is the new service default). Its formula and execution rules are pinned;
capital and margin estimates remain configurable. Use a **separate DATABASE_URL
for each deployed strategy**. The service rejects a database bound to another
strategy or an unlabelled existing position. Actual broker order execution is
not implemented.

Keep `data/` for offline replay and `reports/` for results and resumable research.
Operational files are `strategy/`, `risk/`, `data/`, `execution/`, `main.py`,
`app.py`, `config.py` and `render.yaml` inside `zen_credit/`. The `backtest/provider_*`
files support the ongoing search and reconstruction; they are not extra deployed
strategies. Selected trials and reports remain available for comparison.

## Strategy 02 — summed return variance

`zen_credit/strategy/strategy_02_variance_credit.py` records candidate
`719c7c6bc176871c`. It uses the same price and geometric-volume inputs, divides
by **CE + PE sample log-return variance over 300 candles**, and disables the
profit target. Its top comments include all rules, parameters and monthly results.

Full reference period **9 July 2025–1 October 2026**, fixed capital **₹320,000**:

| Measure | Strategy 01 | Strategy 02 |
|---|---:|---:|
| Gross realized profit | ₹668,382.00 | ₹785,704.25 |
| Closed trades / win rate | 254 / 57.87% | 194 / 57.73% |
| CAGR equivalent | 149.77% | 173.57% |
| Realized maximum drawdown | 41.50% | 33.48% |
| Trailing 1m / 3m / 6m | −7.55% / 26.35% / 95.49% | −2.32% / 9.32% / 78.27% |
| Published exact entry matches | 81 / 210 | 73 / 210 |

Both results are provisional: missing quotes, estimated margin and absent costs
or broker liquidation affect performance. Strategy 02 improves gross full-period
profit and realized drawdown, while later 3/6 month returns and Zen matching are
worse. It has not established superiority to Zen or reliable live performance.

Use `STRATEGY_NAME=strategy_02` with a separate database for virtual forward
testing. Strategy 01 remains the default. Historical replay:

```powershell
..\.venv\Scripts\python.exe -B -u -m backtest.dhan_replay --strategy strategy_02 --start 2026-09-28 --end 2026-10-01 --exit-tail-days 0 --offline --output ..\reports\strategy_02_last_week
```

Fresh last-week replay: three closed trades, **₹7,091.50 loss**, **33.33% wins**;
one open trade with **₹16,965 gross MTM**. Missing held quotes: 351 minutes.
The named calculation exactly matches all 120,000 archived signal values, and
the standalone week's four trade records match the corresponding research ledger.

Generated results in `reports/` and historical API caches in `data/dhan_cache/`
stay local and are excluded from new Git changes. Keep those data files for
offline backtests and resumable research. Strategy and research code lives in
`zen_credit/`; original provider trades remain in `data/reference/`.

The historical coverage audit classified 28,099 missing held-quote minutes in
the strongest replication candidate: 28,096 have hedges outside the supported
strike range. Both exit legs have event OHLC data for only 150 of the 210
published trades. See `reports/provider_research/replication_trials/held_quote_limits/summary.md`.
These missing prices limit exit reconstruction and the reliability of backtest results.

## Original supplied-description interpretation (`--strategy description`)

The entry code now follows the supplied 800/300 rank formula and 0.8/0.2
thresholds. The literal five-bar **forward** price change becomes observable five
bars later. Both signals are delayed consistently: alpha2's volume and volatility
factors come from the starting bar of that change. Live and historical execution
share these functions. ATM uses current spot (last completed close in replay),
capital allocation is 100%, and no inferred premium cap is applied.

Unspecified details use explicit assumptions: mean volume 5/300 for each option,
300-bar same-contract return volatility per expiry, margin-based stop 5%, spread
target 10, next-session exit 14:53 capped at expiry, and estimated margin. These
choices do not establish the private provider's implementation.

Latest run: [28 September–1 October results](reports/description_2026-09-28_2026-10-01/summary.md)
and [trade ledger](reports/description_2026-09-28_2026-10-01/trades.csv).
Reproduce from `zen_credit/`:

```powershell
..\.venv\Scripts\python.exe -B -u -m backtest.dhan_replay --start 2026-09-28 --end 2026-10-01 --exit-tail-days 0 --offline --output ..\reports\description_2026-09-28_2026-10-01
```

Existing `.env` overrides can retain older settings in forward testing. To use the
description defaults, set `ALPHA2_FACTOR_LAG_BARS=5`, `STRIKE_REFERENCE=spot`,
leave `MAX_SHORT_PREMIUM` blank and set `MONDAY_CAPITAL_FRACTION=1.0`.

## All-trade research (updated 2 October 2026)

Start with the [interactive replay](reports/provider_research/replay.html),
[findings](reports/provider_research/summary.md), or
[210-trade analysis](reports/provider_research/trade_analysis.csv).
The earlier reconstruction agreed with 165/210 trade directions but reproduced
only 45/210 first eligible entry minutes, conditional on provider position history.
It is **not a verified replica**. The fit-selected alternative failed to improve
later directional agreement and has not replaced the entry logic.

The research downloads Dhan history, retains original held strikes and tests
hundreds of candidate/diagnostic rows. Only 118 trades have uninterrupted minute-close
paths through exit; source inconsistencies and missing prices are flagged.
The provider's reported P&L is kept separate from simulated performance.

For numerical entry triggers, read the [entry-trigger report](reports/provider_research/triggers/entry_trigger_report.md)
and [each trade's condition checks](reports/provider_research/triggers/every_trade_trigger_diagnosis.csv).
This expands the research to 571 market variables, 1,120 alpha/alpha2 pairs,
one-/three-bar changes and combined numeric conditions. It compares actual entries
with preceding flat minutes and reports extra signals. Clock time and weekday are
not predictors. The candidate thresholds remain research hypotheses; the strategy
defaults have not been replaced with a fitted rule.

To reproduce from `zen_credit/` (the first command resumes missing downloads;
the remaining steps use cached data and process one historical chunk at a time):

```powershell
..\.venv\Scripts\python.exe -B -u -m backtest.provider_research --download-only
..\.venv\Scripts\python.exe -B -u -m backtest.provider_research --prepare-features
..\.venv\Scripts\python.exe -B -u -m backtest.provider_research --prepare-entry-quotes
..\.venv\Scripts\python.exe -B -u -m backtest.provider_signals
..\.venv\Scripts\python.exe -B -u -m backtest.provider_research --replay-actual
..\.venv\Scripts\python.exe -B -m backtest.provider_report
..\.venv\Scripts\python.exe -B -u -m backtest.provider_triggers --prepare
..\.venv\Scripts\python.exe -B -u -m backtest.provider_triggers --screen
```

For autonomous historical simulations within 9 July 2025–1 October 2026, add
`--provider-history-rules` to `backtest.dhan_replay`. This uses the dated exchange
calendar and the observed 15:00 exit schedule for entries through June 2026,
then 14:53 from July. Forward tests retain the configured 14:53 default.
This profile does not supply the missing private entry filter. Use smaller date
ranges for autonomous simulations; the all-trade research above streams the
full history with lower memory use. Cache keys include exact date boundaries,
so a different simulation range can require additional downloads.

Earlier reconstruction reports used the last completed NIFTY candle's **open**, which
matches all 210 published short strikes. The inferred short-option premium limit
is INR 200: every published short fill satisfies it. These are ledger-derived
rules; exact tick timing and the private alpha2 formula remain unresolved.
That conditional signal test matched 163/210 directions and 45/210 first
entry minutes. Older simulation reports predate these changes and require a rerun
for comparison with the current configuration.

## Where everything is

| Folder/file | Purpose |
|---|---|
| `zen_credit/` | Strategy, risk rules, historical replay and forward-test service |
| `data/dhan_cache/` | Downloaded index/option candles and official NSE settlement files; keep for offline backtests |
| `data/reference/` | Original provider trade CSV, latest published trade/strategy snapshots and exchange reference rules |
| `reports/dhan_2024-01-01_2025-01-01/` | Latest backtest results and price-gap diagnostics |
| `.env` | Your local credentials and settings; gitignored |
| `.env.example` | Settings template; add needed fields to your existing `.env` |
| `zen_credit/tests/` | Checks for signals, exits, pricing, replay, database state and API behavior |

## Setup

From the repository root, if an environment has not already been created:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r zen_credit/requirements-dev.txt
```

Use the existing root `.env`. Do not overwrite it with the template. Environment
variables take precedence; the older `zen_credit/.env` location is still supported
as a fallback. On a deployed service, set variables in its environment settings.

## Run the historical backtest

Supported entry ranges are 1 January 2024 through 1 January 2025, and
22 January through 10 December 2026, inclusive. The end must precede today.
Run these commands from the repository root:

```powershell
cd zen_credit
..\.venv\Scripts\python.exe -u -m backtest.dhan_replay --start 2024-01-01 --end 2025-01-01 --offline
```

Remove `--offline` to download missing data with `DHAN_CLIENT_ID` and
`DHAN_ACCESS_TOKEN`. Downloads resume from the cache. The replay adds 21 days of
warm-up and seven days after the last entry date for exits. It uses fixed historical
strikes, sourced expiry/holiday rules and the historical lot sizes.

For the recent week, with P&L valued strictly through 1 October:

```powershell
..\.venv\Scripts\python.exe -B -u -m backtest.dhan_replay --start 2026-09-28 --end 2026-10-01 --exit-tail-days 0
```

The replay starts flat. Warm-up computes indicators without taking prior trades.
`--exit-tail-days 0` leaves surviving positions open and reports their unrealized
P&L at the final minute close, separately from closed trades. Downloads always
exclude today and future dates. The 2026 rules use Tuesday expiries, 65-unit lots
and the official NSE holiday calendar.
For options still listed in the dated Dhan instrument master, the replay uses
fixed security-ID candles in place of the rolling feed. The master and chart
responses stay cached so the same run can be reproduced offline after expiry.

Defaults exclude charges and slippage. Optional `--slippage-points 0.5
--fee-per-leg 20` models adverse points per leg execution and a flat rupee fee per
leg order; it does not calculate all taxes. Historical runs use the reconstruction
defaults in `StrategyConfig`; forward-test environment overrides do not tune them.

Read [the latest summary](reports/dhan_2024-01-01_2025-01-01/summary.md) and
[trade ledger](reports/dhan_2024-01-01_2025-01-01/trades.csv). Other files in that
folder explain decisions, indicators, conflicting quotes and missing prices.
Results are provisional: Dhan's rolling archive covers nearby strikes, so a held
leg can leave its range. Missing quotes are not filled or replaced. Official dated
NSE index closes resolve expired contracts, but cannot repair earlier missed exits.
Execution and stops are simulated at minute closes, not tick-by-tick fills.

## Run the forward test

The current service gets live option chains from NSE and index bars from Yahoo.
Dhan is connected for historical replay; a Dhan live feed is not implemented yet.
Forward testing needs `DATABASE_URL` for PostgreSQL state/history. Set
`EMAIL_ENABLED=false` for paper testing without alerts, or configure the SMTP and
email fields in `.env` to receive entry/exit alerts.

From `zen_credit/`:

```powershell
..\.venv\Scripts\python.exe main.py --check-db
..\.venv\Scripts\python.exe main.py --once
```

Run `--once` every minute during 09:15-15:30 Asia/Kolkata to collect history and
evaluate exits. Alpha2 needs roughly 510-600 recorded session minutes to warm up.
Positions, snapshots and signal history live in PostgreSQL; do not delete that
database to clean local files. Missing/stale data blocks new entries.

For the web service, run `..\.venv\Scripts\python.exe app.py` from this directory. It exposes `/health`,
`/status` and `POST /run-cycle`. The POST requires `X-Cron-Token: <CRON_TOKEN>`.
`zen_credit/render.yaml` keeps the deployment settings. Configure a scheduler to
call `/run-cycle` each minute during the session. No orders are submitted.

## Original interpretation rules (`description`)

| Rule | Implementation |
|---|---|
| alpha | Rank the causal five-bar change `(close[T]-close[T-5])/open[T-5]` over 800 observed session bars |
| alpha2 | Rank observed change times starting-bar average CE/PE volume ratio (5/300), divided by starting-bar summed CE/PE return volatility (300), over 300 bars; option factors delayed 5 bars |
| Entry | Both ranks above 0.8: sell ATM put, buy put 400 points below. Both below 0.2: sell ATM call, buy call 400 points above |
| Entry window | 10:15-14:15 Asia/Kolkata; nearest expiry, including same-day expiry |
| Strike reference | Nearest listed strike to current spot; replay uses the last completed close |
| Premium eligibility | No premium cap by default |
| Position size | Floor of allocated capital divided by estimated margin per lot; base capital INR 320,000 |
| Allocation | 100% every day by default; a Monday fraction can be configured explicitly |
| Stop | Credit plus 5% of normal-day margin per lot divided by lot size (default approximately 45 points) |
| Target | Spread value at or below 10 points |
| Scheduled exit | 14:53 next trading day, capped at expiry day |
| Positions | One position at a time; exits evaluated before another entry |

The directional mapping is momentum-like. Alpha2 internals, margin estimates,
target, stop and scheduled exit are reconstruction assumptions. The 2024 replay
used the previous reconstruction defaults before the provider's published trade period; it does not
establish that the private strategy used those rules in 2024. Missing option minutes
remain missing, and returns compare the same strike in adjacent session minutes.

<details>
<summary>Research history and rejected trial families</summary>

## Replication research

The resumable parameter search and trade-by-trade evidence are in
[the trial summary](reports/provider_research/replication_trials/summary.md).
These candidates are still research results; they have not replaced the service
strategy. Matching direction at a published entry is weaker evidence than taking
the same trade autonomously without extra trades.

From `zen_credit/`, run one main search worker at a time:

```powershell
..\.venv\Scripts\python.exe -B -u -m backtest.provider_trials
..\.venv\Scripts\python.exe -B -u -m backtest.provider_trials --expanded --limit 1000
..\.venv\Scripts\python.exe -B -u -m backtest.provider_trials --replay-top 4
..\.venv\Scripts\python.exe -B -u -m backtest.provider_autonomous
..\.venv\Scripts\python.exe -B -u -m backtest.provider_trial_report
```

`--fine` runs a separate neighboring-window and factor-lag search in the `fine/`
research folder; `--expanded` uses its own `expanded/` folder for additional volume
definitions. Full-history autonomous replay carries open positions across raw-data
chunks and resumes from its checkpoint. It permits entries through the final
published exit date, including extras after the last published entry.
`backtest.provider_exit_trials` compares causal profit targets,
profit floors and trailing exits on complete original-contract paths. Incomplete
paths are excluded from exit match scores.

`backtest.provider_exit_trials --margin` screens each published position for
possible expiry-day margin shortfalls at unchanged source quantities. It compares
1.50/1.54 margin scenarios and an additional 2% of short index notional. These are
diagnostics: broker funds and historical margin updates are unavailable, so a
shortfall flag is not a confirmed liquidation or simulated fill. No automatic
margin reserve or liquidation rule has been added to the trading strategy.

`backtest.provider_fixed_factors` reconstructs volume ratios and rolling volatility
from each selected ATM contract's own history. The corresponding comparison runs
with `backtest.provider_trials --fixed-contract --contexts continuous_near expiry_near`.
`--mixed` tests separate return definitions for alpha and alpha2. Each trial family
has its own journal, candidate files and checkpointed summary in the research folder.

`backtest.provider_price_bounds --sampling` compares historical observation
frequencies for alpha without restricting entries to a particular bar phase.
`--sampling-pairs` tests sampled alpha2 ranks against the fit-leading alpha
choices. Their candidates can be replayed across the full history using
`backtest.provider_autonomous --family sampling`. Prior-minute compatibility is
diagnostic only; it does not introduce an unverified order delay.

The [premium eligibility trials](reports/provider_research/replication_trials/eligibility/summary.md)
test 125 combinations on five saved alpha/alpha2 candidates. The provider lists
a PREMIUM check but does not specify its thresholds. The fit-selected candidate
matches 74/210 entries across the full history, with 180 extras; it is not a replica.
These research filters preserve the existing sizing and exit rules.

The [opening-ATM comparison](reports/provider_research/replication_trials/opening_atm/summary.md)
tests 1,280 option-factor formulas. The selected reconstruction matches 80/210
entries with 170 extras. Its matched close-ATM control also matches 80 entries,
with 182 extras. The report includes price changes, volume ratios, volatility and
alpha2 values for every source entry. Neither candidate is a verified replica.

Generate this alternative panel and bank with
`backtest.provider_fixed_factors --opening-reference`, then
`backtest.provider_trials --family opening_atm`. Replay and report with
`backtest.provider_autonomous --family opening_atm` and
`backtest.provider_trial_report --family opening_atm`.

The [volume aggregation comparison](reports/provider_research/replication_trials/opening_volume/summary.md)
tests 240 formulas on the same opening-selected ATM data. Its harmonic-mean
candidate matches 74/210 entries with 172 extras, versus 72 matches and 172 extras
for its otherwise identical arithmetic control. It does not improve on the
80-match opening-ATM candidate. Reproduce with
`backtest.provider_trials --family opening_volume`.

`backtest.provider_exit_trials --rank-exits` tests whether alpha and alpha2 losing
directional support explain exits. It compares the first modeled exit against
matched stop/target controls on complete source-conditioned spread paths. The
[exit report](reports/provider_research/replication_trials/rank_exit_review.md)
and [public exit-field audit](reports/provider_research/public_exit_field_audit.csv)
retain the evidence without changing the trading service.

The [fresh-crossing tests](reports/provider_research/replication_trials/crossings/summary.md)
compare 20 matched entry rules. Requiring a fresh joint threshold crossing
matches 61/210 entries with 192 extras, versus 74 matches and 172 extras for its
otherwise identical level-condition control. Its weekly trade path is unchanged.
The report includes previous ranks and independent replay states for all source
entries. Generate the bank with `backtest.provider_trials --family crossings`,
then replay with `backtest.provider_autonomous --family crossings`.

The [put/call volume-ratio tests](reports/provider_research/replication_trials/opening_pcr/summary.md)
compare 392 formulas using opening-selected ATM contracts. The selected CE/PE
ratio matches 65/210 entries with 189 extras; its otherwise identical per-leg
relative-volume control matches 54 entries with 195 extras. This does not improve
on the 80-match opening-ATM candidate. Generate this bank with
`backtest.provider_trials --family opening_pcr`.

Full-history research replays require the dated official NSE settlement whenever
a position survives expiry. Transient archive requests are retried; an unavailable
required settlement stops the replay before later entries are scored. The
[December settlement recovery](reports/provider_research/replication_trials/opening_pcr/settlement_recovery.json)
records the recovered official archive and excludes the failed control run.

The [contract cumulative-volume audit](reports/provider_research/replication_trials/contract_cumulative/panel_design.json)
reconstructs daily totals from each actual option contract's own minute volumes.
Both legs have complete prefixes at all 210 published entry minutes. The panel
contains 240,000 near/next ATM observations; absent earlier minutes invalidate a
total rather than being replaced with zero. The [matched replay report](reports/provider_research/replication_trials/contract_cumulative/summary.md)
compares 224 formulas with seven price signals. The selected cumulative candidate
matches 61/210 entries with 184 extras, versus 57 matches and 191 extras for its
otherwise identical minute-volume control. It matches both September 28/30 entry
minutes with no weekly extras, but the first exit is delayed by missing hedge
quotes. It does not improve the existing 80-match full-history candidate.
Rebuild the panel with `backtest.provider_fixed_factors --contract-cumulative`,
then run `backtest.provider_trials --family contract_cumulative`. All 504 shared
native control pairs reproduce the previous bank's 28 metrics exactly.
Two session-average interpretations also match both weekly entry minutes:
normalizing cumulative volume by elapsed session minutes yields 59/210 full-history
matches with 184 extras; current minute volume divided by its same-contract
session average yields 56 matches with 176 extras. These remain research
hypotheses and do not recover the provider's full trade path.

The [rank-convention comparison](reports/provider_research/replication_trials/rank_conventions/summary.md)
tests 144 combinations of percentile and tie definitions on four fixed input
models. All unchanged controls reproduce their original arrays exactly. Thirty-two
alternative definitions leave every eligible signal unchanged. The strongest
changed-signal convention for the 80-match model produces 78 matches and 172
extras. The cumulative-volume variant improves from 61 to 63 matches, with 179
extras, but still misses most published entries. Generate the bank with
`backtest.provider_price_bounds --rank-conventions`; replay it using
`backtest.provider_autonomous --family rank_conventions`.

Research searches now share identical rolling-volume means through a context-local
64 MiB cache. The [real-data benchmark](reports/provider_research/replication_trials/rolling_cache_benchmark.json)
verified exact output arrays: this component ran about 7.3x faster on the
continuous panel and 9.2x faster on the expiry-grouped panel. These are component
timings, not overall backtest speedups. Reproduce with
`backtest.provider_trials --benchmark-cache`.

Full-history finalists can share raw historical chunks in bounded groups:

```powershell
cd zen_credit
..\.venv\Scripts\python.exe -B -m backtest.provider_autonomous --family opening_atm --batch-finalists 2 --batch-size 2 --style ledger
```

Each candidate keeps independent positions, exits and resumable checkpoints.
The replay-engine fixture verifies identical individual and grouped results,
with chunk loads reduced from four to two. This is an I/O reduction, not a
measured end-to-end runtime speedup. Two candidates per group limits memory use.
The separate batch scorer also reproduces scalar metrics and signals exactly,
but its real-data benchmark on seven pairs and 120,000 minutes was slightly
slower (0.938x), so ordinary searches retain scalar scoring. Benchmark results
are saved in `reports/provider_research/replication_trials/batch_scoring_benchmark.json`.

The finite bulk search tests 153,600 parameter combinations (30,720 factor
recipes paired with five completed-price alpha definitions). Sixteen disjoint
shards cover two ATM-history contexts and eight volume definitions. Each shard
has its own resumable trial journal; at most two local workers run together.
They read the shared alpha bank and retain finalist rank arrays for replay.

Bulk workers also cache factor shifts: eight volatility definitions across eight
lags are reused, and volume shifts are cached per window pair. This reduces
grouped shift calls from 3,840 to 304 per full shard. At 240,000 expiry rows the
additional array payload is about 132 MiB per worker. Newly started workers use
this optimization; already running workers retain their loaded code. This is a
reduction in repeated calculations, not a measured whole-search speedup.

For sorted expiry panels, queued bulk workers apply rolling operations through
contiguous Series slices. Noncontiguous groups keep the original label-based
calculation. On the cached 240,000-row panel, output equality was verified for
shifts, rolling means, standard deviations and ranks. The rank component was
about 1.08x faster in this benchmark; a full-search speedup was not measured.
Results are in `reports/provider_research/replication_trials/expiry_transform_benchmark.json`.

Finalist merging removes duplicate full directional signal sequences as well as
identical rank arrays. Premium gates and profit-target policy remain separate,
so identical indicators do not erase distinct exit experiments. Fit signatures
use observations through 28 February 2026, with crossing masks calculated before
the cutoff. The saved alias audit is a screening aid: reuse of historical outcomes
also requires identical quotes, execution configuration, period and initial state.

```powershell
cd zen_credit
..\.venv\Scripts\python.exe -B -u -m backtest.provider_price_bounds --bulk-workers 2
```

Use `--bulk-limit 2` for two new recipes per shard. Re-running resumes existing
journals. Progress and worker logs live in
`reports/provider_research/replication_trials/bulk/`. After successful workers,
the scheduler merges fit-selected finalists. Independently replay them with
`backtest.provider_autonomous --family bulk --batch-finalists 2 --batch-size 2`.

The fixed five-alpha grid cannot reproduce all published entries: its optimistic
per-trade union passes 204/210 necessary alpha conditions, while the strongest
single definition passes 201/210. The six failures and ranks are recorded in
`bulk/alpha_entry_ceiling.csv`. Volume and volatility trials can improve alpha2
and suppress extra trades, but cannot resolve those alpha failures. A screened
formula is a hypothesis until autonomous entry, exit and quote-coverage checks
support it across the full history.

Shortlist selection can now use actual autonomous fit-period entries rather
than only conditional first-signal scores. Run the first ten historical chunks,
then rank committed paths by exact source entry matches through 28 February
2026 and fewer extra entries. The scorer includes carried open positions and
ignores later entries, later labels and uncommitted output files. Finalists can
resume their existing checkpoints for the remaining full-history validation.

```powershell
..\.venv\Scripts\python.exe -B -m backtest.provider_autonomous --family bulk --frontier-name fit_stage_frontier --batch-finalists 2 --limit-blocks 10
..\.venv\Scripts\python.exe -B -m backtest.provider_autonomous --family bulk --frontier-name fit_stage_frontier --rank-fit
```

The fit rankings are written to `bulk/fit_autonomous_selection.json`, with
original candidate definitions retained in `bulk/fit_autonomous_frontier.json`.
Later periods were previously inspected; these chronological checks are not
untouched holdouts. The fit-stage candidates are provisional snapshots while
the broader grid remains active.

The 153,600-pair bulk grid is now complete. Its conditional rankings prioritize
replays; published exit resets in that screening score mean that a lower-ranked
formula is not proven worse in autonomous trading. Final shortlist and completion
evidence are in `bulk/frontier.json` and `bulk/bulk_progress.json`. Two previously
untested shortlist formulas and their disabled-target controls are defined in
`bulk/final_grid_fit_design.json` for independent fit-period replays.

Candidate batches now prepare the sorted option quote lookup once per chunk.
The shared quote mapping and numeric buffers are immutable; positions, decisions
and missing-quote records remain independent. On a cached 209,990-row chunk,
two-candidate constructor preparation took a median 0.36 seconds with sharing
versus 0.74 seconds without it. This measures preparation only, not whole-replay
runtime. Evidence is in `replication_trials/shared_quote_index_benchmark.json`.

Replay chains now expose a read-only view of the prepared numeric quotes and
construct an `OptionQuote` only when requested. All valid strikes, missing ATM
placeholders and last-valid duplicate prices are preserved. On the first two
cached chunks, unprofiled replay was 1.35x and 1.47x faster than eager chain
construction, with identical decisions, trades, carried positions, trade details
and missing-quote events. Loading and report writing are excluded from these
timings; this is not a full-history speed measurement. The comparison and 66-test
verification are in `replication_trials/bulk/lazy_quote_replay_benchmark.json`.

The calendar-minute alpha controls with assumed zero returns outside market
hours passed every source entry's necessary alpha direction, but their actual
fit replays regressed from 38 to 32 and from 40 to 36 exact entries. Execution
decisions across all ten tested chunks were identical to the direction-only
controls. These two candidates are rejected at fit selection; their later
history remains untested. Evidence is in `bulk/calendar_alpha_fit_comparison.json`.

The separate implied-volatility screen tests 900 pairs using current CE+PE IV,
rolling IV means or rolling IV standard deviations. Opening-selected ATM IV is
joined only on identical completed minute, expiry and strike; missing IV is not
filled from another contract. Exact positive opening-strike IV exists at 168/210
published entries, versus 209/210 for closing-selected ATM IV. Conditional scores
are exploratory. Three distinct IV controls completed autonomous fit replay with
27, 25 and 24 exact entries and 95, 97 and 94 extra entries. The existing
geometric-volume/log-return-STD leader has 40 exact and 76 extra fit entries,
so these IV controls are rejected at fit selection. This does not rule out IV
interpretations with missing opening-strike data or other untested definitions.
Results and coverage are in `replication_trials/implied_volatility/fit_comparison.json`.

From `zen_credit`, reproduce the screen and resume the fit replays with:

```powershell
..\.venv\Scripts\python.exe -B -m backtest.provider_trials --iv-screen
..\.venv\Scripts\python.exe -B -u -m backtest.provider_autonomous --family implied_volatility --frontier-name fit_stage_frontier --batch-finalists 3 --batch-size 3 --limit-blocks 10
```

`--limit-blocks` limits newly committed chunks on each invocation; it does not
set an absolute endpoint. Inspect checkpoints before resuming a completed fit
batch, since another invocation can advance into later validation periods.

An exploratory alpha1 volatility-normalization screen tested 146 definitions.
Its best necessary direction coverage was 202/210 versus 201/210 unscaled.
Paired with unchanged geometric alpha2, the fit replay tied 40 exact entries
with one fewer extra entry. Full-history validation declined to 80/210 exact
entries with 126 extras, versus 81/210 and 126 for its seed; the September week
still generated five entries. This extension is rejected as an improvement.
Evidence is in `replication_trials/volatility_normalized_alpha/completed_comparison.json`.

The next distinct factor preparation uses the opening-selected ATM strike's own
fixed-contract rolling history. Prior `FIXED_CACHE` used closing-selected ATM;
bulk opening-ATM factors roll along a changing selection of strikes. Prepare the
new cache with `backtest.provider_fixed_factors --opening-fixed`. It uses exact
expiry/strike quotes, carries 300 prior observations across chunks and leaves
overnight returns and absent quotes unknown. New windows are 10/15/20/60/150/300,
with volume short window 1. The existing closing-selected cache is preserved.

The opening own-strike factors were screened in 120 pairs, with rank300 still
following the selected ATM path. Three fit controls produced 26, 22 and 21 exact
entries, with 84, 86 and 85 extras; they do not improve the 40-exact/76-extra fit
leader. Evidence is in `replication_trials/opening_fixed/fit_comparison.json`.

A separate experiment computes raw alpha2 and rank300 within each exact
expiry/strike BEFORE selecting the opening ATM contract. It carries 610 prior
observations, retains the original opening-price denominator and preserves
unknown quotes and overnight returns. Its 24 formulas cover volume baseline
10/15/20, logSTD150/300, lag0/5 and two completed price changes. Original
observed alpha1 and explicit calendar-zero alpha1 controls give 48 paired trials.
Calendar support is an assumption, not observed closed-market returns. This
differs from the selected-path ranks above; execution validation is required.
The combined fixed-history and causal-research regression run passed 50 tests.

```powershell
..\.venv\Scripts\python.exe -B -u -m backtest.provider_fixed_factors --opening-fixed-ranks
..\.venv\Scripts\python.exe -B -u -m backtest.provider_trials --opening-fixed-rank-screen
```

Preparation evidence is in `reports/provider_research/opening_fixed_rank_design.json`;
paired screening evidence is in `replication_trials/opening_fixed_rank/`.

Four exact-contract rank candidates completed autonomous replay through the fit
cutoff (28 February 2026). The best matched 30/120 fit entries with 87 extra
entries, below the geometric-volume incumbent's 40 matches and 76 extras.
These four candidates were rejected; see `opening_fixed_rank/fit_comparison.json`.

Two separate volatility interpretations are available for exact-contract ranks:
log returns between successive observed-clock quotes (including overnight gaps
when both prices are known), and rolling option-price standard deviation.
Missing quote rows are never filled or skipped. These alternatives require
known current CE and PE prices at the factor observation; the original adjacent
log-return variant retains its existing policy. Their caches and reports are
separate, and neither alternative is a confirmed provider formula.

```powershell
..\.venv\Scripts\python.exe -B -u -m backtest.provider_fixed_factors --opening-fixed-ranks --fixed-rank-volatility observed_log_return
..\.venv\Scripts\python.exe -B -u -m backtest.provider_trials --opening-fixed-rank-screen --fixed-rank-volatility observed_log_return
..\.venv\Scripts\python.exe -B -u -m backtest.provider_fixed_factors --opening-fixed-ranks --fixed-rank-volatility price_std
..\.venv\Scripts\python.exe -B -u -m backtest.provider_trials --opening-fixed-rank-screen --fixed-rank-volatility price_std
```

Each variant screens 48 paired alpha/alpha2 definitions. Only fit-selected
finalists should proceed to autonomous replay; conditional signal matches alone
do not establish actual entry or exit replication.

The observed-clock log-return variant completed all 240,000 selected-contract
rows and its 48-pair screen. Both selected finalists then completed the fit
replay: each matched 23/120 entries, with 85 and 89 extra entries respectively.
Both were rejected against the 40-match/76-extra incumbent. Evidence is in
`opening_fixed_rank_observed_log_return/fit_comparison.json`; per-source numeric
threshold checks are in `selected_source_alpha_diagnosis.csv` in that directory.
The latter are necessary signal conditions, not autonomous execution evidence.

Two additional, untested-in-history variants use the same preparation and
screen commands with `--fixed-rank-volatility adjacent_five_minute_log_return`
or `--fixed-rank-volatility adjacent_log_rms`. The former takes STD of overlapping
five-minute option log returns and requires all six endpoint/intermediate quotes
and five consecutive minute links. The latter uses square root of rolling mean
squared one-minute log returns without subtracting their mean. Each has a
separate 24-formula cache and 48-pair screen family. Independent numerical and
causality tests pass; that does not establish provider-trade alignment.

The price-STD variant also completed 240,000 rows and 48 paired screens. Its two
selected fit replays each matched 20/120 entries, with 88 and 90 extra entries,
and were rejected. See `opening_fixed_rank_price_std/fit_comparison.json`.
The separate prior-observation-only alpha1 rank control changed none of the
210 source direction-pass decisions; original alpha1 compatibility remained
201/210. See `prior_observation_rank/comparison.json`.

To prepare the two remaining volatility modes with shared quote loading:

```powershell
..\.venv\Scripts\python.exe -B -u -m backtest.provider_fixed_factors --opening-fixed-ranks --fixed-rank-volatilities adjacent_five_minute_log_return adjacent_log_rms
```

At most two variants share a preparation run. Formula calculations and output
caches remain independent; completed chunks resume separately. Numeric tests
verified equivalence to separate preparation and halved load/supplement calls
for a two-chunk fixture; this is not a measured full-job speedup.

Both remaining modes completed 240,000 rows and 48 paired screens each. Selected
five-minute volatility fit replays scored 26 exact/87 extra and 23 exact/83 extra;
RMS fit replays scored 27 exact/85 extra and 26 exact/83 extra. All four were
rejected against 40 exact/76 extra. Each family's `fit_comparison.json` records
the autonomous results; these cohorts were not promoted to full-history replay.

### Exact entry and exit candle audit

The targeted 840-leg-event audit recovered all 210 short and all 210 hedge entry
candles, 198 short exits and 150 hedge exits. Of 768 available exact-contract
candles, 760 published fills lie within the event range and 8 lie outside.
Remaining exclusions are 56 unsupported strike offsets, 14 after-expiry events,
and 2 outside-session events. There were no request failures. Earlier ATM-only
cache coverage limitations are superseded by this exact-strike audit.

Read `reports/provider_research/source_market_data_audit.md` and
`source_leg_candles.csv`. Event candles complete after the recorded timestamp;
they are diagnostic only. Preceding completed candles are stored separately,
and source fills do not enter signal calculations.

```powershell
..\.venv\Scripts\python.exe -B -u -m backtest.provider_research --source-candles
```

The separate discrepancy scan examined six anomalous events across their event
day and previous trading day. Both legs of the Sep29 2025 exit match ranges only
at Sep26 15:29; both legs of the Oct6 2025 entry match only at Oct3 15:29.
This supports investigating stale closing-price labels, without proving actual
execution timing or RMS liquidation. Oct6 has 51 unsupported fixed-leg minutes
in the event-day scan. See `source_fill_timing_summary.md` and
`source_fill_timing.csv` under the research report directory.

```powershell
..\.venv\Scripts\python.exe -B -u -m backtest.provider_research --source-fill-timing
```

### Rank after opening-ATM selection

The exact opening-selected contract download is complete across all 18 history
blocks: both option legs are available for 239,954 of 240,000 near/next rows.
Its separate 630-pair IV screen has positive exact CE and PE IV at all 210
published entries. This repairs the earlier opening-IV join coverage; it does
not prove the private formula uses implied volatility. Four distinct finalists
completed autonomous fit replay: IV level with native or geometric volume each
matched 28/120 entries with 95 extras; rolling IV STD300 matched 28 with 90 extras;
rolling IV mean60 matched 22 with 96 extras. All four were rejected against
40 exact/76 extra. See that family's `fit_summary.md` and `fit_comparison.json`.

```powershell
..\.venv\Scripts\python.exe -B -u -m backtest.provider_fixed_factors --opening-full-fields
..\.venv\Scripts\python.exe -B -u -m backtest.provider_trials --iv-opening-full-screen
```

Coverage and candidate evidence are in `opening_full_fields_design.json` and
`replication_trials/implied_volatility_opening_complete/` under the research
report directory. Missing or conflicting exact quotes remain unknown.

The selected-raw observed-log-return finalists completed fitting-period replay
with 26 exact/84 extra and 25 exact/86 extra entries. The adjacent-log-return
finalists scored 27 exact/84 extra and 26 exact/85 extra. All four were rejected
against the incumbent's 40 exact/76 extra; their separate `fit_comparison.json`
files preserve these results. The selected-raw option-price STD finalists also
completed fit replay: 22 exact/93 extra and 21 exact/93 extra, and were rejected.
These are fitting-period scores, not full-history replication counts.

The independent alpha1 audit identifies nine published entries where the
observed-bar 800-rank formula fails its required direction threshold, including
several substantial disagreements. All 18 entry-leg fills for those nine trades
lie inside the corresponding exact event-candle range. This does not establish
the causal indicator value, but the previously identified stale-price cases do
not explain these failures. Read `alpha1_unresolved_entry_checks.md` in the
replication report directory. Changing alpha2 alone cannot fix that AND gate;
the calendar-zero alpha1 alternative remains an explicitly assumed control.

A separate option-OHLC volatility screen tests 1,134 paired definitions using
intrabar option-return STD and high/low or OHLC range estimates. It uses exact
opening-selected contracts at each completed minute, preserves native volumes,
and keeps missing, zero or incoherent candles unknown. Rolling estimates follow
the selected ATM path; they are not each fixed strike's full history. These are
additional interpretations of the unspecified volatility denominator, with
observed and explicitly assumed calendar-zero alpha1 controls.

```powershell
..\.venv\Scripts\python.exe -B -u -m backtest.provider_trials --opening-ohlc-screen
```

The range formulas are based on [Parkinson's paper](https://www.cmegroup.com/trading/fx/files/michael_parkinson.pdf)
and the practical estimator in [Garman and Klass's paper, equation 19a](https://www.cmegroup.com/trading/fx/files/a_estimation_of_security_price.pdf).
Their use on minute option candles is a research hypothesis. Screening and
replay evidence belongs in `replication_trials/opening_ohlc_volatility/`.

The OHLC screen and four autonomous fit trials are complete. The best new fit
tradeoff (Garman-Klass300, total-volume ratio baseline20, lag5) matched 39/120
entries with 73 extras. Full-history continuation then matched only 74/210
entries, with 126 extras and 17 matching exits, versus the incumbent's 81/126/21.
The start-flat September–October week took three trades and matched only one
of the two published entries, with no matching exits. The candidate was rejected
as a replacement. Read that family's `validation_summary.md` and numeric
`selected_source_alpha_diagnosis.csv`; 75 combined research regression tests pass.

### Own-contract OHLC factors before ATM selection

The next comparison computes volatility and volume from each fixed expiry/strike
on the common observed decision clock, applies the factor lag within that
contract, then selects opening ATM. Alpha2 is ranked after selection using
continuous-near and separate-expiry histories. The separate screen covers 864
pairs, including original observed and explicitly assumed calendar-zero alpha1.

```powershell
..\.venv\Scripts\python.exe -B -u -m backtest.provider_fixed_factors --opening-fixed-ohlc
..\.venv\Scripts\python.exe -B -u -m backtest.provider_trials --opening-fixed-ohlc-screen
```

Preparation requests only supported historical offsets needed by market-selected
contracts' trailing 305 clock slots. It also reconstructs 330 prior slots from
their original dated payloads, including offsets newly needed at a chunk boundary.
Near-expiry offsets are limited to ±10 and next-expiry to ±3. Wider or unknown
histories remain unknown. Missing quotes are not compressed into shorter windows.

For bounded preparation add `--ohlc-limit-blocks 1`: this processes one **new**
block per invocation and resumes existing blocks. `--ohlc-offline` can inspect
available history; an online run retries chunks with missing offline payloads.
Screening rejects incomplete preparation and missing expected opening labels.

The first block is complete: 15,000 rows and 108 factors, with 12,649 known
intrabar-STD300/native-volume/baseline10/lag0 factors and 12,579 known
Garman-Klass300/total-volume/baseline20/lag5 factors. The latter is known at all
five source entries in that block. Preparation is now complete for all 18 blocks
and 240,000 opening labels; these are coverage results, not new trade matches.
90 combined research tests
passed, including own-contract lag, missing slots, historical request scopes,
exact resume, overflow handling and offline-to-online recovery.

Factor computation now keeps only each contract's contiguous clock range needed
by its selected minutes, retaining missing slots and all 304 prior slots. On the
first block's 66 contracts, all 108 selected factors and NaN masks matched the
original calculation and saved CSV exactly. One measured factor-computation pass
took 4.43 seconds versus 5.43 seconds (1.23× speedup). This excludes downloading,
cache loading and report writes; it is not a whole-run speedup. Evidence is
`replication_trials/fixed_ohlc_clock_trimming_benchmark.json`.

Preparation evidence is `opening_fixed_ohlc_design.json`; generated factors stay
in the ignored historical cache. Screening and replay evidence belong in
`replication_trials/opening_fixed_ohlc/`. Strategy defaults are unchanged.

The 864-pair screen is complete. Its conditional fit leader is
`a2a3173032ddb966`: Parkinson300, total-volume ratio with baseline20, factor lag5,
separate-expiry rank and observed alpha1. It has 46 conditional first-entry
alignments, which require autonomous replay before comparison with actual trade
matches. Across all factors and rank contexts, alpha2 is known at 172–188 of the
210 source entries. Four saved finalists span Parkinson, intrabar standard
deviation, Garman-Klass and continuous versus separate-expiry ranking; their
selection uses fit scores only. See `fit_stage_selection.json` and
`source_factor_rank_coverage.csv` in that experiment directory.

All four autonomous fit replays are complete through 10 committed blocks. Scores
include entries only through 28 February 2026 (120 published trades), excluding
March entries in the tenth block. Intrabar-STD separate-expiry achieved 29 exact
entries and 81 extras; Parkinson and Garman-Klass each achieved 28/81; continuous
intrabar-STD achieved 23/84. Each is worse than the independently rechecked
reference's 40/76, so these finalists are rejected without full-history promotion.
`fit_comparison.json` and `fit_summary.md` hold the comparison;
`selected_source_alpha_diagnosis.csv` holds 840 numeric source-entry checks,
which are necessary signal conditions rather than autonomous trade matches.

An additional experiment takes volume/volatility factors and their lag from
the currently selected contract's own history, then ranks the selected raw
alpha2 series. This differs from shifting the previously selected ATM path and
from ranking separately within each fixed strike before selection. Each mode
screens 96 pairs using existing caches, across continuous-near and per-expiry
rank contexts. Only the final 12 candidate archives are written. Independent
chronology, missing-data and causality tests pass; autonomous replay is required.

```powershell
..\.venv\Scripts\python.exe -B -u -m backtest.provider_trials --opening-fixed-selected-raw-screen --fixed-rank-volatility adjacent_five_minute_log_return
..\.venv\Scripts\python.exe -B -u -m backtest.provider_trials --opening-fixed-selected-raw-screen --fixed-rank-volatility adjacent_log_rms
```

The geometric-volume finalist completed the full history with 81/210 exact
entries, 126 extra entries and 21 matching exits when its profit target was
disabled. It generates five entries in the September–October comparison week,
so it is not a replica. The detailed results and fit changes are in
`bulk/final_grid_fit_summary.md`.

Separate research controls allow one flat evaluation after an actual exit at
the same decision minute, using the same completed indicators and fresh
nearest-expiry quotes. This tests published same-minute exit/entry sequences;
it does not supply intraminute prices or change the live runner's cadence.
The mode has its own candidate identity and resumable checkpoint. Decision CSVs
may contain both an exit and an entry evaluation at the same minute in this mode.
Both sequencing controls have now completed the full history and were rejected:
they improve fit entries by one but fall to 77/210 exact entries later. Complete
comparison evidence is in `bulk/reentry_summary.md`; live cadence remains unchanged.

```powershell
..\.venv\Scripts\python.exe -B -u -m backtest.provider_autonomous --family bulk --frontier-name reentry_frontier --batch-finalists 2 --limit-blocks 10
```

```powershell
..\.venv\Scripts\python.exe -B -u -m backtest.provider_trials --premium-gates
..\.venv\Scripts\python.exe -B -u -m backtest.provider_trials --family eligibility --replay-top 1
..\.venv\Scripts\python.exe -B -u -m backtest.provider_autonomous --family eligibility
..\.venv\Scripts\python.exe -B -u -m backtest.provider_trial_report --family eligibility
```

### Recency-weighted option volatility control

One matched experiment replaces the reference's summed CE/PE log-return STD150
with a bounded exponential sample STD over the same 150 clock slots. Weights are
`(149/151)^age`; the variance denominator is `sum(w)-sum(w²)/sum(w)`. Both models
require 120 valid returns and retain gaps at their original ages. Opening ATM,
geometric volume1/baseline10, factor lag5, alpha800, beta300/min270, strict
thresholds and execution rules are unchanged. The original clock and float64
alpha/alpha2 control arrays reproduce exactly, including missing values.

```powershell
..\.venv\Scripts\python.exe -B -u -m backtest.provider_trials --weighted-volatility-screen
..\.venv\Scripts\python.exe -B -u -m backtest.provider_autonomous --family weighted_volatility --candidate 3164e36da6d12a81 --limit-blocks 10
```

The weighted candidate's actual fit replay scored 31 exact entries and 83 extras,
worse than the original reference's 40/76. It is rejected without full-history
promotion. The uniform control is compared against its existing committed replay;
no checkpoint outcomes were copied. All 49 trial tests passed, including direct
weighted calculations, retained gaps, prefix causality and exact-control checks.
Evidence: `replication_trials/weighted_volatility/fit_comparison.json` and its
210-row paired source-entry diagnostics.

### Signal failures versus execution state

The complete reference replay matches 81 of 210 entries, with 126 extras and
21 matching exits. At 164 source entries its two indicator direction conditions
both pass. Of the 129 missed entries, 46 fail a signal condition or have an unknown
indicator; 62 have aligned signals while a simulated position is held; 18 have
aligned signals while a time exit is due but valid held-contract quotes are
missing. The remaining three aligned cases record a stop exit, time exit and
short-premium rejection respectively. Thirty-three aligned missed entries have
missing held-contract quotes at that minute; this overlaps the groups above.

`replication_trials/baseline_source_entry_gate_audit.csv` records all 210 source
entries joined to the saved indicator bank and committed replay decisions;
the matching JSON gives counts. This diagnoses the model's actual decisions,
not the provider's undisclosed triggers. Changing a preceding exit is not proof
that the subsequent source trade would then be reproduced. No position resets,
timestamp changes or inferred broker liquidation events were introduced.

### Paired rank-clock experiment (7 October 2026)

The matched nine-pair experiment changes alpha's 800-minute and alpha2's
300-minute rank support while retaining the best replication baseline's raw
signals and no-target execution. Supports are observed trading candles, elapsed
calendar minutes with minimum 20 actual observations, and elapsed minutes with
an explicit closed-market zero-input assumption. Missing traded inputs stay
unknown. Run the screen with `python -m backtest.provider_price_bounds
--calendar-rank-pairs`; independent replay inputs are saved in
`reports/provider_research/replication_trials/calendar_rank_pairs/`.

Initial conditional screen: zero-input support for both ranks passes 204/210
published entry directions, versus the control's 164/210, but fit-period
first-entry agreement falls from 50 to 12 and extra signal minutes increase.
These are signal diagnostics, not reproduced trades or profit evidence.
All eight changed combinations completed independent fit-period replay. The
best reproduced 36/120 fit entries with 80 extras, versus the control's 40/120
with 76 extras. Its gross realized profit through 24 March was ₹382,289 versus
₹342,940.75 for the control after the observation-cutoff correction. No variant
improves exact entry matching; none is promoted as a Zen replica.
All trial statistics and monthly values are in `calendar_rank_pairs/fit_summary.md`
and `fit_performance_monthly.csv` under the trial reports directory.

### Volatility-definition experiment (7 October 2026)

`python -m backtest.provider_trials --volatility-definition-screen` tests a finite
64-pair bank: eight volatility definitions, 150/300 candles, zero/five-candle
factor lags, and original/closed-market-zero alpha rank support. The original
STD150 definition exactly reproduces the saved control. Unknown inputs remain
unknown; no future observations enter any definition.

Eight conditional fit leaders are retained. Autonomous fit replays initially
test the three leaders plus the remaining candidate with the most fit-period
direction passes: price coefficient of variation at 150/300 candles, summed
log-return variance at 300, and mean absolute log return at 300. Selection uses
fit labels only; later diagnostic scores do not determine that shortlist.
The variance finalist retained 40 exact fit entries while reducing extras to 68.
Its full replay produced ₹785,704.25 gross realized profit and 73/210 exact
entries; it is separately implemented as Strategy 02 for performance research.
Outputs and per-trial performance are in `replication_trials/volatility_definitions/`.
A conditional screen alone never establishes replication or performance advantage.

### Observation-age weighted alpha ranks

The six fixed alpha-rank kernels keep the completed five-bar return and
800-observation support unchanged. Exponential half-life 800 passes 202 of 210
necessary source alpha conditions, versus 201 for the uniform control. It repairs
the 12 September 2025 entry but still fails eight other entries; this is insufficient
for replication. The evidence is in `replication_trials/weighted_alpha_rank/`.

Four matched uniform/weighted alpha and alpha2 pairs retain the original raw
geometric-volume/log-return-volatility inputs. The three changed candidates are
replayed independently in `replication_trials/weighted_rank_pairs/`; each committed
replay includes trades, monthly P&L, win rate, CAGR and trailing returns. These
research hypotheses have not changed either named strategy or the service default.

Full validation of the fit-selected weighted-alpha/original-alpha2 pair completed:
82/210 exact entries, 22 matching exits and 125 extras, versus the control's
81 entries, 21 exits and 126 extras. Its gross profit is INR623,346; fresh
28 September–1 October replay loses INR22,317.75 realized and matches only one
of two source entries. The additional exact entry is 12 September 2025: alpha
changes from 0.205 to 0.198335, crossing the strict bearish threshold; alpha2
remains 0.096667. Eight necessary alpha conditions still fail. Evidence and all
monthly statistics: `replication_trials/weighted_rank_pairs/summary.md`.

Trailing-return centering was also tested with fixed mean/median windows
30/60/150/300/800 and lag 1/5. Twenty uniform-rank variants pass at most
198/210 necessary alpha conditions (control 201); twenty weighted-rank variants
pass at most 199/210 (control 202). Neither family improves its control.
These are rejected signal screens, with no new backtest performance claim.
Per-trade evidence is in `replication_trials/return_innovation_alpha/` and
`replication_trials/weighted_return_innovation_alpha/`. Both named strategies
remain unchanged.

### Weighted alpha with alternative alpha2 volatility

The weighted alpha was paired with 32 fixed volatility definitions. Four fit
replays completed; variance300 preserved 41 exact fit entries while reducing
extras from 75 to 67. Full validation did worse on matching: 74/210 entries,
24 matching exits and 121 extras, versus the weighted-STD control's 82 entries,
22 exits and 125 extras. It gained 18 source entries but lost 26 others.

Gross full-history profit was INR785,449.25, INR255 below Strategy02; win rate
57.73%, CAGR equivalent173.52%, trailing1/3/6m -2.32%/9.32%/78.27%.
The fresh recent-week replay matched one of two Zen entries and lost INR7091.50
realized. Keep both named strategies unchanged. All four trial statistics,
monthly P&L and causal factors at every source entry are retained in
`replication_trials/weighted_alpha_volatility_definitions/summary.md`.

### Shared input dataframe/drop policies

22 alpha clocks and six paired preprocessing policies were screened. Removing
329 unavailable option-input rows before constructing and ranking the return
lets alpha pass 203/210 necessary conditions, versus 201 for price-only and 202
for weighted price-only. It repairs the alpha boundary at 26 December 2025 and
24 July 2026, but alpha2 still fails at both entries (0.356667 and 0.763333).

Three common-period autonomous fit replays score 40/76, 39/76 and 38/77
exact entries/extras. None beats the weighted control41/75. The partial gross
profits through24March2026 are INR342940.75, INR352284.50 and INR352404.50;
these do not imply full October performance. Retain research only. Complete
statistics, monthly values and per-entry parameters are in
`replication_trials/complete_case_pairs/summary.md`.

### Persistent rank-state interpretation

36 fixed state hypotheses keep a bullish/bearish state after a raw rank exceeds
0.8 or falls below0.2, releasing toward the midpoint at0.5/0.6/0.7. Two controls
remain unchanged. Encoded0.9/0.1/0.5 gates represent states, not alpha ranks.
Midpoint alpha2 state adds nine necessary source conditions (174/210 versus165),
but actual fit replay gains three entries and loses five:39 matches80 extras.
Release0.6 and0.7 each score41 matches77 extras, worse than control41/75.

Partial gross profits9July2025–24March2026 are INR241118.25 (release0.5) and
INR288138.00 (release0.6/0.7). Reject these state replacements. Exact earlier
arming times, raw ranks, all three trial metrics and monthly P&L are in
`replication_trials/hysteresis_pairs/summary.md`. Named strategies stay unchanged.

</details>

## Performance reports for every backtest

Autonomous trial replays now save `performance.json` and
`performance_monthly.csv` alongside each trade ledger and include performance in
`report.json`. These show win rate, gross realized P&L, monthly P&L and returns,
CAGR equivalent, trailing calendar 1/3/6-month returns, profit factor, realized
drawdown and separate open-position MTM. Ordinary Dhan replays also distinguish
gross results from results after modeled order fees.

Rebuild summaries of existing committed backtests without rerunning them:

```powershell
cd zen_credit
..\.venv\Scripts\python.exe -B -u -m backtest.provider_autonomous --performance-report
```

The backfill covers valid checkpoint replays, recent-week replays
and ordinary backtests. One preserved invalid unresolved-settlement run
is excluded. The central research comparison contains separate observed periods,
a common period ending 24 March 2026, and the fit period ending 28 February.
Completed historical trials also have comparisons through 1 October.
Partial trials are not compared to Zen's later full-history profits.

Read `reports/provider_research/replication_trials/performance_summary.md`,
`performance_comparison.csv` and `performance_monthly.csv`. Research
comparison rows reconcile to their monthly P&L totals. Strategy 02
(`719c7c6bc176871c`) realizes INR785,704.25 versus published Zen's
INR893,286.75 on the same dates and INR320,000 base; realized drawdown is
33.48% versus 25.39%. A profitable alternative may still be evaluated independently
of replication; these metrics do not automatically promote a strategy.

P&L is booked on exit dates; source comparison uses published reported P&L.
Win rate excludes open trades. CAGR annualizes ending realized value over the
full inclusive observed period; position sizing remains on fixed capital.
Missing 1/3/6-month windows are unavailable, not zero. Open endpoint marks remain
unknown where unavailable. Realized drawdown excludes intratrade losses, costs
and actual historical broker RMS/margin behavior are incomplete, and later dates
were previously inspected. All 77 relevant trial/replay tests passed, including
calendar boundaries, future-exit censoring, carried positions, fees and monthly
report reconciliation fixtures.

## Verify the code

From `zen_credit/`:

```powershell
..\.venv\Scripts\python.exe -m pytest tests/ -q
```

Database tests use a temporary local PostgreSQL instance, with production database
credentials blocked. Keep these tests when editing strategy or execution code.
