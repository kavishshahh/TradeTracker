# Deploy automatic Dhan paper trading

## What runs

One continuously running Python background worker runs every registered strategy (`strategy/registry.py`); a strategy only enters when its catalogue record is enabled.
Every minute it obtains Dhan NIFTY index/option data, evaluates the strategies,
records virtual entries/exits in Firestore, and publishes each paper account to
`algo_paper_state`. The existing authenticated backend serves the records to
Algo Lab; its UI refreshes every 30 seconds. For production, Cloudflare triggers the API each minute; the standalone loop remains a local alternative.
The data provider has no order endpoints; real orders are sent only by the live desk (see Live trading below), and only for strategies the owner switched to live.

The strategy decisions, stops, targets and P&L marks are evaluated once per minute,
not on every tick. This worker polls Dhan REST quotes; it is not a WebSocket stream.
This preserves the existing one-evaluation-per-minute rules. Tick-based stops would
be a different execution model and would need separate validation.

## Configuration: two environments

- Frontend: existing TradeTracker root `.env` (or `.env.local`), with public Firebase
  configuration and `NEXT_PUBLIC_API_BASE_URL` pointing to the deployed API.
- Backend: `backend/.env`, shared by the existing Python API and paper worker.

The duplicate `algos/.env.example` was removed. `backend/env.example` is only a
template, not a third runtime environment. The worker and historical client now
load `backend/.env`; hosting environment variables take precedence.

Dhan credentials, in one of two modes:

```dotenv
DHAN_CLIENT_ID=your_client_id
# Automatic (recommended): the worker generates and renews its own 24-hour token.
DHAN_PIN=your_6_digit_dhan_pin
DHAN_TOTP_SECRET=base32_setup_key_from_dhan_totp_setup
# Manual: a token pasted from Dhan Web, which expires after 24 hours.
DHAN_ACCESS_TOKEN=your_access_token
```

Automatic mode (`data/providers/dhan_auth.py`): set up TOTP once under Dhan Web > DhanHQ Trading
APIs > Setup TOTP, and save the base32 key shown next to the QR code as `DHAN_TOTP_SECRET` (the same
key your authenticator app uses). The worker calls Dhan's `POST https://auth.dhan.co/app/generateAccessToken`
when it has no token, 30 minutes before expiry, and once after Dhan rejects a token. A failed
generation pauses further attempts for 15 minutes, so a wrong PIN or key cannot hammer the login and
lock the account; the error then appears in the paper status as a data error. The PIN and key give
full account login, so keep them only in the hosting provider's secret environment variables. Orders
also require Dhan's static-IP whitelist and the live desk's own switches (see Live trading below). Generating a token on
another machine (for example a local research replay with the same credentials) may invalidate the
worker's token; the worker then regenerates on its next rejected request.

Keep the existing Firebase service-account credential in the backend environment:
`FIREBASE_SERVICE_ACCOUNT_JSON` (or its existing local service-account file path).
It is needed to persist the paper accounts, not to connect to Dhan.
Strategy formula settings are pinned in versioned Python. Model capital is read
from each Firestore catalogue record when the worker starts that strategy.
Changing capital requires a worker restart; do not change it midway through an
open position if you want comparable statistics. The standalone loop needs no cron secret; the Cloudflare/API deployment needs one shared scheduler secret. SMTP settings, strategy selectors and database URLs are optional or unnecessary.

## Live trading

**Status: switched off.** Since 22 Nov 2026 only paper and dry run exist. `LIVE_ORDERS = False` in
`execution/broker.py` makes the real broker client impossible to construct and its `place` refuse, and
the desk treats a stored `live` mode as `off`; `LIVE_TRADING_AVAILABLE = False` in `backend/algos_api.py`
makes the API refuse to save `live` and the page offer only Off and Dry run. No environment variable or
page setting can turn orders on: going live means changing both constants in code, then steps 1 to 3
below. `tests/test_live.py::test_as_shipped_no_order_can_reach_dhan` pins this. The rest of this section
describes the order flow as built, which today runs only against the simulated dry-run broker.

`execution/live.py` (the live desk) mirrors a strategy's paper position with real Dhan orders through
`execution/broker.py`. The paper engine stays the only decision maker: paper enters, the desk enters the
same spread at the owner's deployed capital; paper exits, the desk exits. Nothing is sent unless all of
these hold:

1. The owner set the strategy to **Live** in Algo Lab > Live (stored in Firestore `algo_live/account`),
   with a capital between 1,20,000 and 3,20,000.
2. The backend environment has `LIVE_TRADING_ENABLED=true`. Without it a live strategy's entries are
   skipped and reported. **Dry run** needs neither this nor a static IP: it runs the same flow against a
   simulated broker that fills at the live bid/ask, and records the slippage versus the paper price.
3. The server's outbound IP is whitelisted in Dhan (Dhan Web > DhanHQ Trading APIs, or
   `POST /v2/ip/setIP`). Dhan requires an IP unique to the account and allows one change every 7 days.
   A host that shares its outbound addresses with other customers does not qualify; an order from an
   unlisted IP comes back as a rejection, which the desk reports as a failed entry.

What the desk does (each case has a test in `tests/test_live.py`):

- **Sizing**: lots come from the strategy's own rules applied to the deployed capital (margin estimate,
  the Monday allocation, the per-stop loss cap), further capped by the owner's maximum lots. The paper
  account keeps its 3,20,000 model capital.
- **Entry**: funds are checked against the estimated margin, then the hedge is bought and the short leg
  sold, both as limit orders at the touch. An entry that would give up more than the slippage cap
  (default 3 points of credit) is skipped. A short leg that is rejected or does not fill has its hedge
  sold back and the entry recorded as failed with its cost.
- **Exit**: the short leg is bought back first, with the limit widened each attempt and a market order
  last, retried every minute until done; then the hedge is sold. A hedge nobody bids for is left to
  expire after three minutes and tracked. An expired trade is booked at intrinsic value.
- **Restarts and timeouts**: the trade and each order's correlation id are stored before the request is
  sent. A request with no answer is looked up by that id on the next cycle, never re-sent blindly. A
  live trade whose paper position is gone is closed on the next cycle, however the exit minute was missed.
- **Account checks**: every minute with a live trade open, the desk checks that Dhan still holds at
  least the quantities its trades need; a shortfall lasting two rounds blocks new entries and alerts. The
  kill switch and the daily loss limit block new entries; open trades still exit. "Exit now" closes a
  live trade while paper holds.
- **Shared account**: the kill switch, loss limit and exit buttons are the desk's own (Firestore) and
  act only on its trades. It never calls Dhan's kill switch, P&L exit or exit-all-positions APIs, and
  only places, reads and cancels orders carrying its own tag, so algos run from Dhan's portal and manual
  trades are not touched. They do share the account's funds: keep enough for both, or one side's entries
  will be refused for margin.
- **Alerts**: entries, exits, skips, failures, unfilled exits and mismatches are logged, shown in
  Algo Lab > Live, and emailed when `EMAIL_ENABLED=true` with SMTP settings.

Not covered: brokerage and taxes are not in the desk's P&L; there is no stop order resting at the
exchange, so if the worker is down a stop is acted on only when it is back (the Live tab shows the desk
as stale after three minutes without an update); evaluation stays once a minute. Before real money, run
dry run for some days, then one lot live and compare the fills. The order code has been tested against
a fake broker only, never against Dhan's order API.

## Local check

From the TradeTracker root:

```powershell
.\algos\.venv\Scripts\python.exe -B algos/zen_credit/paper_worker.py --check-data
```

This reads Dhan data only, without creating paper trades or writing to Firestore.
During market hours it also checks live options and exchange timestamps.

Start the persistent worker:

```powershell
.\algos\.venv\Scripts\python.exe -u algos/zen_credit/paper_worker.py
```

Keep the terminal running for local testing. Ctrl+C stops it. Open `/algos`, sign
in with the existing account, select Paper feed, and verify evaluation timestamps.

## Production: Cloudflare scheduler + existing backend

Use [cloudflare-scheduler/README.md](cloudflare-scheduler/README.md).
Cloudflare Free calls the protected endpoint in the existing Python API every
minute during the exchange session. The API hosts the same shared evaluator and
stores paper results in Firestore. No separate paid Render background worker is
required. Dhan/Firebase settings remain in the backend environment; one shared
`PAPER_SCHEDULER_TOKEN` authenticates the Cloudflare scheduler.

Do not run the local continuous worker and the cloud scheduler against the same
accounts at the same time. Existing backend costs, cold starts and availability
still apply. All evaluations and stops are minute-based.

## History, outages and credentials

- Chain snapshot history is held once per process (`SnapshotHistory`), shared by every
  strategy, as one compact frame covering `SNAPSHOT_HISTORY_DAYS`. A cold start streams
  that window from Firestore once; afterwards each minute's rows enter the cache from the
  process's own saves, so steady-state cycles read no snapshot documents. The dashboard's
  closed ledger is re-read only after a position closes. This keeps a 512MB instance
  well under its limit and the free-tier read quota intact across restarts.
- Price alpha is bootstrapped using completed Dhan index candles. Alpha2 builds
  same-contract minute option-price/volume history in Firestore. On a new account,
  allow multiple trading sessions for all rolling inputs to become valid. Missing
  data is not filled and no trade is forced during warmup.
- REST cumulative-volume snapshots are not identical to archived native one-minute
  option candles; live/backtest parity has not been established. Overnight/gapped
  changes and stale quotes are excluded rather than used as fabricated volume.
- Instrument IDs, expiries and lot sizes come from Dhan. Only the holiday calendar
  still uses official NSE holiday metadata; no NSE/Yahoo live prices are fetched.
  Failure to obtain usable calendar/data prevents a trade and appears in status/logs.
- Firestore positions survive restarts. Leases, signal IDs and minute claims prevent
  duplicate simulated entries. Missing held-leg data can delay a paper exit; watch
  stale marks and errors. Expired contracts are not priced using invented settlement.
- Dhan Web-generated access tokens normally last 24 hours. Replace the token in the
  shared backend environment and deploy/restart the worker before it expires. Updating
  a local `.env` does not update Render. Automated token renewal/login is not implemented.
- This is paper-only with gross P&L and estimated margin. It is not the recovered
  Zen Credit implementation and does not simulate real broker RMS liquidation.

Official references:
- https://render.com/docs/background-workers
- https://render.com/docs/configure-environment-variables
- https://dhanhq.co/docs/v2/market-quote/
- https://dhanhq.co/docs/v2/historical-data/
- https://dhanhq.co/docs/v2/authentication/
