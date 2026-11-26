'use client';

import { useAuth } from '@/contexts/AuthContext';
import { Activity, AlertCircle, ArrowLeft, ArrowUpDown, Banknote, ChevronRight, Eye, EyeOff, RefreshCw, Search, ShieldCheck, Star, TrendingUp, Wallet } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { AccessBanner, AccessCard, openAccess, type LabAccess } from './AlgoAccessCard';
import AlgoDetail from './AlgoDetail';
import type { LoadRobustness, Robustness } from './AlgoRobustness';
import AlgoLive from './AlgoLive';
import AlgoResearch from './AlgoResearch';
import type { LiveActions, LiveResponse } from './liveData';
import type { Research } from './researchData';
import { useAlgoAccess } from './useAlgoAccess';
import { PERIODS, algoSlug, algoState, blurb, clock, equityPoints, inTrade, isStale, ledgerFills, marketOpen, money, openPnl, percent, periodName, periodReturn, periodShort, scanMessage, stateLabel, strikesLabel, time, todayRealized, type BacktestLedger, type EquityDays, type Paper, type PaperResponse, type Period, type Strategy, type Trade } from './algoData';
import { AlgoIcon, BacktestTag, EmptyRow, Pills, PositionTable, Return, Sparkline, tone } from './algoUi';
import styles from './algos.module.css';

const apiBase = (process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');
type View = 'algos' | 'positions' | 'orders' | 'live' | 'research';
const VIEWS: View[] = ['algos', 'positions', 'orders', 'live', 'research'];
// The 'live' view is the order desk. Live trading is switched off, so it is shown as what it does today: dry run.
const VIEW_NAMES: Record<View, string> = { algos: 'My Algos', positions: 'Positions', orders: 'Orders', live: 'Dry run', research: 'Research' };

export default function AlgoDashboard() {
  const { currentUser } = useAuth();
  const access = useAlgoAccess();
  const [catalog, setCatalog] = useState<Strategy[]>([]);
  const [paper, setPaper] = useState<PaperResponse | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loadedAt, setLoadedAt] = useState<string | null>(null);
  const [, setTick] = useState(0);

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
  // Daily backtest P&L for an algo's equity chart: the API derives it from that same ledger. Kept for this page load.
  const equities = useRef(new Map<string, Promise<EquityDays | null>>());
  const loadEquity = useCallback((id: string) => {
    let pending = equities.current.get(id);
    if (!pending) {
      pending = authed(`/algos/equity/${encodeURIComponent(id)}`).then(async response => response.ok ? await response.json() as EquityDays : null);
      pending.catch(() => equities.current.delete(id));
      equities.current.set(id, pending);
    }
    return pending;
  }, [authed]);

  // Reliability-check chart data for an algo's Robustness tab, fetched when the tab first opens. Kept for this page load.
  const robustness = useRef(new Map<string, Promise<Robustness | null>>());
  const loadRobustness = useCallback((id: string) => {
    let pending = robustness.current.get(id);
    if (!pending) {
      pending = authed(`/algos/robustness/${encodeURIComponent(id)}`).then(async response => {
        if (response.status === 404 && /^No robustness/.test((await response.json().catch(() => ({})) as { detail?: string }).detail || '')) return null;
        if (!response.ok) throw new Error('Robustness checks unavailable');
        return await response.json() as Robustness;
      });
      pending.catch(() => robustness.current.delete(id));
      robustness.current.set(id, pending);
    }
    return pending;
  }, [authed]);

  // Research notes (owner only) are fetched when the Research tab first opens and kept for this page load.
  const researchNotes = useRef<Promise<Research> | null>(null);
  const loadResearch = useCallback(() => {
    if (!researchNotes.current) {
      researchNotes.current = authed('/algos/research').then(async response => {
        if (!response.ok) throw new Error('Research notes unavailable');
        return await response.json() as Research;
      });
      researchNotes.current.catch(() => { researchNotes.current = null; });
    }
    return researchNotes.current;
  }, [authed]);

  // Live trading (owner only): settings are stored through the API; the worker's order desk acts on them.
  const liveActions = useMemo<LiveActions>(() => {
    const send = async (path: string, method: 'PUT' | 'POST', body?: unknown) => {
      const token = await currentUser!.getIdToken();
      const response = await fetch(`${apiBase}${path}`, { method, headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });
      if (!response.ok) {
        const detail = (await response.json().catch(() => ({})) as { detail?: unknown }).detail;
        throw new Error(typeof detail === 'string' ? detail : 'Could not save live settings. Please retry.');
      }
    };
    return {
      load: async () => {
        const response = await authed('/algos/live');
        if (!response.ok) throw new Error('Live trading status unavailable');
        return await response.json() as LiveResponse;
      },
      saveStrategy: (id, setting) => send(`/algos/live/strategies/${encodeURIComponent(id)}`, 'PUT', setting),
      saveAccount: change => send('/algos/live/account', 'PUT', change),
      exitStrategy: id => send(`/algos/live/strategies/${encodeURIComponent(id)}/exit`, 'POST'),
    };
  }, [authed, currentUser]);

  const refresh = useCallback(() => { backtests.current.clear(); equities.current.clear(); return run(() => Promise.all([loadCatalog(), loadPaper()])); }, [run, loadCatalog, loadPaper]);

  useEffect(() => {
    const controller = new AbortController();
    void run(() => Promise.all([loadCatalog(controller.signal), loadPaper(controller.signal)]), controller.signal);
    const timer = window.setInterval(() => void run(() => loadPaper(controller.signal), controller.signal), 30_000);
    // Re-render once a minute so market-hours and staleness labels advance without extra API calls.
    const clockTimer = window.setInterval(() => setTick(value => value + 1), 60_000);
    return () => { controller.abort(); window.clearInterval(timer); window.clearInterval(clockTimer); };
  }, [run, loadCatalog, loadPaper]);

  // A grant takes effect on the next paper poll, which then carries the trades.
  const requestAccess = access.requestAccess;
  const labAccess = useMemo<LabAccess>(() => ({ allowed: access.allowed, owner: access.owner, request: access.request, requestAccess }), [access.allowed, access.owner, access.request, requestAccess]);

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
    const fields: (keyof Trade)[] = ['signal_id', 'option_type', 'sell_strike', 'buy_strike', 'units', 'entry_ts', 'exit_ts', 'pnl', 'exit_reason', 'structure'];
    const cell = (value: unknown) => `"${String(value ?? '').replace(/"/g, '""')}"`;
    const csv = [fields.join(','), ...rows.map(row => fields.map(field => cell(row[field])).join(','))].join('\r\n');
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8;' }));
    const link = document.createElement('a'); link.href = url; const listed = catalog.find(item => item.id === strategyId); link.download = `${listed ? algoSlug(listed) : 'algo'}-paper-trades.csv`; link.click(); URL.revokeObjectURL(url);
  }

  return <AlgoLab catalog={catalog} paper={paper} error={error} loading={loading} saving={saving} loadedAt={loadedAt} access={labAccess} onRefresh={() => void refresh()} onFollow={(id, enabled) => void follow(id, enabled)} onDownload={downloadLedger} loadBacktest={loadBacktest} loadEquity={loadEquity} loadRobustness={loadRobustness} loadResearch={loadResearch} live={liveActions} />;
}

export type AlgoLabProps = { catalog: Strategy[]; paper: PaperResponse | null; error: string; loading: boolean; saving: boolean; loadedAt: string | null; access?: LabAccess; onRefresh: () => void; onFollow: (id: string, enabled: boolean) => void; onDownload: (id: string) => void; loadBacktest: (id: string) => Promise<BacktestLedger | null>; loadEquity?: (id: string) => Promise<EquityDays | null>; loadRobustness?: LoadRobustness; loadResearch?: () => Promise<Research>; live?: LiveActions };

/** Everything on screen, given data. Holds only view state: the open tab, the open algo and the return period.
 *  Cards and backtest figures show for everyone; the trades sections show only when `access.allowed`. */
export function AlgoLab({ catalog, paper, error, loading, saving, loadedAt, access = openAccess, onRefresh, onFollow, onDownload, loadBacktest, loadEquity, loadRobustness, loadResearch, live }: AlgoLabProps) {
  const [view, setView] = useState<View>('algos');
  const [algoKey, setAlgoKey] = useState<string | null>(null);   // the ?algo= value: a name slug (or an id from an old link)
  const [period, setPeriod] = useState<Period>('1y');

  // The open tab and algo live in the query string (?tab=positions, ?algo=skew-afternoon-credit) so reloads and back/forward keep them.
  useEffect(() => {
    const read = () => {
      const params = new URLSearchParams(window.location.search);
      const tab = params.get('tab') as View | null;
      setView(tab && VIEWS.includes(tab) ? tab : 'algos');
      setAlgoKey(params.get('algo'));
    };
    read();
    window.addEventListener('popstate', read);
    return () => window.removeEventListener('popstate', read);
  }, []);
  const go = useCallback((next: View, id: string | null = null) => {
    const opened = id ? catalog.find(item => item.id === id) : undefined;
    const algo = opened ? algoSlug(opened) : id;
    setView(next); setAlgoKey(algo);
    const params = new URLSearchParams();
    if (next !== 'algos') params.set('tab', next);
    if (algo) params.set('algo', algo);
    const query = params.toString();
    window.history.pushState(null, '', window.location.pathname + (query ? `?${query}` : ''));
  }, [catalog]);

  const detail = algoKey ? catalog.find(item => algoSlug(item) === algoKey || item.id === algoKey) : undefined;
  const algoId = detail?.id ?? algoKey;
  const openCount = catalog.filter(item => inTrade(paper?.strategies[item.id])).length * 2;

  let main;
  if (!catalog.length) main = <div className={styles.card}><EmptyRow>{loading ? 'Loading strategies…' : error || 'No strategies are listed in the catalogue yet.'}</EmptyRow>{!loading && <button className={styles.outlineButton} onClick={onRefresh}>Refresh catalogue</button>}</div>;
  else if (algoId) main = <div className={styles.split}>
    <AlgoRail catalog={catalog} activeId={algoId} period={period} onPeriod={setPeriod} onOpen={id => go(view, id)} />
    <div className={styles.splitMain}>{detail ? <AlgoDetail key={detail.id} strategy={detail} account={paper?.strategies[detail.id]} paperLoaded={!!paper} following={!!paper?.following[detail.id]} saving={saving} period={period} onFollow={enabled => onFollow(detail.id, enabled)} onDownload={() => onDownload(detail.id)} loadBacktest={loadBacktest} loadEquity={loadEquity} loadRobustness={loadRobustness} access={access} /> : <div className={styles.card}><EmptyRow>This algo is not in the catalogue.</EmptyRow></div>}</div>
  </div>;
  // Research names the rules of unlisted strategies: the owner's only, like the rules on an algo's page.
  // The order desk's settings are the owner's alone (the API refuses everyone else).
  else if (view === 'live') main = access.owner && live ? <AlgoLive catalog={catalog} actions={live} /> : <div className={styles.card}><EmptyRow>Dry run is not available on this account.</EmptyRow></div>;
  else if (view === 'research') main = access.owner && loadResearch ? <AlgoResearch load={loadResearch} catalog={catalog} /> : <div className={styles.card}><EmptyRow>Research notes are not shared.</EmptyRow></div>;
  else if (!access.allowed && view !== 'algos') main = <AccessCard access={access} what={view === 'positions' ? 'Open positions' : 'Simulated orders'} />;
  else if (view === 'positions') main = <PositionsView catalog={catalog} paper={paper} onOpen={id => go(view, id)} />;
  else if (view === 'orders') main = <OrdersView catalog={catalog} paper={paper} />;
  else main = <MyAlgos catalog={catalog} paper={paper} period={period} owner={access.owner} onPeriod={setPeriod} onOpen={id => go(view, id)} />;

  return <section className={styles.lab}>
    <div className={styles.heading}>
      <div><h1>Algo Lab</h1><p className={styles.subtitle}>Follow TradeBud’s option-selling algos and their paper trades.</p></div>
      <span className={styles.paperBadge}><ShieldCheck size={16} /><span><b>Paper trading only</b>No broker orders</span></span>
    </div>
    <div className={styles.tabs}>
      {algoId ? <button className={styles.back} onClick={() => go(view)}><ArrowLeft size={15} />Back to {VIEW_NAMES[view]}</button> : <nav aria-label="Algo Lab sections">
        {([['algos', 'My Algos', catalog.length], ['positions', 'Positions', openCount], ['orders', 'Orders', null], ...(access.owner && live ? [['live', VIEW_NAMES.live, null] as const] : []), ...(access.owner && loadResearch ? [['research', 'Research', null] as const] : [])] as const).map(([id, label, count]) => <button key={id} className={view === id ? styles.tabActive : ''} aria-current={view === id ? 'page' : undefined} onClick={() => go(id)}>{label}{count ? <span>{count}</span> : null}</button>)}
      </nav>}
      <div className={styles.tabMeta}>
        <span className={styles.market}><i className={marketOpen() ? styles.marketOpen : ''} />Market {marketOpen() ? 'open' : 'closed'}</span>
        <button className={styles.refresh} onClick={onRefresh} disabled={loading} title={loadedAt ? `Updated ${clock(loadedAt)}` : undefined}><RefreshCw size={14} className={loading ? styles.spin : ''} />{loading ? 'Refreshing' : 'Refresh'}</button>
      </div>
    </div>
    {error && <div className={styles.notice} role="status"><AlertCircle size={16} />{error}<button onClick={onRefresh}>Retry</button></div>}
    {!access.allowed && catalog.length > 0 && <AccessBanner access={access} />}
    <div className={styles.content}>{main}</div>
    <footer className={styles.disclaimer}><ShieldCheck size={15} /><p>Positions, orders and P&L come from shared paper model accounts, not your brokerage account. Backtests are gross historical simulations. Following an algo saves your selection; it never places orders. All times IST.</p></footer>
  </section>;
}

const matches = (item: Strategy, needle: string) => !needle || `${item.name} ${item.category} ${item.underlying} ${item.version} ${item.summary || ''}`.toLowerCase().includes(needle);

type Sort = 'returns' | 'drawdown' | 'winrate' | 'name';
const SORTS: { id: Sort; label: string }[] = [{ id: 'returns', label: 'Highest return' }, { id: 'drawdown', label: 'Lowest drawdown' }, { id: 'winrate', label: 'Highest win rate' }, { id: 'name', label: 'Name' }];

function MyAlgos({ catalog, paper, period, owner, onPeriod, onOpen }: { catalog: Strategy[]; paper: PaperResponse | null; period: Period; owner: boolean; onPeriod: (period: Period) => void; onOpen: (id: string) => void }) {
  const [group, setGroup] = useState<'following' | 'all'>('all');
  const [today, setToday] = useState(true);
  const [hidden, setHidden] = useState(false);
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState<Sort>('returns');
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
  const needle = query.trim().toLowerCase();
  const cards = rows.filter(item => matches(item, needle)).sort((a, b) =>
    sort === 'name' ? a.name.localeCompare(b.name)
      : sort === 'drawdown' ? Math.abs(a.metrics.max_drawdown_pct) - Math.abs(b.metrics.max_drawdown_pct)
      : sort === 'winrate' ? b.metrics.win_rate_pct - a.metrics.win_rate_pct
      : periodReturn(b, period) - periodReturn(a, period));
  return <>
    <div className={`${styles.card} ${styles.summary}`}>
      <div><Wallet size={20} strokeWidth={1.5} /><p><span>Model capital</span><strong>{mask(money(capital))}</strong></p></div>
      <div><TrendingUp size={20} strokeWidth={1.5} /><p><span>{prefix} P&L</span><strong className={hidden ? '' : tone(total)}>{mask(money(total))}</strong></p></div>
      <div><Banknote size={20} strokeWidth={1.5} /><p><span>{prefix} realized</span><strong className={hidden ? '' : tone(realized)}>{mask(money(realized))}</strong></p></div>
      <div><Activity size={20} strokeWidth={1.5} /><p><span>Unrealized</span><strong className={hidden ? '' : tone(unrealized)}>{mask(money(unrealized))}</strong></p></div>
      <div className={styles.summaryControls}>
        <Pills label="P&L period" value={today ? 'today' : 'overall'} onChange={value => setToday(value === 'today')} items={[{ id: 'today', label: 'Today' }, { id: 'overall', label: 'Overall' }]} />
        <button className={styles.iconButton} onClick={() => setHidden(value => !value)} aria-label={hidden ? 'Show amounts' : 'Hide amounts'} aria-pressed={hidden}>{hidden ? <EyeOff size={16} /> : <Eye size={16} />}</button>
      </div>
    </div>
    <div className={styles.toolbar}>
      <Pills label="Algo group" value={group} onChange={setGroup} items={[{ id: 'all', label: 'All algos', count: catalog.length }, { id: 'following', label: 'Following', count: followed.length }]} />
      <div className={styles.toolbarEnd}>
        <label className={styles.search}><Search size={14} /><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search algos" aria-label="Search algos" /></label>
        <Pills label="Backtest return period" value={period} onChange={onPeriod} items={PERIODS.map(id => ({ id, label: periodShort[id] }))} />
        <label className={styles.sort}><ArrowUpDown size={14} /><span>Sort</span><select value={sort} onChange={event => setSort(event.target.value as Sort)} aria-label="Sort algos">{SORTS.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
      </div>
    </div>
    {cards.length ? <div className={styles.algoGrid}>{cards.map((item, index) => {
      const account = paper?.strategies[item.id];
      const state = algoState(account);
      const position = account?.open_position;
      const holding = inTrade(account);
      const realizedValue = today ? todayRealized(account) : account?.realized_pnl;
      const livePnl = holding ? account!.unrealized_pnl : realizedValue;
      return <button key={item.id} className={styles.algoCard} style={{ '--i': index } as CSSProperties} onClick={() => onOpen(item.id)} aria-label={`Open ${item.name}`}>
        {paper?.following[item.id] && <span className={styles.cornerTag}>Following</span>}
        <span className={styles.cardBody}>
          <span className={styles.cardTop}>
            <AlgoIcon version={item.version} size="lg" />
            <span className={styles.cardName}><b>{item.name}</b><small>{item.underlying}<i />{item.category}</small></span>
          </span>
          <span className={styles.cardDesc}>{blurb(item, owner)}</span>
          <span className={styles.cardChart}><BacktestTag /><Sparkline values={equityPoints(item).map(point => point.value)} label={`Backtest equity curve for ${item.name}`} /></span>
          <span className={styles.cardStats}>
            <span><small>Model capital</small><b>{mask(money(account?.capital ?? item.capital))}</b></span>
            <span><small>{periodShort[period]} returns</small><b><Return value={periodReturn(item, period)} /></b></span>
            <span><small>Max drawdown</small><b>{percent(-Math.abs(item.metrics.max_drawdown_pct))}</b></span>
          </span>
        </span>
        <span className={styles.cardLive}>
          <span className={`${styles.state} ${styles[`state_${state.replace('-', '_')}`]}`}><i />{stateLabel[state]}{position ? <em>{strikesLabel(position)} {position.option_type}</em> : null}</span>
          <span className={styles.cardPnl}><small>{holding ? 'Unrealized' : `${prefix} realized`}</small><b className={hidden ? '' : tone(livePnl)}>{livePnl == null ? '—' : mask(money(livePnl))}</b></span>
          <ChevronRight size={16} className={styles.cardGo} aria-hidden="true" />
        </span>
      </button>;
    })}</div> : <div className={styles.tableCard}><EmptyRow>{needle ? 'No algos match your search.' : 'You are not following any algo yet. Open one from All algos and choose Follow.'}</EmptyRow></div>}
    <p className={styles.caption}>Returns are gross backtest figures on fixed model capital; the curve on each card is the full backtest equity. Status combines NSE hours with the paper worker heartbeat (stale after 3 minutes without an update).</p>
  </>;
}

/** Left rail on the algo page: every algo ranked by backtest return for the chosen period. */
function AlgoRail({ catalog, activeId, period, onPeriod, onOpen }: { catalog: Strategy[]; activeId: string; period: Period; onPeriod: (period: Period) => void; onOpen: (id: string) => void }) {
  const [query, setQuery] = useState('');
  const needle = query.trim().toLowerCase();
  const rows = catalog.filter(item => matches(item, needle)).sort((a, b) => periodReturn(b, period) - periodReturn(a, period));
  return <aside className={styles.rail} aria-label="All algos">
    <label className={styles.search}><Search size={14} /><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search for algo name, kind etc" aria-label="Search algos" /></label>
    <div className={styles.railCard}>
      <div className={styles.railHead}><Star size={13} />Top algos by return<span>{catalog.length}</span></div>
      <div className={styles.railList}>
        {rows.map(item => <button key={item.id} className={item.id === activeId ? styles.railActive : ''} aria-current={item.id === activeId ? 'page' : undefined} onClick={() => onOpen(item.id)}>
          <span className={styles.railName}><b>{item.name}</b><small>{item.underlying}<i />Capital {money(item.capital)}</small></span>
          <span className={styles.railRet}><Return value={periodReturn(item, period)} /><small>{periodName[period]}</small></span>
        </button>)}
        {!rows.length && <EmptyRow>No algos match your search.</EmptyRow>}
      </div>
      <div className={styles.railFoot} role="group" aria-label="Backtest return period">{PERIODS.map(id => <button key={id} className={period === id ? styles.railPeriodActive : ''} aria-pressed={period === id} onClick={() => onPeriod(id)}>{periodShort[id].toLowerCase()}</button>)}<BacktestTag /></div>
    </div>
  </aside>;
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
