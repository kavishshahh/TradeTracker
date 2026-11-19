# Algo Lab frontend

This folder contains the Algo Lab client component and scoped CSS. It reuses
TradeTracker's Next.js app, Firebase Auth context, existing login and navigation.
There is no separate npm install or second frontend project.

From the TradeTracker root run `npm run dev`, then open `/algos`. Use the existing
account to sign in. `NEXT_PUBLIC_API_BASE_URL` points to the existing Python API;
that backend now registers the `/algos` router. The UI sends Firebase ID tokens,
polls paper state every 30 seconds and can save follow preferences and export the
latest paper ledger. No scheduler or trade execution is invoked by the browser.

Strategy metadata and backtest metrics come from Firestore through `/algos/catalog`; paper metrics come exclusively
from the worker feed. Historical results are explicitly gross and provisional.
Unconfigured or stale paper data is displayed honestly, without demo positions.

Deployment and continuous Dhan paper-worker configuration: `../algos/PAPER_DEPLOYMENT.md`.

## Who sees what in Algo Lab

Three tiers, decided by Firestore, not code:

- Every signed-in user sees the card grid and basic stats: names, descriptions, backtest
  metrics, monthly returns and each paper account's summary numbers and live status.
- Users whose verified email is in `feature_access/algo_lab` (field `emails`) also see the
  trades: Past trades (backtest ledger and paper ledger), Positions and Orders. The API
  strips open and closed positions from the paper feed for everyone else and answers 403
  on the backtest ledger.
- The owner (`ALGO_LAB_OWNER_EMAIL` on the API, default kavishshah30@gmail.com) is always
  allowed and is the only account that receives each strategy's rules, limitations, exit
  policy and tuning parameters on the About algo page; everyone else gets a basic
  description there.

Anyone without access sees a banner and, in place of the trades sections, a Request
access card. Asking writes `algo_access_requests/{uid}` (email, requested_at, status).
The owner grants, declines or revokes from Settings > Admin (`/profile`), which edits
the same two documents through `/algos/access/admin/*`. Only the owner can reach those routes.
