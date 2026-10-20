'use client';

import { useAuth } from '@/contexts/AuthContext';
import { AlertCircle, ArrowLeft, ChevronRight, Eye, EyeOff, RefreshCw, Search, ShieldCheck } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import AlgoDetail from './AlgoDetail';
import { algoState, clock, isStale, ledgerFills, marketOpen, money, openPnl, scanMessage, stateLabel, time, todayRealized, type BacktestLedger, type Paper, type PaperResponse, type Strategy, type Trade } from './algoData';
import { AlgoIcon, EmptyRow, Pills, PositionTable, tone } from './algoUi';
import styles from './algos.module.css';

const apiBase = (process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');
type View = 'algos' | 'positions' | 'orders';
const VIEWS: View[] = ['algos', 'positions', 'orders'];

export default function AlgoDashboard() {
  const { currentUser } = useAuth();
  const [catalog, setCatalog] = useState<Strategy[]>([]);
  const [paper, setPaper] = useState<PaperResponse | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loadedAt, setLoadedAt] = useState<string | null>(null);
  const [view, setView] = useState<View>('algos');
  const [algoId, setAlgoId] = useState<string | null>(null);
  const [, setTick] = useState(0);

  // The open tab and algo live in the query string (?tab=positions, ?algo=zen_strategy_01) so reloads and back/forward keep them.
  useEffect(() => {
    const read = () => {
      const params = new URLSearchParams(window.location.search);
      const tab = params.get('tab') as View | null;
      setView(tab && VIEWS.includes(tab) ? tab : 'algos');
      setAlgoId(params.get('algo'));
    };
    read();
    window.addEventListener('popstate', read);
    return () => window.removeEventListener('popstate', read);
  }, []);
  const go = useCallback((next: View, algo: string | null = null) => {
    setView(next); setAlgoId(algo);
    const params = new URLSearchParams();
    if (next !== 'algos') params.set('tab', next);
    if (algo) params.set('algo', algo);
    const query = params.toString();
    window.history.pushState(null, '', window.location.pathname + (query ? `?${query}` : ''));
  }, []);

  const authed = useCallback(async (path: string, signal?: AbortSignal) => {
    const token = await currentUser!.getIdToken();
    return fetch(`${apiBase}${path}`, { headers: { Authorization: `Bearer ${token}` }, signal, cache: 'no-store' });
  }, [currentUser]);

  // Catalogue metadata and backtest metrics change only when a strategy is re-published: load once per page load or Refresh.
  const loadCatalog = useCallback(async (signal?: AbortSignal) => {
    const response = await authed('/algos/catalog', signal);
    if (!response.ok) throw new Error(response.status === 401 ? 'Your session has expired. Sign in again.' : 'Strategy catalogue unavailable. Please retry.');
    const body = await response.json() as { strategies: Strategy[] };
    if (!signal?.aborted) setCatalog(body.strategies);
  }, [authed]);

  // The paper feed is the only live data, so it is the only request on the 30-second poll.
  const loadPaper = useCallback(async (signal?: AbortSignal) => {
    const response = await authed('/algos/paper', signal);
    if (!response.ok) throw new Error(response.status === 401 ? 'Your session has expired. Sign in again.' : 'Paper feed unavailable. Your historical results are still available.');
    const body = await response.json() as PaperResponse;
    if (!signal?.aborted) { setPaper(body); setError(''); setLoadedAt(new Date().toISOString()); }
  }, [authed]);

  const run = useCallback(async (task: () => Promise<unknown>, signal?: AbortSignal) => {
    if (!currentUser) return;
    setLoading(true);
    try { await task(); }
    catch (err) { if (!signal?.aborted) setError(err instanceof Error ? err.message : 'Unable to load algo data.'); }
    finally { if (!signal?.aborted) setLoading(false); }
  }, [currentUser]);

  // Backtest ledgers are fetched when an algo's Past trades tab first opens and kept for this page load.
  const backtests = useRef(new Map<string, Promise<BacktestLedger | null>>());
  const loadBacktest = useCallback((id: string) => {
    let pending = backtests.current.get(id);
    if (!pending) {
      pending = authed(`/algos/backtest/${encodeURIComponent(id)}`).then(async response => {
        // Only the route's own 404 means "no ledger"; a generic 404 means the API predates the route.
        if (response.status === 404 && /^No backtest ledger/.test((await response.json().catch(() => ({})) as { detail?: string }).detail || '')) return null;
        if (!response.ok) throw new Error('Backtest ledger unavailable');
        return await response.json() as BacktestLedger;
      });
      pending.catch(() => backtests.current.delete(id));
      backtests.current.set(id, pending);
    }
    return pending;
  }, [authed]);

  const refresh = useCallback(() => { backtests.current.clear(); return run(() => Promise.all([loadCatalog(), loadPaper()])); }, [run, loadCatalog, loadPaper]);

  useEffect(() => {
    const controller = new AbortController();
    void run(() => Promise.all([loadCatalog(controller.signal), loadPaper(controller.signal)]), controller.signal);
    const timer = window.setInterval(() => void run(() => loadPaper(controller.signal), controller.signal), 30_000);
    // Re-render once a minute so market-hours and staleness labels advance without extra API calls.
    const clockTimer = window.setInterval(() => setTick(value => value + 1), 60_000);
    return () => { controller.abort(); window.clearInterval(timer); window.clearInterval(clockTimer); };
  }, [run, loadCatalog, loadPaper]);

  async function follow(id: string, enabled: boolean) {
    if (!currentUser || saving || !paper) return;
    setSaving(true);
    try {
      const token = await currentUser.getIdToken();
      const response = await fetch(`${apiBase}/algos/follow/${id}`, { method: 'PUT', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled }) });
      if (!response.ok) throw new Error('Could not save your selection. Please retry.');
      await loadPaper();
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not save your selection.'); }
    finally { setSaving(false); }
  }

  function downloadLedger(strategyId: string) {
    const rows = paper?.strategies[strategyId]?.closed_positions || [];
    if (!rows.length) return;
    const fields: (keyof Trade)[] = ['signal_id', 'option_type', 'sell_strike', 'buy_strike', 'units', 'entry_ts', 'exit_ts', 'pnl', 'exit_reason'];
    const cell = (value: unknown) => `"${String(value ?? '').replace(/"/g, '""')}"`;
    const csv = [fields.join(','), ...rows.map(row => fields.map(field => cell(row[field])).join(','))].join('\r\n');
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8;' }));
    const link = document.createElement('a'); link.href = url; link.download = `${strategyId}-paper-trades.csv`; link.click(); URL.revokeObjectURL(url);
  }

  const detail = algoId ? catalog.find(item => item.id === algoId) : undefined;
  const openCount = catalog.filter(item => paper?.strategies[item.id]?.open_position).length * 2;

  let main;
  if (!catalog.length) main = <div className={styles.card}><EmptyRow>{loading ? 'Loading strategies…' : error || 'No strategies are listed in the catalogue yet.'}</EmptyRow>{!loading && <button className={styles.outlineButton} onClick={() => void refresh()}>Refresh catalogue</button>}</div>;
  else if (algoId) main = detail ? <AlgoDetail key={detail.id} strategy={detail} account={paper?.strategies[detail.id]} paperLoaded={!!paper} following={!!paper?.following[detail.id]} saving={saving} onFollow={enabled => void follow(detail.id, enabled)} onDownload={() => downloadLedger(detail.id)} loadBacktest={loadBacktest} /> : <div className={styles.card}><EmptyRow>This algo is not in the catalogue.</EmptyRow></div>;
  else if (view === 'positions') main = <PositionsView catalog={catalog} paper={paper} onOpen={id => go(view, id)} />;
  else if (view === 'orders') main = <OrdersView catalog={catalog} paper={paper} />;
  else main = <MyAlgos catalog={catalog} paper={paper} onOpen={id => go(view, id)} />;

  return <section className={styles.lab}>
    <div className={styles.heading}>
      <div><h1>Algo Lab</h1><p className={styles.subtitle}>Follow TradeBud’s option-selling algos and their paper trades.</p></div>
      <span className={styles.paperBadge}><ShieldCheck size={16} /><span><b>Paper trading only</b>No broker orders</span></span>
    </div>
    <div className={styles.tabs}>
      {algoId ? <button className={styles.back} onClick={() => go(view)}><ArrowLeft size={15} />Back to {view === 'algos' ? 'My Algos' : view === 'positions' ? 'Positions' : 'Orders'}</button> : <nav aria-label="Algo Lab sections">
        {([['algos', 'My Algos', catalog.length], ['positions', 'Positions', openCount], ['orders', 'Orders', null]] as const).map(([id, label, count]) => <button key={id} className={view === id ? styles.tabActive : ''} aria-current={view === id ? 'page' : undefined} onClick={() => go(id)}>{label}{count ? <span>{count}</span> : null}</button>)}
      </nav>}
      <div className={styles.tabMeta}>
        <span className={styles.market}><i className={marketOpen() ? styles.marketOpen : ''} />Market {marketOpen() ? 'open' : 'closed'}</span>
        <button className={styles.refresh} onClick={() => void refresh()} disabled={loading} title={loadedAt ? `Updated ${clock(loadedAt)}` : undefined}><RefreshCw size={14} className={loading ? styles.spin : ''} />{loading ? 'Refreshing' : 'Refresh'}</button>
      </div>
    </div>
    {error && <div className={styles.notice} role="status"><AlertCircle size={16} />{error}<button onClick={() => void refresh()}>Retry</button></div>}
    <div className={styles.content}>{main}</div>
    <footer className={styles.disclaimer}><ShieldCheck size={15} /><p>Positions, orders and P&L come from shared paper model accounts, not your brokerage account. Backtests are gross historical simulations. Following an algo saves your selection; it never places orders. All times IST.</p></footer>
  </section>;
}

function MyAlgos({ catalog, paper, onOpen }: { catalog: Strategy[]; paper: PaperResponse | null; onOpen: (id: string) => void }) {
  const [group, setGroup] = useState<'following' | 'all'>('all');
  const [today, setToday] = useState(true);
  const [hidden, setHidden] = useState(false);
  const followed = catalog.filter(item => paper?.following[item.id]);
  const rows = group === 'following' ? followed : catalog;
  const accounts = rows.map(item => paper?.strategies[item.id]).filter((account): account is Paper => !!account);
  const sum = (pick: (account: Paper) => number | null) => accounts.length ? accounts.reduce((total, account) => total + (pick(account) ?? 0), 0) : null;
  const capital = rows.reduce((total, item) => total + (paper?.strategies[item.id]?.capital ?? item.capital), 0);
  const unrealized = sum(openPnl);
  const realized = sum(account => today ? todayRealized(account) : account.realized_pnl);
  const total = realized == null || unrealized == null ? null : realized + unrealized;
  const mask = (value: string) => hidden ? '••••' : value;
  const prefix = today ? 'Today’s' : 'Overall';
  return <>
    <div className={`${styles.card} ${styles.summary}`}>
      <div><span>Model capital</span><strong>{mask(money(capital))}</strong></div>
      <div><span>{prefix} P&L</span><strong className={hidden ? '' : tone(total)}>{mask(money(total))}</strong></div>
      <div><span>{prefix} realized</span><strong className={hidden ? '' : tone(realized)}>{mask(money(realized))}</strong></div>
      <div><span>Unrealized</span><strong className={hidden ? '' : tone(unrealized)}>{mask(money(unrealized))}</strong></div>
      <button className={styles.iconButton} onClick={() => setHidden(value => !value)} aria-label={hidden ? 'Show amounts' : 'Hide amounts'} aria-pressed={hidden}>{hidden ? <EyeOff size={16} /> : <Eye size={16} />}</button>
    </div>
    <div className={styles.toolbar}>
      <Pills label="Algo group" value={group} onChange={setGroup} items={[{ id: 'all', label: 'All algos', count: catalog.length }, { id: 'following', label: 'Following', count: followed.length }]} />
      <Pills label="P&L period" value={today ? 'today' : 'overall'} onChange={value => setToday(value === 'today')} items={[{ id: 'today', label: 'Today' }, { id: 'overall', label: 'Overall' }]} />
    </div>
    <div className={styles.tableCard}><div className={styles.tableScroll}><table className={`${styles.table} ${styles.clickable}`}>
      <thead><tr><th>Algo</th><th>Status</th><th>Position</th><th className={styles.num}>Model capital</th><th className={styles.num}>Unrealized</th><th className={styles.num}>{prefix} realized</th><th aria-label="Open" /></tr></thead>
      <tbody>{rows.map(item => {
        const account = paper?.strategies[item.id];
        const state = algoState(account);
        const realizedValue = today ? todayRealized(account) : account?.realized_pnl;
        return <tr key={item.id} onClick={() => onOpen(item.id)} tabIndex={0} onKeyDown={event => { if (event.key === 'Enter') onOpen(item.id); }}>
          <td><span className={styles.algoCell}><AlgoIcon version={item.version} /><span><b>{item.name}</b><small>{item.category}{paper?.following[item.id] ? ' · Following' : ''}</small></span></span></td>
          <td><span className={`${styles.state} ${styles[`state_${state.replace('-', '_')}`]}`}><i />{stateLabel[state]}</span></td>
          <td className={styles.muted}>{account?.open_position ? `${account.open_position.sell_strike}/${account.open_position.buy_strike} ${account.open_position.option_type}` : '—'}</td>
          <td className={styles.num}>{mask(money(account?.capital ?? item.capital))}</td>
          <td className={`${styles.num} ${hidden ? '' : tone(openPnl(account))}`}>{account?.open_position ? mask(money(account.unrealized_pnl)) : '—'}</td>
          <td className={`${styles.num} ${hidden ? '' : tone(realizedValue)}`}>{realizedValue == null ? '—' : mask(money(realizedValue))}</td>
          <td className={styles.chevron}><ChevronRight size={16} /></td>
        </tr>;
      })}</tbody>
    </table></div>
      {!rows.length && <EmptyRow>You are not following any algo yet. Open one from All algos and choose Follow.</EmptyRow>}
    </div>
    <p className={styles.caption}>Status combines NSE hours with the paper worker heartbeat (stale after 3 minutes without an update). Click an algo for its backtest, paper trades and rules.</p>
  </>;
}

function PositionsView({ catalog, paper, onOpen }: { catalog: Strategy[]; paper: PaperResponse | null; onOpen: (id: string) => void }) {
  const [filter, setFilter] = useState<'all' | 'profit' | 'loss'>('all');
  const rows = catalog.map(strategy => ({ strategy, account: paper?.strategies[strategy.id] }));
  const holding = rows.filter(row => row.account?.open_position);
  const profit = holding.filter(row => (row.account!.unrealized_pnl ?? 0) > 0);
  const loss = holding.filter(row => (row.account!.unrealized_pnl ?? 0) < 0);
  const visible = filter === 'profit' ? profit : filter === 'loss' ? loss : holding;
  const nameFor = new Map(holding.map(row => [row.account!.open_position!.signal_id, row.strategy.name]));
  return <>
    <div className={styles.sectionHead}><h2>Open positions</h2><Pills label="Filter open positions" value={filter} onChange={setFilter} items={[{ id: 'all', label: 'All', count: holding.length * 2 }, { id: 'profit', label: 'In profit', count: profit.length * 2 }, { id: 'loss', label: 'In loss', count: loss.length * 2 }]} /></div>
    {visible.length ? <PositionTable trades={visible.map(row => row.account!.open_position!)} open totalPnl={visible.reduce((total, row) => total + (row.account!.unrealized_pnl ?? 0), 0)} algo={trade => nameFor.get(trade.signal_id) || ''} /> : <div className={styles.tableCard}><EmptyRow>{filter === 'all' ? 'No open paper positions. They appear here once an algo enters a trade.' : `No open positions ${filter === 'profit' ? 'in profit' : 'in loss'}.`}</EmptyRow></div>}
    <div className={styles.sectionHead}><h2>Algo status</h2></div>
    <div className={styles.tableCard}>
      {rows.map(({ strategy, account }) => <button key={strategy.id} className={styles.scanRow} onClick={() => onOpen(strategy.id)}>
        <span className={styles.algoCell}><AlgoIcon version={strategy.version} /><b>{strategy.name}</b></span>
        <span className={`${styles.state} ${styles[`state_${algoState(account).replace('-', '_')}`]}`}><i />{stateLabel[algoState(account)]}</span>
        <span className={`${styles.scanMsg} ${account?.open_position ? tone(account.unrealized_pnl) : ''}`}>{scanMessage(account)}</span>
        <ChevronRight size={16} className={styles.muted} />
      </button>)}
    </div>
    <p className={styles.caption}>Covers the shared paper account of every listed algo{rows.some(row => isStale(row.account)) && marketOpen() ? '; a stale feed means the last mark is not a current price' : ''}. Last worker update {time(rows.map(row => row.account?.updated_at).filter(Boolean).sort().at(-1))}.</p>
  </>;
}

function OrdersView({ catalog, paper }: { catalog: Strategy[]; paper: PaperResponse | null }) {
  const [query, setQuery] = useState('');
  const fills = useMemo(() => ledgerFills(catalog, paper), [catalog, paper]);
  const needle = query.trim().toLowerCase();
  const visible = fills.filter(fill => !needle || `${fill.name} ${fill.algo} ${fill.kind}`.toLowerCase().includes(needle));
  return <>
    <div className={styles.sectionHead}><h2>Simulated orders <span className={styles.count}>{fills.length}</span></h2><label className={styles.search}><Search size={14} /><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search orders" aria-label="Search orders" /></label></div>
    <div className={styles.tableCard}><div className={styles.tableScroll}><table className={styles.table}>
      <thead><tr><th>Time</th><th>Side</th><th>Instrument</th><th>Algo</th><th className={styles.num}>Qty</th><th>Type</th><th className={styles.num}>Avg price</th><th className={styles.num}>LTP</th></tr></thead>
      <tbody>{visible.map(fill => <tr key={fill.key}>
        <td className={styles.muted}>{clock(fill.ts)}</td>
        <td><span className={fill.side === 'B' ? styles.buyTag : styles.sellTag}>{fill.side === 'B' ? 'BUY' : 'SELL'}</span></td>
        <td><b>{fill.name}</b></td>
        <td>{fill.algo}</td>
        <td className={styles.num}>{fill.qty}</td>
        <td className={styles.muted}>Paper {fill.kind.toLowerCase()}</td>
        <td className={styles.num}>{fill.price == null ? '—' : fill.price.toFixed(2)}</td>
        <td className={styles.num}>{fill.ltp == null ? '—' : fill.ltp.toFixed(2)}</td>
      </tr>)}</tbody>
    </table></div>
      {!visible.length && <EmptyRow>{needle ? 'No orders match your search.' : 'When an algo enters or exits a paper trade, its simulated fills appear here.'}</EmptyRow>}
    </div>
    <p className={styles.caption}>Reconstructed from the paper ledger: each spread is two legs on entry and two on exit. Nothing is sent to a broker or exchange.</p>
  </>;
}
