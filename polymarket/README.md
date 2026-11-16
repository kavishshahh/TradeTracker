# Polymarket Algos (private, paper only)

A separate section from Algo Lab. It shares no code, styles, Firestore collections or scheduler
with the Indian-market algos in `algos/` and `frontend/`. It does use the same Firebase service
account (read from `backend/.env`) and writes only to the `poly_*` collections. There is no wallet, key or
order-placement code anywhere in this folder.

## What is where

| Piece | Location |
|---|---|
| Feed-driven paper trader | `polymarket/worker.py`, `feed.py`, `store.py`, `pmq/` |
| Strategies | `polymarket/pmq/strategies/` (`crypto_fair_value`, `sports_pregame_underdog`, `updown_leader_3m`, `updown_leader_early`, `updown_latency_2bp`, `updown_latency_1bp`, `copy_substantial_service`, `copy_c8b9_politics`, `copy_goool_esports`, `copy_6e82_nba`, `long_dated_no`) |
| Copy trading | `polymarket/copy_algo.py` (watches Polymarket's live activity feed for copied wallets, paper fills against the book at the copy order's arrival time), wallets in `pmq/strategies/copy_wallet.py` |
| Latency rule and probe | `polymarket/latency_algo.py` (paper fills against the book at the order's arrival time), `latency.py` (network delay probe, every 10 minutes) |
| Research scripts | `polymarket/research/` |
| Page and nav hook | `polymarket/frontend/`, route `src/app/poly-algos/page.tsx` |
| API (read-only) | `backend/poly_api.py` → `GET /poly/access`, `GET /poly/paper`, `GET /poly/trades` |
| Tests | `backend/test_poly_api.py` |

Two shared app-shell files carry a small addition each: `backend/main_firebase.py` registers the
router, and `src/components/Layout.tsx` shows the nav item when `/poly/access` says so.

## Who can see it

Decided by Firestore, not code: document `feature_access/polymarket_algos`, field `emails`.
A signed-in user sees the section only if their verified email is in that list. Everyone else gets
no nav item, and the data route answers 404. Edit the list in the Firebase console or with:

```powershell
.venv\Scripts\python.exe seed.py --grant someone@example.com
.venv\Scripts\python.exe seed.py --revoke someone@example.com
```

The API re-reads the list within a minute; the browser remembers the answer for the session.

## Running the paper trader

```powershell
cd polymarket
python -m venv .venv; .venv\Scripts\python.exe -m pip install -r requirements.txt   # once
.venv\Scripts\python.exe -u worker.py                       # runs until Ctrl+C; resumes from Firestore
.venv\Scripts\python.exe -u worker.py --dry --seconds 60    # test run, writes nothing
```

Locally it uses the Firebase service account already in `backend/.env`; on a host, set
`FIREBASE_SERVICE_ACCOUNT_JSON` instead. It is one long-running process, so it needs a machine
that stays on.

Only one copy trades at a time. The running copy holds a lease in Firestore (`poly_worker/lease`),
renewed with each heartbeat. Any other copy logs "another worker ... is running" and waits. A
clean stop (Ctrl+C, or SIGTERM from a host) saves the accounts and releases the lease, so a
waiting copy takes over within about 10 seconds. If a copy dies without stopping cleanly, the
lease expires after 5 minutes.

## Running on Render (background worker)

Create a Background Worker from this repository with:

| Setting | Value |
|---|---|
| Language | Python 3 |
| Branch | `main` |
| Root Directory | `polymarket` |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `python -u worker.py` |
| Instance type | Starter (0.5 CPU, 512 MB) |

Environment variables:

- `PYTHON_VERSION` = `3.11.9` (the version the worker is tested on)
- `FIREBASE_SERVICE_ACCOUNT_JSON` = the same value the backend service uses (secret)

With Root Directory set, only changes inside `polymarket/` redeploy the worker. During a
redeploy Render starts the new instance before stopping the old one; the new one waits on the
lease until the old one has saved and stepped down. Stop the copy on your PC once the Render one
shows "lease acquired" in its logs, or the PC copy keeps the lease and Render waits.

How it reacts:

- Only markets near a trade are streamed. Every 3 minutes the worker scans the full market list (about 800 crypto and 180 sports markets, each with its current quotes) and opens live feeds only for the shortlist plus held positions. A market that becomes interesting between scans is picked up at the next one.
- Polymarket order-book WebSocket: a change in a watched market's best price re-evaluates it immediately.
- Binance price WebSocket: a 0.05% move re-evaluates every watched crypto market (at most every 5 s).
- Fills are simulated against the live ask ladder with real taker fees and the 5-share minimum,
  and saved to Firestore at once. A heartbeat with marks is saved every 2 minutes.
- No stream exists for these, so they refresh on a timer: the list of open markets and the shortlist (3 min),
  hourly candles for the volatility estimate (10 min), and resolution of held markets (2 min).
- Copy algos: Polymarket's live activity WebSocket (`wss://ws-live-data.polymarket.com`, every trade on the exchange with the trader's wallet) triggers a copy as soon as a copied wallet buys. Each copy opens a short book connection for that token and fetches the market's settings once (`clob-markets/{condition_id}`).
- 5-minute BTC/ETH up/down markets are always streamed (the current window and the next two) and re-checked every second, because time left is part of the rule. They are found by their fixed slugs (`btc-updown-5m-<start>`), not by the scan.
- If the book feed goes quiet for 45 s, trading pauses until it reconnects and re-snapshots.

Paper account rules: $25 per strategy, at most 12 open markets, 80% of the bankroll in play, one
position per event. Bets are about $1.50–2.50; when the price is above ~50c the bet is raised to
what 5 shares cost (the minimum for the scan-based algos), so up to about $4. Entries are paced:
2 new positions per 10 minutes for the scan-based algos, 8 for the up/down algos. Up/down bets
use the $1 minimum that applies to marketable orders.

## Firestore

- `poly_paper_state/{strategy}`: account, open positions, last 150 fills, last 300 settled bets, equity curve, feed status
- `poly_paper_trades/{id}`: every paper buy and settlement, one document each, never trimmed (`GET /poly/trades`, CSV export on the page)
- `poly_catalog/{strategy}`: backtest summary (`seed.py --catalog`, from `backtests/*.json`)
- `feature_access/polymarket_algos`: allowed emails

Writes: about 2,900 a day from heartbeats (four algos, one save every 2 minutes each), plus two
writes per paper bet and per settlement. The up/down algos can add a few thousand on a busy day.
The free tier allows 20,000 a day, shared with the main app.

## Algos

| Algo | Markets | Rule | Backtest |
|---|---|---|---|
| `crypto_fair_value` (v2) | BTC/ETH/SOL/XRP "dip to / reach / above / between" | Buy NO when it is 15+ points cheap under both the calmest and hottest recent volatility; max 2 bets that lose on the same move | +53% per bet held out (optimistic: hourly trade prices) |
| `long_dated_no` | Yes/No markets, 30+ days to the scheduled end, no sports | Buy No when Yes is 35-65c and the No spread is 3c or less; one bet per event, $2, held to resolution. Paper account of $1,000 so a few hundred bets can be open at once | +5c a share at real trade prices (551 events, Apr-Nov 2026), +6c in an unseen earlier year (666 events); mostly pre-fee, not yet tested at live bid/ask |
| `sports_pregame_underdog` | Match-winner markets, 10-240 min before start | Buy the side priced 10-40c | +25% per bet held out, ~0% in the tuning period |
| `updown_leader_3m` (v2) | BTC/ETH 5-minute up/down | Last 3 minutes; a real trade at 70-90c in the last 10 s and the ask within 3c of it | see `backtests/` |
| `updown_leader_early` (v2) | BTC/ETH 5-minute up/down | Same, any time after the first 15 s | see `backtests/` |
| `copy_substantial_service` | Whatever wallet 0x2c33...0563 buys (mostly sports, half in-play) | Its first buy of $20+ under 97c in each market: limit at its price +2c, arriving 350 ms after the trade shows on the live feed plus the market's in-play delay (`sd`) or 250 ms (`itode`); fills only at the asks there then; held to resolution. $1.50 a bet, at most 15 open markets | wallet: +$6.1M on $1.44B volume (~0.4%) |
| `copy_c8b9_politics`, `copy_goool_esports`, `copy_6e82_nba` | Wallets 0xc8b9...b836 (politics, holds weeks), 0xda3a...381f (CS2/LoL pregame), 0x6e82...752c (NBA pregame) | Same copy rule, first buy of $5+ per market; politics account $1.10 a bet, up to 18 open markets | copy backtest on 80 first entries each, price 10 min later +1c: +61% / +28% / +24% per bet (wide error bars, picked for looking good) |
| `updown_latency_2bp_real` | BTC/ETH 5-minute up/down | The 2 bp rule with a 350 ms order delay, the figure measured on real orders | first live test, 16 Nov 2026 |
| `updown_latency_2bp`, `updown_latency_1bp` | BTC/ETH 5-minute up/down | Binance perp moves 2 bp (or 1 bp) in 200 ms: buy the matching side with a limit at the ask seen; the simulated order arrives 100 ms later and fills only if that ask is still there (`latency_algo.py`) | tick research, see `research/README.md` |

Paused (`halted = True` on the class): all of them except the four `copy_` algos (added 17 Nov 2026). The three `updown_latency` algos were paused on
16 Nov 2026 after a real-order test: Polymarket holds taker orders on these markets for 250 ms, so the
quotes the paper accounts assumed are gone before a real order is matched. Also paused: `crypto_fair_value`,
`sports_pregame_underdog` and both `updown_leader` algos. They place no new bets; open bets still settle.

### Versions

When an algo's rules change, bump `account_version` on its class. On the next start the worker
archives the old account to `poly_paper_archive/{algo}_v{n}`, starts a fresh $25 account, and
records the old result in the new account's `previous` list (shown on the page). Ledger rows carry
`version`; the page counts only the current version, the CSV export has everything.

Version 1 results (14-15 Nov 2026): up/down 3m -$18.63 after 50 bets (66% won), up/down early
-$15.21 after 55 (64%), crypto -$18.40 after 6 (0 won). Causes and fixes are in each strategy
file's docstring; the analysis scripts are in the research folder (`analyze_forward*.py`,
`updown_variants.py`, `crypto_robust.py`).
