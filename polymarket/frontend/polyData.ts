// Polymarket paper accounts: types, plain-language algo descriptions and every figure the page
// shows. Pure functions only; all inputs come from GET /poly/paper and GET /poly/trades.

export type Position = { cid: string; outcome: number; outcome_name?: string | null; question: string; shares: number; cost: number; opened: number; mark?: number | null; entry_price?: number | null; end?: string | null };
export type Account = {
  name: string; description?: string; origin?: string; start_cash: number; cash: number; equity?: number; exposure?: number;
  realized_pnl?: number; n_settled?: number; n_wins?: number; n_fills?: number; updated_at?: string; started_at?: string;
  candidates?: number; watching?: number; signals?: number; params?: Record<string, number>;
  feed?: { connected?: boolean; last_message_at?: string | null }; last_error?: string | null;
  halted?: boolean;   // paused by the worker: no new bets, open bets still settle
  account_version?: number; previous?: { version: number; ended_at?: string; start_cash?: number; equity?: number; realized_pnl?: number; n_settled?: number; n_wins?: number }[];
  positions: Position[]; fills?: LedgerRow[]; settled?: LedgerRow[];
};
export type Stats = { n?: number; win_rate?: number; avg_price?: number; roi_per_bet?: number; t_stat?: number | null; avg_hold_hours?: number };
export type Catalog = { train?: Stats; test?: Stats; note?: string; train_label?: string; test_label?: string };
export type Feed = { strategies: Record<string, Account>; catalog: Record<string, Catalog> };
/** One ledger record: a paper buy ("fill") or a resolved bet ("settled"). */
export type LedgerRow = {
  t: number; ts: string; cid: string; outcome: number; outcome_name?: string | null; question: string; kind?: 'fill' | 'settled'; strategy?: string;
  shares?: number; price?: number; fee?: number; reason?: string; cost?: number; payout?: number; pnl?: number;
  version?: number;   // which version of the algo's rules placed the bet (1 when absent)
};

export const STALE_MS = 5 * 60_000;   // the worker saves at least every 2 minutes
export const MIN_BET = 1;             // below this much free cash an algo cannot place a new bet

// ------------------------------------------------------------------ presentation helpers
export const usd = (v: number | null | undefined, digits = 2) => v == null || !Number.isFinite(v) ? '—' : `${v < 0 ? '−' : ''}$${Math.abs(v).toFixed(digits)}`;
export const signedUsd = (v: number | null | undefined) => v == null || !Number.isFinite(v) ? '—' : `${v > 0 ? '+' : ''}${usd(v)}`;
export const pct = (v: number | null | undefined, digits = 1) => v == null || !Number.isFinite(v) ? '—' : `${(v * 100).toFixed(digits)}%`;
export const signedPct = (v: number | null | undefined, digits = 1) => v == null || !Number.isFinite(v) ? '—' : `${v > 0 ? '+' : ''}${(v * 100).toFixed(digits)}%`;
export const cents = (v: number | null | undefined) => v == null || !Number.isFinite(v) ? '—' : `${Math.round(v * 100)}¢`;
const IST: Intl.DateTimeFormatOptions = { timeZone: 'Asia/Kolkata' };
export const when = (v: string | number | null | undefined) => v ? new Date(typeof v === 'number' ? v * 1000 : v).toLocaleString('en-IN', { ...IST, month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—';
export const ago = (v: string | null | undefined, now = Date.now()) => {
  if (!v) return '—';
  const s = Math.max(0, Math.round((now - Date.parse(v)) / 1000));
  return s < 60 ? `${s}s ago` : s < 3600 ? `${Math.round(s / 60)} min ago` : s < 86400 ? `${Math.round(s / 3600)} h ago` : `${Math.round(s / 86400)} d ago`;
};
export const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`;

// ------------------------------------------------------------------ what each algo does
type Info = { title: string; short: string; color: string; how: (p: Record<string, number>) => string; hold: string };
export const ALGOS: Record<string, Info> = {
  updown_leader_3m: {
    title: 'Up/Down · last 3 min', short: 'Your manual pattern', color: 'var(--chart-1)', hold: 'about 2 minutes',
    how: p => `In each 5-minute Bitcoin and Ethereum "Up or Down" market, during the last ${Math.round((p.max_seconds_left ?? 180) / 60)} minutes it buys whichever side has just traded at ${cents(p.lo ?? 0.7)} to ${cents(p.hi ?? 0.9)}, then holds to the result.`,
  },
  updown_leader_early: {
    title: 'Up/Down · early entry', short: 'Variation of your pattern', color: 'var(--chart-3)', hold: 'about 3 minutes',
    how: p => `Same 5-minute markets, but it can enter from ${Math.round((300 - (p.max_seconds_left ?? 285)))} seconds into the window, buying a side that has just traded at ${cents(p.lo ?? 0.7)} to ${cents(p.hi ?? 0.9)}.`,
  },
  crypto_fair_value: {
    title: 'Crypto price levels', short: 'Modelled on top crypto traders', color: 'var(--chart-2)', hold: 'hours to weeks',
    how: p => `Prices markets like "Will Bitcoin dip to $62,000?" from the coin's live price and recent volatility, and buys NO when it is at least ${Math.round((p.edge ?? 0.15) * 100)} points cheaper than its fair price even in the most volatile recent conditions.`,
  },
  sports_pregame_underdog: {
    title: 'Sports underdogs', short: 'Modelled on a top sports trader', color: 'var(--chart-4)', hold: 'until the game ends',
    how: p => `${p.min_minutes ?? 10} to ${p.max_minutes ?? 240} minutes before a match starts, buys the underdog when it is priced ${cents(p.lo ?? 0.1)} to ${cents(p.hi ?? 0.4)}.`,
  },
};
const ORDER = ['updown_leader_3m', 'updown_leader_early', 'crypto_fair_value', 'sports_pregame_underdog'];
export const info = (id: string): Info => ALGOS[id] ?? { title: id.replaceAll('_', ' '), short: '', color: 'var(--chart-5)', hold: 'until resolution', how: () => '' };
export const sortIds = (ids: string[]) => [...ids].sort((a, b) => (ORDER.indexOf(a) + 1 || 99) - (ORDER.indexOf(b) + 1 || 99) || a.localeCompare(b));

// ------------------------------------------------------------------ ledger
// Two algos can hold the same market and settle it in the same second, so the algo is part of the key.
const key = (r: LedgerRow) => `${r.strategy}:${r.kind}:${r.cid}:${r.outcome}:${Math.round(r.t)}`;
/** Full ledger from /poly/trades, topped up with newer rows the account documents already carry. */
export function mergeLedger(ledger: LedgerRow[] | null, feed: Feed | null): LedgerRow[] {
  const rows = new Map<string, LedgerRow>();
  // When an algo's rules change its account restarts; bets from earlier versions stay in the ledger
  // (and the CSV export) but are not mixed into the current account's figures.
  const current = (id?: string) => feed?.strategies[id ?? '']?.account_version ?? 1;
  for (const r of ledger ?? []) if ((r.version ?? 1) === current(r.strategy)) rows.set(key(r), r);
  for (const [id, a] of Object.entries(feed?.strategies ?? {})) {
    for (const r of a.fills ?? []) { const row = { ...r, kind: 'fill' as const, strategy: id }; rows.set(key(row), rows.get(key(row)) ?? row); }
    for (const r of a.settled ?? []) { const row = { ...r, kind: 'settled' as const, strategy: id }; rows.set(key(row), rows.get(key(row)) ?? row); }
  }
  return [...rows.values()].sort((a, b) => a.t - b.t);
}

// ------------------------------------------------------------------ per-algo figures
export type AlgoStats = {
  id: string; start: number; value: number; pnl: number; pnlPct: number; realized: number; unrealized: number;
  inBets: number; cash: number; openCount: number; settled: number; wins: number; losses: number; winRate: number | null;
  staked: number; bets: number; avgEntry: number | null; liveRoi: number | null; avgWin: number | null; avgLoss: number | null;
  state: 'offline' | 'holding' | 'watching' | 'paused'; lowCash: boolean; updated?: string; started?: string;
  backtest?: Stats; verdict: Verdict;
};
export type Verdict = { tone: 'good' | 'bad' | 'neutral'; text: string };

export const unrealizedOf = (a: Account) => a.positions.reduce((t, p) => t + (p.mark == null ? 0 : p.mark * p.shares - p.cost), 0);
export const isStale = (a: Account, now = Date.now()) => !a.updated_at || now - Date.parse(a.updated_at) > STALE_MS || a.feed?.connected === false;

export function algoStats(id: string, a: Account, ledger: LedgerRow[], catalog: Catalog | undefined, now = Date.now()): AlgoStats {
  const mine = ledger.filter(r => r.strategy === id);
  const fills = mine.filter(r => r.kind === 'fill');
  const settledRows = mine.filter(r => r.kind === 'settled');
  const start = a.start_cash;
  const unrealized = unrealizedOf(a);
  const value = a.equity ?? a.cash + a.positions.reduce((t, p) => t + p.cost, 0);
  const settled = a.n_settled ?? settledRows.length;
  const wins = a.n_wins ?? settledRows.filter(r => (r.pnl ?? 0) > 0).length;
  const settledCost = settledRows.reduce((t, r) => t + (r.cost ?? 0), 0);
  const settledPnl = settledRows.reduce((t, r) => t + (r.pnl ?? 0), 0);
  const winRows = settledRows.filter(r => (r.pnl ?? 0) > 0), lossRows = settledRows.filter(r => (r.pnl ?? 0) <= 0);
  const backtest = catalog?.test;
  const liveRoi = settledCost > 0 ? settledPnl / settledCost : null;
  return {
    id, start, value, pnl: value - start, pnlPct: (value - start) / start, realized: a.realized_pnl ?? settledPnl, unrealized,
    inBets: a.exposure ?? a.positions.reduce((t, p) => t + p.cost, 0), cash: a.cash, openCount: a.positions.length,
    settled, wins, losses: settled - wins, winRate: settled ? wins / settled : null,
    staked: fills.reduce((t, r) => t + (r.shares ?? 0) * (r.price ?? 0) + (r.fee ?? 0), 0), bets: a.n_fills ?? fills.length,
    avgEntry: fills.length ? fills.reduce((t, r) => t + (r.price ?? 0), 0) / fills.length : null,
    liveRoi, avgWin: winRows.length ? winRows.reduce((t, r) => t + (r.pnl ?? 0), 0) / winRows.length : null,
    avgLoss: lossRows.length ? lossRows.reduce((t, r) => t + (r.pnl ?? 0), 0) / lossRows.length : null,
    state: isStale(a, now) ? 'offline' : a.halted ? 'paused' : a.positions.length ? 'holding' : 'watching', lowCash: a.cash < MIN_BET,
    updated: a.updated_at, started: a.started_at,
    backtest, verdict: verdict(settled, liveRoi, settled ? wins / settled : null, backtest),
  };
}

/** Plain-language comparison of live results with the held-out backtest. */
export function verdict(n: number, liveRoi: number | null, liveWin: number | null, bt?: Stats): Verdict {
  if (!n || liveRoi == null) return { tone: 'neutral', text: 'No settled bets yet.' };
  if (bt?.roi_per_bet == null) return { tone: 'neutral', text: `${plural(n, 'bet')} settled; no backtest to compare.` };
  const few = n < 30;
  const diff = liveRoi - bt.roi_per_bet;
  if (few) return { tone: 'neutral', text: `Only ${plural(n, 'settled bet')}: too few to judge yet (aim for 30+).` };
  if (liveRoi >= bt.roi_per_bet * 0.5 && liveRoi > 0) return { tone: 'good', text: `In line with the backtest so far.` };
  if (liveRoi > 0) return { tone: 'neutral', text: `Profitable, but below the backtest (${signedPct(liveRoi)} vs ${signedPct(bt.roi_per_bet)} per bet).` };
  return { tone: 'bad', text: `Losing where the backtest made money (${signedPct(liveRoi)} vs ${signedPct(bt.roi_per_bet)} per bet, ${pct(liveWin, 0)} wins vs ${pct(bt.win_rate, 0)}).${diff < -0.2 ? ' Worth reviewing before any real money.' : ''}` };
}

// ------------------------------------------------------------------ chart series
export type ChartPoint = { t: number } & Record<string, number>;
/** Cumulative profit/loss per algo over time: settled bets step the line; the last point adds open bets at today's prices. */
export function pnlSeries(ids: string[], ledger: LedgerRow[], feed: Feed, now = Date.now()): ChartPoint[] {
  const running: Record<string, number> = Object.fromEntries(ids.map(id => [id, 0]));
  const firstStart = Math.min(...ids.map(id => Date.parse(feed.strategies[id]?.started_at ?? '') || now));
  const points: ChartPoint[] = [{ t: firstStart, ...running, total: 0 } as ChartPoint];
  for (const r of ledger) {
    if (r.kind !== 'settled' || !r.strategy || !(r.strategy in running)) continue;
    running[r.strategy] += r.pnl ?? 0;
    points.push({ t: r.t * 1000, ...running, total: Object.values(running).reduce((a, b) => a + b, 0) } as ChartPoint);
  }
  const final = Object.fromEntries(ids.map(id => { const a = feed.strategies[id]; return [id, (a.equity ?? a.start_cash) - a.start_cash]; }));
  points.push({ t: now, ...final, total: Object.values(final).reduce((a, b) => a + b, 0) } as ChartPoint);
  return points;
}
