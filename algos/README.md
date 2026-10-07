# TradeBud algorithms — Firestore paper trading

Algo code, reference data and historical reports live in this repository.
The original checkout is preserved; continue integration work here.

- `zen_credit/strategy/strategy_01_geometric_credit.py`: saved geometric-volume trial.
- `zen_credit/strategy/strategy_02_variance_credit.py`: saved variance-scaled trial.
- `../frontend/`: authenticated Algo Lab dashboard at `/algos`.
- `../backend/algos_api.py`: Firebase-authenticated catalogue, paper state and follows.
- `algo_catalog` in Firestore: verified historical/monthly statistics and strategy descriptions.
- `data/` and `reports/`: migrated backtest inputs/results; generated caches and reports stay out of Git.
- `RESEARCH.md`: archived research notes and replay commands. Its historical PostgreSQL references describe the earlier implementation.

## One Firestore project

The algo workers now use **the existing TradeBud Firestore project only**.
No PostgreSQL database or `DATABASE_URL` is needed. The old SQL adapter remains
solely for isolated regression fixtures; production factories select Firestore.

Execution state lives in `algo_engines/{strategy_id}` subcollections:

- `control`: runtime pointers, exactly-once closed totals and transactional worker lease.
- `positions`, `closed`, `signals`: simulated positions and signal deduplication.
- `runs`: persistent minute claims and outcomes.
- `snapshots`: one document per minute, containing strike rows for both expiries.
- `state`: strategy binding, last evaluation and holiday cache.
- `emails`: pending notification retry queue.

Each strategy has its own namespace in the same project. Transactions enforce
one open position, atomic exits/totals and duplicate suppression. A five-minute
lease is renewed by writes; a fenced token refuses writes from expired workers.
Minute history is loaded on cold start and incrementally cached for the required
lookback. Positions and totals survive restarts. Expired/stale leases cannot be
used to mutate another worker's state.

The dashboard reads `algo_paper_state/{strategy_id}`, exported after each worker
cycle. It contains actual paper positions, gross P&L, quote timestamps and the
latest 200 closed trades. Summary totals cover all closed paper trades. Historic
backtest profit is never substituted for paper profit. User follows are stored
under `users/{uid}/algo_follows/{strategy_id}`. Following does not launch a worker
or customize its fixed model capital. Only virtual trades are recorded.

## Runtime and deployment

See [PAPER_DEPLOYMENT.md](PAPER_DEPLOYMENT.md) for exact local/Render steps.
Cloudflare schedules the existing Python API once per minute; its shared evaluator
runs both strategies using Dhan REST quotes and completed index candles. Both use the shared `backend/.env` locally
and the existing backend environment in production. No separate algo environment,
database URL or SMTP configuration is required. One shared scheduler secret
authenticates Cloudflare requests.

`python algos/zen_credit/paper_worker.py --check-data` performs a read-only probe.
`python -u algos/zen_credit/paper_worker.py` runs the paper accounts each minute.
See `cloudflare-scheduler/README.md` for the free Cloudflare scheduler and existing
backend deployment. The separate paid worker blueprint was removed.
NSE is used only for exchange holiday metadata; live prices come from Dhan.

## Subdomain and access

Add `algos.tradebud.xyz` to the existing hosting project, using its supplied DNS
record, and to Firebase Auth authorized domains. A host rewrite maps its root to
`/algos`; backend CORS includes the subdomain. Existing accounts are reused, but
browser login persistence is origin-specific.

API requests verify existing Firebase ID tokens and derive the user ID server-side.
The browser needs no direct Firestore access. Scope your existing Firestore rules
so browser clients cannot modify `algo_engines`, `algo_paper_state` or the algo
follow records: server Admin SDK operations own these writes. Existing project
rules were not modified by this change. All paper state is a shared model account,
not a user's real brokerage account.

Validation: offline lease/isolation/idempotency/MTM tests and an actual temporary
Firestore transaction smoke test passed. The smoke namespace was completely
removed; no actual strategy positions or user trades were created.

Firestore transaction semantics: https://firebase.google.com/docs/firestore/manage-data/transactions

## Database-driven catalogue

The authenticated `/algos/catalog` route reads `algo_catalog/{strategy_id}` from
Firestore on each request. Names, descriptions, rules, capital, backtest statistics
and monthly results are database records. The frontend fetches them with the
existing Firebase login; it imports no catalogue JSON and has no static fallback.
Disabled records (`enabled: false`) are hidden. No database access returns 503.

`backend/seed_algos_catalog.py` inserts the two verified initial records using
`backend/seed_data/algos_catalog.json` as migration input only. Existing documents
are preserved. New strategies need a Python implementation, verified backtest
results, a catalogue record and a deployed paper worker. Changing catalogue text
does not change formulas or deploy workers. API routes and executable Python stay
in the repository. Paper state stays separate from historical backtest results.
Browser clients must not be allowed to write `algo_catalog` directly.
