# Automatic Dhan paper trading with Cloudflare Free

## Architecture

Cloudflare Cron Trigger -> protected Tradebud Python API -> Dhan market data ->
both paper strategies -> existing Firestore -> Algo Lab.

The free Worker schedules work; the existing Python backend performs all strategy
calculations. There is no additional Render background-worker service. Cloudflare
does not hold Dhan/Firebase credentials or run the Python engine. Existing backend
hosting costs and availability still apply. No broker orders are submitted.

## 1. Deploy the updated existing backend

Commit/push the updated TradeTracker source, excluding all `.env` files, credentials,
virtualenvs, node_modules and generated caches. In the existing Render service for
`https://ricotradetracker-1.onrender.com`, use:

| Setting | Value |
|---|---|
| Root Directory | Leave blank: repository root |
| Build Command | `pip install -r backend/requirements.txt` |
| Start Command | `uvicorn main_firebase:app --app-dir backend --host 0.0.0.0 --port $PORT` |

Keeping the repository root available is necessary because the API imports the
strategy files under `algos/zen_credit`. A backend-only checkout/root directory
will not include them. Use one API process initially so both strategies share
the Dhan provider cache/throttle; Firestore still fences duplicate execution.

Keep existing Firebase environment variables. Add these server-only values:

```dotenv
DHAN_CLIENT_ID=your_existing_client_id
DHAN_ACCESS_TOKEN=your_current_token
PAPER_SCHEDULER_TOKEN=the_shared_secret_saved_in_backend_env
```

The shared secret was generated in your local `backend/.env`. Copy its exact
value to Render and Cloudflare. It is required because the scheduler must call
an authenticated machine endpoint without your browser's Firebase login.
It is not another Dhan credential. Do not commit or paste it into source code.

Deploy/restart the API. Open `/docs` and confirm `POST /algos/run-paper-cycle`
exists. Without the shared header the endpoint refuses execution. It also refuses
missing/stale timestamps. Ordinary browser requests never run the strategies.

## 2. Deploy Cloudflare scheduler

From a terminal:

```powershell
cd C:\Users\kavis\OneDrive\Desktop\TradeTracker\algos\cloudflare-scheduler
npm install
npx wrangler login
npx wrangler deploy
npx wrangler secret put PAPER_SCHEDULER_TOKEN
```

Complete the browser login. At the secret prompt, paste the exact value from
`backend/.env`. It remains a Cloudflare secret. The deployment is fail-closed until
both hosts have the matching secret. No third local `.env` file is needed.

`wrangler.jsonc` already specifies:
- Worker name: `tradebud-paper-scheduler`
- API base: `https://ricotradetracker-1.onrender.com`
- One cron expression: `* 3-10 * * MON-FRI` (UTC)

The handler filters this broader UTC interval to **09:15–15:30 IST** and waits
until about five seconds after the scheduled minute, allowing completed candles
to arrive. Official holidays are checked in Python. Trigger changes can take up
to 15 minutes to propagate. The worker uses only one Cron Trigger.

## Dashboard alternative

If you prefer the dashboard shown in the screenshot:
1. Create a Worker named `tradebud-paper-scheduler`.
2. Replace its code with the complete `index.mjs` from this folder and deploy.
3. In Settings > Variables and Secrets, add the text variable `API_BASE_URL` with
   `https://ricotradetracker-1.onrender.com` and secret `PAPER_SCHEDULER_TOKEN` with
   the value from `backend/.env`.
4. In Settings > Triggers > Cron Triggers, add `* 3-10 * * MON-FRI`.
5. Do not configure a second scheduler or run the continuous local worker against
   the same paper accounts while testing this scheduled deployment.

## 3. Verify automatic execution

- In Cloudflare, view Worker logs/Cron Events (or use `npx wrangler tail`). Expect
  `paper_cycle_ok`; errors/busy outcomes are logged explicitly, without secrets.
- In Render logs, look for both strategies' evaluation results.
- In Firestore, `algo_paper_state/strategy_01` and `strategy_02` should show advancing
  `last_evaluation`, `data_provider: dhan`, and `execution: paper_only`.
- In Algo Lab > Paper feed, verify those timestamps and later qualifying entries,
  exits, marked P&L and the paper ledger. The UI polls every 30 seconds.

Existing positions and minute claims survive restarts. Request overlap is blocked
by the coordinator mutex and Firestore leases. A disabled strategy's existing
position is still monitored, including after restart. Missing data stays unknown.

## What remains to check

- The live backend currently needs this code deployment; local edits do not update
  `ricotradetracker-1.onrender.com`. Its schema lacked the new route at verification.
- The local Wrangler login had expired at verification. Deployment needs a fresh
  `wrangler login`; no Cloudflare deployment has yet been completed.
- Cloudflare Free has a 10 ms CPU limit per cron invocation. This tiny scheduler
  only validates time and performs an HTTP call; rolling calculations run in Python.
  Monitor deployed CPU/error metrics rather than assuming a local test proves limits.
- If the existing Render API uses a free sleeping instance, a cold start can miss
  the first minute. This setup does not guarantee exact execution times or uptime.
  Requests older than 45 seconds are rejected, rather than recording a late price
  under an earlier timestamp. Failures are not automatically replayed.
- Dhan Web-generated access tokens normally expire after 24 hours. Update the hosted
  backend token and redeploy/restart before expiry. Token renewal is not implemented.
- Initial option alpha2 history requires warmup over trading sessions. Signals use
  once-per-minute REST observations, not tick-based stop execution. Backtest/live
  parity remains unverified. Fees, slippage and broker liquidation are not modeled.

## Environment layout

Local frontend: existing TradeTracker root `.env`.
Local backend/API/algos: `backend/.env`.
Cloudflare: one backend URL variable and one scheduler secret in deployment settings.
The scheduler has no Dhan/Firebase keys and no separate local algo environment.

References:
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://developers.cloudflare.com/workers/platform/limits/
- https://render.com/docs/free
