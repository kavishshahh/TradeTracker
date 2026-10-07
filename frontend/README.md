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
