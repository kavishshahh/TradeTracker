# Deploy automatic Dhan paper trading

## What runs

One continuously running Python background worker runs both saved strategies.
Every minute it obtains Dhan NIFTY index/option data, evaluates the strategies,
records virtual entries/exits in Firestore, and publishes each paper account to
`algo_paper_state`. The existing authenticated backend serves the records to
Algo Lab; its UI refreshes every 30 seconds. No browser or cron trigger is needed.
No Dhan order endpoints exist in the live provider.

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

Only these new credentials are needed for Dhan:

```dotenv
DHAN_CLIENT_ID=your_client_id
DHAN_ACCESS_TOKEN=your_access_token
```

Keep the existing Firebase service-account credential in the backend environment:
`FIREBASE_SERVICE_ACCOUNT_JSON` (or its existing local service-account file path).
It is needed to persist the paper accounts, not to connect to Dhan.
Strategy formula settings are pinned in versioned Python. Model capital is read
from each Firestore catalogue record when the worker starts that strategy.
Changing capital requires a worker restart; do not change it midway through an
open position if you want comparable statistics. No cron secret, SMTP settings,
strategy selector or database URL is required for this worker.

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

## Production: Render background worker

1. Commit/push the updated TradeTracker source to the connected Git repository.
   Do not commit `.env`, service-account files, local venvs, caches or logs.
2. Deploy the updated existing dashboard/API as usual. Set the frontend's
   `NEXT_PUBLIC_API_BASE_URL` to that API's HTTPS URL before rebuilding.
3. In Render, create an Environment Group named for your backend, containing the
   existing Firebase service-account credential plus Dhan client ID/token. Link
   it to the existing API and the new worker. Remove duplicate per-service values
   for these keys if they would override the shared group. Never link it to the
   frontend. Existing email settings belong to the API only if you use them.
4. Choose New > Background Worker, connect the TradeTracker repository and branch.
5. Use these settings:

   | Setting | Value |
   |---|---|
   | Runtime | Python |
   | Root directory | Leave blank (repository root) |
   | Build command | `pip install -r algos/zen_credit/requirements-paper.txt` |
   | Start command | `python -u algos/zen_credit/paper_worker.py` |
   | Instance | Paid always-on worker; one instance |
   | Environment group | The shared backend group from step 3 |

6. Deploy and inspect logs for `Paper worker started. Provider=Dhan` and per-strategy
   evaluation statuses. Start it before market open. It stays alive overnight;
   the exchange calendar blocks market requests/trades outside the session.
7. Verify that `algo_paper_state/strategy_01` and `strategy_02` evaluation times
   advance, their `data_provider` is `dhan`, and the UI displays the corresponding
   paper state. Actual simulated positions appear only when signal criteria align.

Alternatively the repo includes `algos/render.yaml`, a Blueprint for the same
single worker. Choose that Blueprint path and provide its three secret values.
Do not create both the manual worker and the Blueprint worker. A background worker
has no HTTP URL or health-check endpoint; monitor logs and Firestore/UI heartbeat.

## History, outages and credentials

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
