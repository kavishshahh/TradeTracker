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
  policy, tuning parameters and the full description on the About algo page. Everyone
  else reads the catalogue's short `summary` as the description, on the cards and on About
  algo; a record without one shows only its style and underlying. The client hides the rules
  unless the API says the viewer is the owner, so an older API cannot expose them. New or
  changed summaries reach Firestore with `backend/set_catalog_summaries.py` (one merge write
  per strategy), since the seed script never touches existing records.
- The owner also gets a Research tab (`?tab=research`, `AlgoResearch.tsx`): write-ups of strategies that
  were built and tested but not listed, with their figures and the reason they were left out. The notes
  name rules, so they come from `GET /algos/research` (owner only, 404 for everyone else) and are never
  in the page bundle. They live in `backend/seed_data/algo_research.json`, a file shipped with the API
  (no Firestore read); add a note there when a strategy is researched and rejected. Research-only
  strategies are listed in `RESEARCH_ONLY` in `algos/zen_credit/strategy/registry.py`, which keeps them
  out of the paper worker.

Anyone without access sees a banner and, in place of the trades sections, a Request
access card. Asking writes `algo_access_requests/{uid}` (email, requested_at, status).
The owner grants, declines or revokes from Settings > Admin (`/profile`), which edits
the same two documents through `/algos/access/admin/*`. Only the owner can reach those routes.
