// Shared Algo Lab types and pure helpers. Everything here derives from the two API calls
// (GET /algos/catalog and GET /algos/paper); nothing adds Firestore reads.

export type Rule = string | { label: string; description: string };
export type Month = { month: string; pnl: number; closed_trades: number; win_rate_pct: number | null; return_pct: number; winning_trades?: number; losing_trades?: number; partial_month?: boolean };
export type Strategy = { id: string; name: string; version: string; description: string; underlying: string; category: string; capital: number; period_start: string; period_end: string; limitations: string; exit_policy?: string; rules: Rule[]; metrics: { total_pnl: number; trade_count: number; win_rate_pct: number; cagr_pct: number; max_drawdown_pct: number; return_1m_pct: number; return_3m_pct: number; return_6m_pct: number }; monthly: Month[] };
export type Trade = { signal_id: string; status: string; option_type: string; sell_strike: number; buy_strike: number; units: number; lots: number; entry_ts: string; expiry: string; exit_ts: string | null; pnl: number | null; stop_loss: number; target: number | null; exit_due: string; sell_price: number; buy_price: number; exit_reason: string | null; sell_mark?: number | null; buy_mark?: number | null; sell_exit_price?: number | null; buy_exit_price?: number | null };
export type Paper = { execution: string; updated_at: string; last_evaluation: string | null; status: string; capital: number; alpha: number | null; alpha2: number | null; signal_at: string | null; realized_pnl: number | null; unrealized_pnl: number | null; valuation_ts: string | null; closed_trades: number; win_rate_pct: number | null; open_position: Trade | null; closed_positions: Trade[]; ledger_limit: number };
export type PaperResponse = { following: Record<string, boolean>; strategies: Record<string, Paper | null> };
export type Period = '1m' | '3m' | '6m' | '1y';

export const STALE_MS = 180_000;
export const money = (value: number | null | undefined, digits = 0) => value == null ? '—' : new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value);
export const percent = (value: number | null | undefined) => value == null || !Number.isFinite(value) ? '—' : `${value.toFixed(2)}%`;
export const signedPercent = (value: number | null | undefined) => value == null || !Number.isFinite(value) ? '—' : `${value > 0 ? '+' : ''}${value.toFixed(2)}%`;
export const time = (value: string | null | undefined) => value ? new Date(value).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—';
export const clock = (value: string | null | undefined) => value ? new Date(value).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '—';
export const lakhs = (value: number) => `${(value / 100_000).toFixed(value >= 1_000_000 ? 0 : 1).replace(/\.0$/, '')}L`;
export const monthLabel = (value: string, style: 'short' | 'long' = 'short') => new Date(`${value}-01T00:00:00Z`).toLocaleDateString('en-IN', { month: 'short', year: style === 'short' ? '2-digit' : 'numeric', timeZone: 'UTC' });
export const ruleText = (rule: Rule) => typeof rule === 'string' ? { label: '', description: rule } : rule;
export const legName = (trade: Trade, side: 'sell' | 'buy') => `NIFTY ${trade.expiry} ${side === 'sell' ? trade.sell_strike : trade.buy_strike} ${trade.option_type}`;

/** IST calendar parts for a timestamp (defaults to now). */
export function istParts(date = new Date()) {
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Kolkata', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', weekday: 'short', hourCycle: 'h23' }).formatToParts(date).map(part => [part.type, part.value]));
  return { day: `${parts.year}-${parts.month}-${parts.day}`, month: `${parts.year}-${parts.month}`, weekday: parts.weekday as string, minutes: Number(parts.hour) * 60 + Number(parts.minute) };
}
export const istDay = (value: string | null | undefined) => value ? istParts(new Date(value)).day : '';

/** NSE cash session, Mon–Fri 09:15–15:30 IST. Exchange holidays are not known to the client. */
export function marketOpen(now = new Date()) {
  const { weekday, minutes } = istParts(now);
  return !['Sat', 'Sun'].includes(weekday) && minutes >= 555 && minutes < 930;
}

export const isStale = (account: Paper | null | undefined) => !account || Date.now() - Date.parse(account.updated_at) > STALE_MS;
export const openPnl = (account: Paper | null | undefined) => account ? account.open_position ? account.unrealized_pnl : 0 : null;
export const todayRealized = (account: Paper | null | undefined) => {
  if (!account) return null;
  const today = istParts().day;
  return (account.closed_positions || []).filter(trade => istDay(trade.exit_ts) === today).reduce((total, trade) => total + (trade.pnl ?? 0), 0);
};

export type AlgoState = 'awaiting' | 'closed' | 'stale' | 'in-trade' | 'scanning';
export function algoState(account: Paper | null | undefined): AlgoState {
  if (!account) return 'awaiting';
  if (account.open_position && !marketOpen()) return 'in-trade';
  if (!marketOpen()) return 'closed';
  if (isStale(account)) return 'stale';
  return account.open_position ? 'in-trade' : 'scanning';
}
export const stateLabel: Record<AlgoState, string> = { awaiting: 'Awaiting feed', closed: 'Market Closed', stale: 'Feed stale', 'in-trade': 'In trade', scanning: 'Scanning' };
export function scanMessage(account: Paper | null | undefined) {
  const state = algoState(account);
  if (!account || state === 'awaiting') return 'Waiting for the paper worker to publish this algo’s first update.';
  if (state === 'in-trade') return `Holding ${legName(account.open_position!, 'sell')} / ${account.open_position!.buy_strike} spread${marketOpen() ? '' : ' overnight'} · marked ${time(account.valuation_ts)}.`;
  if (state === 'closed') return 'Market is closed. Algo will look for an entry when trading resumes.';
  if (state === 'stale') return `No worker update since ${time(account.updated_at)}. Entries resume once the feed reconnects.`;
  return `Scanning for an entry · last evaluation ${time(account.last_evaluation)} (${account.status.replaceAll('_', ' ')}).`;
}

/** Trailing backtest return on fixed capital. 1y sums the last 12 monthly rows, as the catalogue stores no 1y metric. */
export function periodReturn(strategy: Strategy, period: Period | 'all') {
  if (period === '1m') return strategy.metrics.return_1m_pct;
  if (period === '3m') return strategy.metrics.return_3m_pct;
  if (period === '6m') return strategy.metrics.return_6m_pct;
  const rows = period === '1y' ? strategy.monthly.slice(-12) : strategy.monthly;
  return period === 'all' ? strategy.metrics.total_pnl / strategy.capital * 100 : rows.reduce((total, row) => total + row.pnl, 0) / strategy.capital * 100;
}
export const periodName: Record<Period, string> = { '1m': '1 Month', '3m': '3 Month', '6m': '6 Month', '1y': '1 Year' };

/** Simulated fills from the paper ledger: two legs on entry and, once closed, two on exit. */
export type Fill = { key: string; ts: string; side: 'B' | 'S'; name: string; algo: string; algoId: string; qty: number; kind: 'Entry' | 'Exit'; price: number | null; ltp: number | null };
export function ledgerFills(catalog: Strategy[], paper: PaperResponse | null): Fill[] {
  const fills: Fill[] = [];
  for (const strategy of catalog) {
    const account = paper?.strategies[strategy.id];
    if (!account) continue;
    const trades = [...(account.open_position ? [account.open_position] : []), ...(account.closed_positions || [])];
    for (const trade of trades) {
      const open = trade === account.open_position;
      const base = { algo: strategy.name, algoId: strategy.id, qty: trade.units };
      fills.push({ ...base, key: `${trade.signal_id}-es`, ts: trade.entry_ts, side: 'S', name: legName(trade, 'sell'), kind: 'Entry', price: trade.sell_price, ltp: open ? trade.sell_mark ?? null : null });
      fills.push({ ...base, key: `${trade.signal_id}-eb`, ts: trade.entry_ts, side: 'B', name: legName(trade, 'buy'), kind: 'Entry', price: trade.buy_price, ltp: open ? trade.buy_mark ?? null : null });
      if (!open && trade.exit_ts) {
        fills.push({ ...base, key: `${trade.signal_id}-xs`, ts: trade.exit_ts, side: 'B', name: legName(trade, 'sell'), kind: 'Exit', price: trade.sell_exit_price ?? null, ltp: null });
        fills.push({ ...base, key: `${trade.signal_id}-xb`, ts: trade.exit_ts, side: 'S', name: legName(trade, 'buy'), kind: 'Exit', price: trade.buy_exit_price ?? null, ltp: null });
      }
    }
  }
  return fills.sort((a, b) => Date.parse(b.ts) - Date.parse(a.ts));
}
