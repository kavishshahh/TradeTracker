'use client';

import { useAuth } from '@/contexts/AuthContext';
import { Activity, ArrowDownRight, ArrowUpRight, Check, FlaskConical, RefreshCw, Radio, ShieldCheck, TrendingUp, Layers, AlertCircle } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import styles from './algos.module.css';

type Strategy = { id: string; name: string; version: string; description: string; underlying: string; category: string; capital: number; period_start: string; period_end: string; limitations: string; rules: { label: string; description: string }[]; metrics: { total_pnl: number; trade_count: number; win_rate_pct: number; cagr_pct: number; max_drawdown_pct: number; return_1m_pct: number; return_3m_pct: number; return_6m_pct: number }; monthly: { month: string; pnl: number; closed_trades: number; win_rate_pct: number | null; return_pct: number }[] };
type Trade = { signal_id: string; status: string; option_type: string; sell_strike: number; buy_strike: number; units: number; lots: number; entry_ts: string; expiry: string; exit_ts: string | null; pnl: number | null; stop_loss: number; target: number | null; exit_due: string; sell_price: number; buy_price: number; exit_reason: string | null };
type Paper = { execution: string; updated_at: string; last_evaluation: string | null; status: string; capital: number; alpha: number | null; alpha2: number | null; signal_at: string | null; realized_pnl: number | null; unrealized_pnl: number | null; valuation_ts: string | null; closed_trades: number; win_rate_pct: number | null; open_position: Trade | null; closed_positions: Trade[]; ledger_limit: number };
type PaperResponse = { following: Record<string, boolean>; strategies: Record<string, Paper | null> };
const money = (value: number | null | undefined) => value == null ? '—' : new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(value);
const pnlClass = (value: number | null | undefined) => value == null || value === 0 ? '' : value < 0 ? styles.red : styles.green;
const percent = (value: number | null | undefined) => value == null ? '—' : `${value.toFixed(2)}%`;
const time = (value: string | null | undefined) => value ? new Date(value).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—';
const apiBase = (process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');

export default function AlgoDashboard() {
  const { currentUser } = useAuth();
  const [catalog, setCatalog] = useState<Strategy[]>([]);
  const [selected, setSelected] = useState('');
  const [view, setView] = useState<'backtest' | 'paper'>('paper');
  const [tab, setTab] = useState<'overview' | 'trades' | 'rules'>('overview');
  const [paper, setPaper] = useState<PaperResponse | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const strategy = catalog.find(item => item.id === selected) || catalog[0];
  const account = paper?.strategies[selected];
  const following = paper?.following[selected] || false;
  const stale = account ? Date.now() - Date.parse(account.updated_at) > 180_000 : true;
  const markStale = account?.valuation_ts ? Date.now() - Date.parse(account.valuation_ts) > 180_000 : true;

  const load = useCallback(async (signal?: AbortSignal) => {
    if (!currentUser) return;
    setLoading(true);
    try {
      const token = await currentUser.getIdToken();
      const catalogueResponse = await fetch(`${apiBase}/algos/catalog`, { headers: { Authorization: `Bearer ${token}` }, signal, cache: 'no-store' });
      if (!catalogueResponse.ok) throw new Error(catalogueResponse.status === 401 ? 'Your session has expired. Sign in again.' : 'Strategy catalogue unavailable. Please retry.');
      const catalogueBody = await catalogueResponse.json() as { strategies: Strategy[] };
      if (!signal?.aborted) {
        setCatalog(catalogueBody.strategies);
        setSelected(previous => catalogueBody.strategies.some(item => item.id === previous) ? previous : catalogueBody.strategies[0]?.id || '');
      }
      const response = await fetch(`${apiBase}/algos/paper`, { headers: { Authorization: `Bearer ${token}` }, signal, cache: 'no-store' });
      if (!response.ok) throw new Error(response.status === 401 ? 'Your session has expired. Sign in again.' : 'Paper feed unavailable. Your historical results are still available.');
      const body = await response.json() as PaperResponse;
      if (!signal?.aborted) { setPaper(body); setError(''); }
    } catch (err) {
      if (!signal?.aborted) setError(err instanceof Error ? err.message : 'Unable to load paper feed.');
    } finally { if (!signal?.aborted) setLoading(false); }
  }, [currentUser]);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    const timer = window.setInterval(() => void load(controller.signal), 30_000);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [load]);

  async function follow() {
    if (!currentUser || saving || !paper) return;
    setSaving(true);
    try {
      const token = await currentUser.getIdToken();
      const response = await fetch(`${apiBase}/algos/follow/${selected}`, { method: 'PUT', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled: !following }) });
      if (!response.ok) throw new Error('Could not save your selection. Please retry.');
      await load();
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not save your selection.'); }
    finally { setSaving(false); }
  }

  function downloadLedger() {
    const rows = account?.closed_positions || [];
    if (!rows.length) return;
    const fields: (keyof Trade)[] = ['signal_id', 'option_type', 'sell_strike', 'buy_strike', 'units', 'entry_ts', 'exit_ts', 'pnl', 'exit_reason'];
    const cell = (value: unknown) => `"${String(value ?? '').replace(/"/g, '""')}"`;
    const csv = [fields.join(','), ...rows.map(row => fields.map(field => cell(row[field])).join(','))].join('\r\n');
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8;' }));
    const link = document.createElement('a'); link.href = url; link.download = `${selected}-paper-trades.csv`; link.click(); URL.revokeObjectURL(url);
  }

  if (!strategy) return <section className={styles.lab}><Empty title={loading ? 'Loading strategies…' : error ? 'Catalogue unavailable' : 'No strategies listed'} text={error || 'Strategy records are loaded from Firestore.'} /><button className={styles.outlineButton} onClick={() => void load()} disabled={loading}>Refresh catalogue</button></section>;

  const metrics = view === 'backtest' ? [
    ['Realized profit', money(strategy.metrics.total_pnl), `Gross • fixed ${money(strategy.capital)} capital`],
    ['Win rate', percent(strategy.metrics.win_rate_pct), `${strategy.metrics.trade_count} closed trades`],
    ['CAGR equivalent', percent(strategy.metrics.cagr_pct), 'Annualized • fixed sizing'],
    ['Maximum drawdown', percent(Math.abs(strategy.metrics.max_drawdown_pct)), 'Realized losses only']
  ] : [
    ['Paper realized P&L', money(account?.realized_pnl), 'Gross • closed positions'],
    ['Open position P&L', money(account?.unrealized_pnl), account?.valuation_ts ? `Marked ${time(account.valuation_ts)}${markStale ? ' · stale' : ''}` : 'Waiting for synchronized quotes'],
    ['Paper win rate', percent(account?.win_rate_pct), account ? `${account.closed_trades} closed trades` : 'No paper feed yet'],
    ['Model capital', money(account?.capital), 'Shared strategy model account']
  ];

  return <section className={styles.lab}>
    <div className={styles.heading}><div><p className={styles.eyebrow}>TRADEBUD / ALGO LAB</p><h1>Algo Lab</h1><p className={styles.subtitle}>Explore strategies, compare performance, and follow paper trades.</p></div><div className={styles.modeBadge}><ShieldCheck size={17} /><div><strong>Paper trading only</strong><span>No broker orders</span></div></div></div>
    <div className={styles.topline}><span><span className={styles.dot} /> Strategies <span className={styles.muted}>/ {catalog.length} available</span></span><span className={styles.muted}>All times IST · INR</span></div>
    <div className={styles.strategyGrid} role="group" aria-label="Select strategy">{catalog.map(item => <button key={item.id} className={`${styles.strategyCard} ${selected === item.id ? styles.selected : ""}`} onClick={() => { setSelected(item.id); setTab("overview"); }} aria-pressed={selected === item.id}><span className={styles.number}>{item.version}</span><span className={styles.strategyName}>{item.name}</span><span className={styles.tag}>{item.underlying}</span>{selected === item.id && <Check size={15} />}</button>)}</div>
    <div className={styles.workspaceHeader}><div><h2>{strategy.name} <span className={styles.tag}>{strategy.underlying}</span></h2><p>{view === 'backtest' ? `${strategy.period_start} – ${strategy.period_end} · historical simulation` : 'Forward signals and the shared paper account'}</p></div><div className={styles.actions}><div className={styles.segment}><button className={view === 'backtest' ? styles.activeSegment : ''} aria-pressed={view === 'backtest'} onClick={() => setView('backtest')}><FlaskConical size={14} /> Backtest</button><button className={view === 'paper' ? styles.activeSegment : ''} aria-pressed={view === 'paper'} onClick={() => setView('paper')}><Radio size={14} /> Paper feed</button></div><button className={styles.follow} onClick={() => void follow()} disabled={saving || !paper}>{saving ? 'Saving…' : following ? 'Following · Unfollow' : 'Follow paper strategy'}{!following && <ArrowUpRight size={15} />}</button></div></div>
    {error && <div className={styles.notice} role="status"><AlertCircle size={16} />{error}<button onClick={() => void load()}>Retry</button></div>}
    <div className={styles.stats}>{metrics.map(([label, value, note], index) => <div key={label}><p>{label}</p><strong className={view === 'paper' ? pnlClass(index === 0 ? account?.realized_pnl : index === 1 ? account?.unrealized_pnl : null) : pnlClass(index === 0 ? strategy.metrics.total_pnl : index === 2 ? strategy.metrics.cagr_pct : index === 3 ? -Math.abs(strategy.metrics.max_drawdown_pct) : null)}>{value}</strong><span>{note}</span></div>)}</div>
    <div className={styles.tabs}><div>{(['overview', 'trades', 'rules'] as const).map(item => <button key={item} className={tab === item ? styles.activeTab : ''} aria-pressed={tab === item} onClick={() => setTab(item)}>{item === 'overview' ? (view === 'paper' ? 'Paper account' : 'Performance') : item === 'trades' ? 'Paper trades' : 'Strategy rules'}</button>)}</div><button className={styles.refresh} onClick={() => void load()} disabled={loading}><RefreshCw size={14} className={loading ? styles.spin : ''} />{loading ? 'Refreshing' : 'Refresh feed'}</button></div>
    {tab === 'overview' && (view === 'backtest' ? <div className={styles.performance}><div className={styles.chart}><div className={styles.sectionTitle}><div><p className={styles.eyebrow}>PERFORMANCE</p><h3>Monthly realized P&L</h3></div><span className={styles.chartLegend}><i />Profit <i className={styles.lossLegend} />Loss</span></div><MonthlyChart months={strategy.monthly} /><p className={styles.caption}>Gross P&L booked on exit date. First and last months are partial.</p></div><div className={styles.returnPanel}><TrendingUp size={22} /><h3>Trailing returns</h3><p>Trailing returns on fixed capital</p>{[['1 month', strategy.metrics.return_1m_pct], ['3 months', strategy.metrics.return_3m_pct], ['6 months', strategy.metrics.return_6m_pct]].map(([label, value]) => <div className={styles.returnRow} key={label as string}><span>{label}</span><strong className={(value as number) < 0 ? styles.red : styles.green}>{percent(value as number)}{(value as number) < 0 ? <ArrowDownRight size={15} /> : <ArrowUpRight size={15} />}</strong></div>)}<span className={styles.small}>Costs and intratrade drawdowns are excluded.</span></div><div className={styles.monthTable}><h3>Month by month</h3><div className={styles.tableScroll}><table><thead><tr><th>Month</th><th>Closed trades</th><th>Win rate</th><th>Return</th><th>Realized P&L</th></tr></thead><tbody>{strategy.monthly.map(month => <tr key={month.month}><td>{monthLabel(month.month)}</td><td>{month.closed_trades}</td><td>{percent(month.win_rate_pct)}</td><td className={month.return_pct < 0 ? styles.red : styles.green}>{percent(month.return_pct)}</td><td className={month.pnl < 0 ? styles.red : styles.green}>{money(month.pnl)}</td></tr>)}</tbody></table></div></div></div> : <div className={styles.paperPanel}><div className={styles.sectionTitle}><h3><Activity size={18} /> Paper account</h3><span className={styles.chip}>{!account ? 'AWAITING WORKER' : stale ? 'STALE FEED' : 'FEED CONNECTED'}</span></div>{!account ? <Empty title="The first signal starts here." text="Once the paper worker is deployed, this account will show entries, exits and marked P&L. Following saves your selection; it does not start the worker." /> : <><div className={styles.signalGrid}><div><span>Last evaluation</span><b>{time(account.last_evaluation)}</b></div><div><span>Worker result</span><b>{account.status.replaceAll('_', ' ')}</b></div><div><span>Alpha / Alpha2</span><b>{account.alpha?.toFixed(4) ?? '—'} / {account.alpha2?.toFixed(4) ?? '—'}</b><small>Signal time {time(account.signal_at)}</small></div></div><Positions key={selected} account={account} onDownload={downloadLedger} /><p className={styles.caption}>Feed updated {time(account.updated_at)}. A stale mark is not a current market price.</p></>}</div>)}
    {tab === 'trades' && <div className={styles.monthTable}><h3>Paper positions</h3>{account ? <Positions key={selected} account={account} onDownload={downloadLedger} /> : <Empty title="No paper positions yet" text="Positions appear here when the worker records them." />}</div>}
    {tab === 'rules' && <div className={styles.rules}><div><Layers size={23} /><h3>Strategy rules</h3><p>{strategy.description}</p><p>{strategy.category}</p><dl>{strategy.rules.map(rule => <div key={rule.label}><dt>{rule.label}</dt><dd>{rule.description}</dd></div>)}</dl><p className={styles.caption}>These records describe the versioned Python implementation. Editing catalogue text does not change the running engine.</p></div></div>}
    <footer className={styles.disclaimer}><ShieldCheck size={17} /><p>{strategy.limitations} Paper results are a shared model account, not your brokerage account. Following does not customize capital or execute orders.</p></footer>
  </section>;
}

function monthLabel(value: string) { return new Date(`${value}-01T00:00:00Z`).toLocaleDateString('en-IN', { month: 'short', year: '2-digit', timeZone: 'UTC' }); }
function Empty({ title, text }: { title: string; text: string }) { return <div className={styles.empty}><Radio size={28} /><h3>{title}</h3><p>{text}</p></div>; }
function Positions({ account, onDownload }: { account: Paper; onDownload: () => void }) {
  const [filter, setFilter] = useState<'all' | 'profit' | 'loss'>('all');
  const closed = account.closed_positions || [];
  const profits = closed.filter(trade => trade.pnl != null && trade.pnl > 0);
  const losses = closed.filter(trade => trade.pnl != null && trade.pnl < 0);
  const visible = filter === 'profit' ? profits : filter === 'loss' ? losses : closed;
  const total = account.realized_pnl != null && account.unrealized_pnl != null ? account.realized_pnl + account.unrealized_pnl : null;
  return <div className={styles.positions}>
    <div className={styles.positionSummary}><strong>Paper positions</strong><span className={styles.muted}>P&L: <b className={pnlClass(total)}>{money(total)}</b></span><span className={styles.muted}>Open: <b>{account.open_position ? 1 : 0}</b></span></div>
    <div className={styles.positionHeading}><h3>Open</h3><span className={styles.muted}>{account.valuation_ts ? 'Marked ' + time(account.valuation_ts) : 'Awaiting quotes'}</span></div>
    {account.open_position ? <PositionTable trades={[account.open_position]} open openPnl={account.unrealized_pnl} /> : <div className={styles.positionEmpty}>No open paper positions at the moment.</div>}
    <div className={styles.positionHeading}><h3>Closed</h3><div className={styles.positionFilters} role="group" aria-label="Filter closed positions">{([['all', 'Closed', closed.length], ['profit', 'In Profit', profits.length], ['loss', 'In Loss', losses.length]] as const).map(([value, label, count]) => <button key={value} aria-pressed={filter === value} onClick={() => setFilter(value)} className={filter === value ? styles.selectedFilter : ''}>{label}<span>{count}</span></button>)}</div></div>
    {visible.length ? <PositionTable trades={visible} /> : <div className={styles.positionEmpty}>{filter === 'all' ? 'No closed paper positions yet.' : filter === 'profit' ? 'No closed positions in profit.' : 'No closed positions in loss.'}</div>}
    <div className={styles.positionFooter}><button className={styles.outlineButton} onClick={onDownload} disabled={!closed.length}>Download as CSV</button><span>Realized P&L: <b className={pnlClass(account.realized_pnl)}>{money(account.realized_pnl)}</b></span></div>
    <p className={styles.caption}>Prices and P&L are for the combined spread. Latest {closed.length} closed trades (maximum {account.ledger_limit}); totals cover the complete paper ledger.</p>
  </div>;
}
function PositionTable({ trades, open = false, openPnl }: { trades: Trade[]; open?: boolean; openPnl?: number | null }) {
  return <div className={styles.positionTable}><div className={styles.tableScroll}><table><thead><tr><th>Name</th><th>Product</th><th>Qty</th><th>Entry credit</th><th>Stop / Target</th><th>{open ? 'Exit due · IST' : 'Exit · IST'}</th><th>P&L</th></tr></thead><tbody>{trades.map(trade => <tr key={trade.signal_id}><td><b>Sell {trade.sell_strike} / Buy {trade.buy_strike} {trade.option_type}</b><small>Expiry {trade.expiry} · Entry {time(trade.entry_ts)}</small></td><td><span className={styles.productBadge}>Paper spread</span></td><td>{trade.units}<small>{trade.lots} lots</small></td><td>{(trade.sell_price - trade.buy_price).toFixed(2)}</td><td>{trade.stop_loss.toFixed(2)} / {trade.target == null ? 'Disabled' : trade.target.toFixed(2)}</td><td>{time(open ? trade.exit_due : trade.exit_ts)}{!open && <small>{trade.exit_reason?.replaceAll('_', ' ') || '—'}</small>}</td><td className={pnlClass(open ? openPnl : trade.pnl)}>{money(open ? openPnl : trade.pnl)}</td></tr>)}</tbody></table></div></div>;
}
function MonthlyChart({ months }: { months: { month: string; pnl: number }[] }) {
  const width = 740, height = 235, padding = 36, top = 15, bottom = 205;
  const max = Math.max(1, ...months.map(item => item.pnl)), min = Math.min(0, ...months.map(item => item.pnl));
  const y = (value: number) => top + (max - value) / (max - min || 1) * (bottom - top);
  const step = (width - padding * 2) / months.length;
  return <svg className={styles.chartSvg} viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Monthly gross realized profit and loss; exact values are available in the table below.">{[min, 0, max].filter((value, index, values) => values.indexOf(value) === index).map(value => <g key={value}><line x1={padding} x2={width - 10} y1={y(value)} y2={y(value)} stroke="currentColor" opacity="0.12" /><text x={padding} y={y(value) - 5} fontSize="9" fill="currentColor" opacity="0.55">{(value / 1000).toFixed(0)}k</text></g>)}{months.map((item, index) => <g key={item.month}><title>{monthLabel(item.month)}: {money(item.pnl)}</title><rect x={padding + index * step + 8} y={Math.min(y(0), y(item.pnl))} width={Math.max(3, step - 13)} height={Math.max(1, Math.abs(y(item.pnl) - y(0)))} rx="2" fill={item.pnl < 0 ? 'var(--negative)' : 'var(--positive)'} /><text x={padding + index * step + step / 2} y={height - 10} textAnchor="middle" fontSize="10" fill="currentColor" opacity="0.6">{monthLabel(item.month).split(' ')[0]}</text></g>)}</svg>;
}
