'use client';

import { useAuth } from '@/contexts/AuthContext';
import { AlertCircle, Download, FileText, RefreshCw, ShieldCheck } from 'lucide-react';
import { useCallback, useEffect, useState, type ReactNode } from 'react';
import styles from './poly.module.css';
import { usePolyAccess } from './usePolyAccess';

const apiBase = (process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');
const STALE_MS = 5 * 60_000;   // the worker saves a heartbeat every 2 minutes

type Position = { cid: string; outcome: number; outcome_name?: string | null; question: string; shares: number; cost: number; opened: number; mark?: number | null; entry_price?: number | null; end?: string | null };
type Fill = { ts: string; cid: string; side: string; outcome_name?: string | null; question: string; shares: number; price: number; fee: number; reason: string };
type Settled = { ts: string; cid: string; question: string; outcome_name?: string | null; cost: number; payout: number; pnl: number; how: string };
type Account = { name: string; description?: string; origin?: string; start_cash: number; cash: number; equity?: number; exposure?: number; realized_pnl?: number; n_settled?: number; n_wins?: number; n_fills?: number; status?: string; updated_at?: string; started_at?: string; candidates?: number; watching?: number; evaluations?: number; signals?: number; feed?: { connected?: boolean; tokens?: number; last_message_at?: string | null }; last_error?: string | null; positions: Position[]; fills: Fill[]; settled: Settled[]; equity_curve: { t: number; equity: number }[] };
type Stats = { n?: number; win_rate?: number; avg_price?: number; roi_per_bet?: number; t_stat?: number | null; avg_hold_hours?: number };
type Catalog = { train?: Stats; test?: Stats; note?: string; train_label?: string; test_label?: string };
type Feed = { strategies: Record<string, Account>; catalog: Record<string, Catalog> };
type View = 'algos' | 'positions' | 'orders' | 'settled';

const usd = (value: number | null | undefined, digits = 2) => value == null || !Number.isFinite(value) ? '—' : `${value < 0 ? '−' : ''}$${Math.abs(value).toFixed(digits)}`;
const signedUsd = (value: number | null | undefined) => value == null ? '—' : `${value > 0 ? '+' : ''}${usd(value)}`;
const pct = (value: number | null | undefined, digits = 1) => value == null || !Number.isFinite(value) ? '—' : `${value > 0 ? '+' : ''}${(value * 100).toFixed(digits)}%`;
const cents = (value: number | null | undefined) => value == null ? '—' : `${(value * 100).toFixed(1)}¢`;
const when = (value: string | number | null | undefined) => value ? new Date(typeof value === 'number' ? value * 1000 : value).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—';
const tone = (value: number | null | undefined) => value == null || value === 0 ? '' : value < 0 ? styles.red : styles.green;
function EmptyRow({ children }: { children: ReactNode }) { return <div className={styles.emptyRow}><FileText size={22} strokeWidth={1.4} />{children}</div>; }
const label = (id: string) => id.replaceAll('_', ' ').replace(/^./, char => char.toUpperCase());
const stale = (account: Account) => !account.updated_at || Date.now() - Date.parse(account.updated_at) > STALE_MS || account.feed?.connected === false;
const unrealized = (account: Account) => account.positions.reduce((total, position) => total + (position.mark == null ? 0 : position.mark * position.shares - position.cost), 0);

function Sparkline({ points }: { points: { t: number; equity: number }[] }) {
  if (points.length < 2) return <p className={styles.caption}>The equity curve appears after the first hour of updates.</p>;
  const values = points.map(point => point.equity);
  const low = Math.min(...values), high = Math.max(...values), span = high - low || 1;
  const path = points.map((point, index) => `${index ? 'L' : 'M'}${(index / (points.length - 1) * 600).toFixed(1)},${(70 - (point.equity - low) / span * 60).toFixed(1)}`).join(' ');
  return <svg className={styles.chartSvg} viewBox="0 0 600 80" preserveAspectRatio="none" role="img" aria-label={`Equity from ${usd(values[0])} to ${usd(values.at(-1))}`}><path className={styles.line} d={path} vectorEffect="non-scaling-stroke" /></svg>;
}

export default function PolyDashboard() {
  const { currentUser } = useAuth();
  const allowed = usePolyAccess();
  const [feed, setFeed] = useState<Feed | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [view, setView] = useState<View>('algos');
  const [denied, setDenied] = useState(false);

  const load = useCallback(async (signal?: AbortSignal) => {
    if (!currentUser) return;
    setLoading(true);
    try {
      const token = await currentUser.getIdToken();
      const response = await fetch(`${apiBase}/poly/paper`, { headers: { Authorization: `Bearer ${token}` }, signal, cache: 'no-store' });
      if (response.status === 404) { setDenied(true); return; }
      if (!response.ok) throw new Error(response.status === 401 ? 'Your session has expired. Sign in again.' : 'Polymarket paper feed unavailable. Please retry.');
      const body = await response.json() as Feed;
      if (!signal?.aborted) { setFeed(body); setError(''); }
    } catch (err) { if (!signal?.aborted) setError(err instanceof Error ? err.message : 'Unable to load Polymarket data.'); }
    finally { if (!signal?.aborted) setLoading(false); }
  }, [currentUser]);

  // The complete ledger (every paper buy and settlement) is fetched only when asked for.
  const [exporting, setExporting] = useState(false);
  const exportTrades = useCallback(async () => {
    if (!currentUser || exporting) return;
    setExporting(true);
    try {
      const token = await currentUser.getIdToken();
      const response = await fetch(`${apiBase}/poly/trades`, { headers: { Authorization: `Bearer ${token}` }, cache: 'no-store' });
      if (!response.ok) throw new Error('Trade ledger unavailable. Please retry.');
      const rows = (await response.json() as { trades: Record<string, unknown>[] }).trades;
      const fields = ['ts', 'strategy', 'kind', 'question', 'outcome_name', 'side', 'shares', 'price', 'fee', 'cost', 'payout', 'pnl', 'reason', 'cid'];
      const cell = (value: unknown) => `"${String(value ?? '').replace(/"/g, '""')}"`;
      const csv = [fields.join(','), ...rows.map(row => fields.map(field => cell(row[field])).join(','))].join('\r\n');
      const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8;' }));
      const link = document.createElement('a'); link.href = url; link.download = 'polymarket-paper-trades.csv'; link.click(); URL.revokeObjectURL(url);
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not export trades.'); }
    finally { setExporting(false); }
  }, [currentUser, exporting]);

  useEffect(() => {
    if (allowed !== true) return;
    const controller = new AbortController();
    void load(controller.signal);
    const timer = window.setInterval(() => void load(controller.signal), 30_000);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [allowed, load]);

  // People without access get the same empty page as an unknown route.
  if (allowed === false || denied) return <section className={styles.lab}><div className={styles.card}><EmptyRow>This page is not available.</EmptyRow></div></section>;
  if (allowed === null) return <section className={styles.lab}><div className={styles.card}><EmptyRow>Loading…</EmptyRow></div></section>;

  const accounts = Object.entries(feed?.strategies || {}).sort(([a], [b]) => a.localeCompare(b));
  const total = (pick: (account: Account) => number) => accounts.reduce((sum, [, account]) => sum + pick(account), 0);
  const positions = accounts.flatMap(([id, account]) => account.positions.map(position => ({ id, position })));
  const fills = accounts.flatMap(([id, account]) => (account.fills || []).map(fill => ({ id, fill }))).sort((a, b) => Date.parse(b.fill.ts) - Date.parse(a.fill.ts));
  const settled = accounts.flatMap(([id, account]) => (account.settled || []).map(row => ({ id, row }))).sort((a, b) => Date.parse(b.row.ts) - Date.parse(a.row.ts));
  const capital = total(account => account.start_cash), equity = total(account => account.equity ?? account.start_cash);
  const realized = total(account => account.realized_pnl ?? 0), open = total(unrealized);
  const live = accounts.length > 0 && accounts.every(([, account]) => !stale(account));
  const lastUpdate = accounts.map(([, account]) => account.updated_at).filter(Boolean).sort().at(-1);

  let main;
  if (!feed) main = <div className={styles.card}><EmptyRow>{loading ? 'Loading paper accounts…' : error || 'No data yet.'}</EmptyRow></div>;
  else if (!accounts.length) main = <div className={styles.card}><EmptyRow>The paper worker has not published an account yet. Start it and this page fills in within a few minutes.</EmptyRow></div>;
  else if (view === 'positions') main = <div className={styles.tableCard}><div className={styles.tableScroll}><table className={styles.table}>
    <thead><tr><th>Market</th><th>Algo</th><th>Outcome</th><th className={styles.num}>Shares</th><th className={styles.num}>Entry</th><th className={styles.num}>Bid</th><th className={styles.num}>Cost</th><th className={styles.num}>Unrealized</th></tr></thead>
    <tbody>{positions.map(({ id, position }) => {
      const pnl = position.mark == null ? null : position.mark * position.shares - position.cost;
      return <tr key={position.cid + position.outcome}>
        <td className={styles.wrap}><b>{position.question}</b><small>Opened {when(position.opened)}{position.end ? ` · ends ${when(position.end)}` : ''}</small></td>
        <td>{label(id)}</td><td><span className={styles.buyTag}>BUY</span>{position.outcome_name ?? position.outcome}</td>
        <td className={styles.num}>{position.shares.toFixed(2)}</td><td className={styles.num}>{cents(position.entry_price)}</td><td className={styles.num}>{cents(position.mark)}</td>
        <td className={styles.num}>{usd(position.cost)}</td><td className={`${styles.num} ${tone(pnl)}`}>{signedUsd(pnl)}</td>
      </tr>;
    })}</tbody>
  </table></div>{!positions.length && <EmptyRow>No open paper positions. They appear here when an algo enters a market.</EmptyRow>}</div>;
  else if (view === 'orders') main = <div className={styles.tableCard}><div className={styles.tableScroll}><table className={styles.table}>
    <thead><tr><th>Time</th><th>Side</th><th>Market</th><th>Algo</th><th className={styles.num}>Shares</th><th className={styles.num}>Price</th><th className={styles.num}>Fee</th><th>Why</th></tr></thead>
    <tbody>{fills.map(({ id, fill }) => <tr key={fill.ts + fill.cid}>
      <td className={styles.muted}>{when(fill.ts)}</td><td><span className={fill.side === 'BUY' ? styles.buyTag : styles.sellTag}>{fill.side}</span>{fill.outcome_name}</td>
      <td className={styles.wrap}><b>{fill.question}</b></td><td>{label(id)}</td><td className={styles.num}>{fill.shares.toFixed(2)}</td><td className={styles.num}>{cents(fill.price)}</td>
      <td className={styles.num}>{usd(fill.fee, 3)}</td><td className={styles.muted}>{fill.reason}</td>
    </tr>)}</tbody>
  </table></div>{!fills.length && <EmptyRow>Simulated fills appear here when an algo enters a market.</EmptyRow>}</div>;
  else if (view === 'settled') main = <div className={styles.tableCard}><div className={styles.tableScroll}><table className={styles.table}>
    <thead><tr><th>Settled</th><th>Market</th><th>Algo</th><th>Outcome held</th><th className={styles.num}>Cost</th><th className={styles.num}>Payout</th><th className={styles.num}>P&L</th></tr></thead>
    <tbody>{settled.map(({ id, row }) => <tr key={row.ts + row.cid}>
      <td className={styles.muted}>{when(row.ts)}</td><td className={styles.wrap}><b>{row.question}</b></td><td>{label(id)}</td><td>{row.outcome_name ?? '—'}</td>
      <td className={styles.num}>{usd(row.cost)}</td><td className={styles.num}>{usd(row.payout)}</td><td className={`${styles.num} ${tone(row.pnl)}`}>{signedUsd(row.pnl)}</td>
    </tr>)}</tbody>
    {settled.length > 0 && <tfoot><tr><td colSpan={6}>Total realized</td><td className={`${styles.num} ${tone(realized)}`}>{signedUsd(realized)}</td></tr></tfoot>}
  </table></div>{!settled.length && <EmptyRow>No bets have settled yet. Up/down bets settle in minutes, sports bets within hours, crypto level bets in about a week.</EmptyRow>}</div>;
  else main = <>
    <div className={`${styles.card} ${styles.summary}`}>
      <div><span>Paper capital</span><strong>{usd(capital)}</strong></div>
      <div><span>Equity (marked at bid)</span><strong className={tone(equity - capital)}>{usd(equity)}</strong></div>
      <div><span>Realized P&L</span><strong className={tone(realized)}>{signedUsd(realized)}</strong></div>
      <div><span>Unrealized</span><strong className={tone(open)}>{signedUsd(open)}</strong></div>
    </div>
    {accounts.map(([id, account]) => {
      const book = feed.catalog[id];
      const state = stale(account) ? 'stale' : account.positions.length ? 'in_trade' : 'scanning';
      const winRate = account.n_settled ? (account.n_wins ?? 0) / account.n_settled : null;
      return <div key={id} className={styles.card}>
        <div className={styles.cardHead}>
          <h2>{label(id)}</h2>
          <span className={`${styles.state} ${styles[`state_${state}`]}`}><i />{state === 'stale' ? `Worker offline since ${when(account.updated_at)}` : state === 'in_trade' ? `${account.positions.length} open` : 'Scanning'}</span>
        </div>
        <p className={styles.caption}>{account.description}{account.origin ? ` Modelled on ${account.origin}.` : ''}</p>
        <dl className={styles.stats}>
          <div><dt>Equity</dt><dd className={tone((account.equity ?? account.start_cash) - account.start_cash)}>{usd(account.equity)} <small>{pct((account.equity ?? account.start_cash) / account.start_cash - 1)}</small></dd></div>
          <div><dt>Realized P&L</dt><dd className={tone(account.realized_pnl)}>{signedUsd(account.realized_pnl ?? 0)}</dd></div>
          <div><dt>Settled bets · win rate</dt><dd>{account.n_settled ?? 0} <small>{winRate == null ? '' : `· ${(winRate * 100).toFixed(0)}%`}</small></dd></div>
          <div><dt>Cash · in positions</dt><dd>{usd(account.cash)} <small>· {usd(account.exposure ?? 0)}</small></dd></div>
          <div><dt>Markets scanned · on live feed</dt><dd>{account.candidates ?? '—'} <small>· {account.watching ?? '—'} near a trade · {account.signals ?? 0} signals</small></dd></div>
          <div><dt>Running since</dt><dd><small>{when(account.started_at)}</small></dd></div>
        </dl>
        <div className={styles.chart}><Sparkline points={account.equity_curve || []} /></div>
        {book && <div className={styles.tableScroll}><table className={styles.table}>
          <thead><tr><th>Backtest</th><th className={styles.num}>Bets</th><th className={styles.num}>Win rate</th><th className={styles.num}>Avg price</th><th className={styles.num}>Return per bet</th><th className={styles.num}>t-stat</th><th className={styles.num}>Median hold</th></tr></thead>
          <tbody>{([[book.train_label ?? 'Jun–Sep 2026 (tuned on)', book.train], [book.test_label ?? 'Oct–Nov 2026 (held out)', book.test]] as const).map(([name, row]) => <tr key={name}>
            <td>{name}</td><td className={styles.num}>{row?.n ?? '—'}</td><td className={styles.num}>{row?.win_rate == null ? '—' : `${(row.win_rate * 100).toFixed(0)}%`}</td>
            <td className={styles.num}>{cents(row?.avg_price)}</td><td className={`${styles.num} ${tone(row?.roi_per_bet)}`}>{pct(row?.roi_per_bet)}</td>
            <td className={styles.num}>{row?.t_stat == null ? '—' : row.t_stat.toFixed(1)}</td><td className={styles.num}>{row?.avg_hold_hours == null ? '—' : row.avg_hold_hours < 1 ? `${Math.round(row.avg_hold_hours * 60)}m` : `${row.avg_hold_hours.toFixed(0)}h`}</td>
          </tr>)}</tbody>
        </table></div>}
        {book?.note && <p className={styles.caption} style={{ marginTop: 12 }}>{book.note}</p>}
        {account.last_error && <p className={styles.caption} style={{ marginTop: 12 }}>Last worker error: {account.last_error}</p>}
      </div>;
    })}
  </>;

  return <section className={styles.lab}>
    <div className={styles.heading}>
      <div><h1>Polymarket Algos</h1><p className={styles.subtitle}>Forward test of strategies modelled on top Polymarket wallets. Private to your account.</p></div>
      <span className={styles.paperBadge}><ShieldCheck size={16} /><span><b>Paper trading only</b>No wallet, no orders</span></span>
    </div>
    <div className={styles.tabs}>
      <nav aria-label="Polymarket sections">
        {([['algos', 'Algos', accounts.length], ['positions', 'Positions', positions.length], ['orders', 'Orders', null], ['settled', 'Settled', settled.length]] as const).map(([id, name, count]) => <button key={id} className={view === id ? styles.tabActive : ''} aria-current={view === id ? 'page' : undefined} onClick={() => setView(id)}>{name}{count ? <span>{count}</span> : null}</button>)}
      </nav>
      <div className={styles.tabMeta}>
        <span className={styles.feed}><i className={live ? styles.feedLive : ''} />{live ? 'Live feed' : 'Worker offline'} · {when(lastUpdate)}</span>
        <button className={styles.refresh} onClick={() => void exportTrades()} disabled={exporting} title="Every paper buy and settlement since the start"><Download size={14} />{exporting ? 'Exporting' : 'All trades (CSV)'}</button>
        <button className={styles.refresh} onClick={() => void load()} disabled={loading}><RefreshCw size={14} className={loading ? styles.spin : ''} />{loading ? 'Refreshing' : 'Refresh'}</button>
      </div>
    </div>
    {error && <div className={styles.notice} role="status"><AlertCircle size={16} />{error}<button onClick={() => void load()}>Retry</button></div>}
    <div className={styles.content}>{main}</div>
    <footer className={styles.disclaimer}><ShieldCheck size={15} /><p>Decisions run on Polymarket’s live order-book stream and Binance’s price stream. Fills are simulated against the live ask ladder, with real taker fees and the 5-share minimum; open positions are valued at the best bid. Backtests use historical trade prices, not order books, so they are optimistic. Amounts in USD, times IST.</p></footer>
  </section>;
}
