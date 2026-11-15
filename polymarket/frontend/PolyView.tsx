'use client';

import { AlertCircle, ArrowDownRight, ArrowUpRight, Download, FileText, Info, RefreshCw, ShieldCheck } from 'lucide-react';
import { useMemo, useState, type ReactNode } from 'react';
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import {
  ago, algoStats, cents, info, mergeLedger, pct, plural, pnlSeries, signedPct, signedUsd, sortIds, usd, when,
  type AlgoStats, type Feed, type LedgerRow,
} from './polyData';
import styles from './poly.module.css';

type Tab = 'overview' | 'open' | 'history' | 'backtests';
const TABS: [Tab, string][] = [['overview', 'Overview'], ['open', 'Open bets'], ['history', 'Bet history'], ['backtests', 'Backtest vs live']];
const tone = (v: number | null | undefined) => v == null || Math.abs(v) < 0.005 ? '' : v < 0 ? styles.red : styles.green;

function Empty({ children }: { children: ReactNode }) {
  return <div className={styles.emptyRow}><FileText size={20} strokeWidth={1.4} />{children}</div>;
}

function Stat({ label, value, sub, className }: { label: string; value: ReactNode; sub?: ReactNode; className?: string }) {
  return <div className={styles.stat}><span>{label}</span><strong className={className}>{value}</strong>{sub != null && <small>{sub}</small>}</div>;
}

function Dot({ color }: { color: string }) {
  return <i className={styles.dot} style={{ background: color }} aria-hidden="true" />;
}

export type PolyViewProps = {
  feed: Feed | null; ledger: LedgerRow[] | null; loading: boolean; error: string; now: number;
  onRefresh: () => void; onExport: () => void; exporting: boolean;
};

export default function PolyView({ feed, ledger, loading, error, now, onRefresh, onExport, exporting }: PolyViewProps) {
  const [tab, setTab] = useState<Tab>('overview');
  const [algoFilter, setAlgoFilter] = useState<string>('all');
  const ids = useMemo(() => sortIds(Object.keys(feed?.strategies ?? {})), [feed]);
  const rows = useMemo(() => mergeLedger(ledger, feed), [ledger, feed]);
  const stats = useMemo(() => feed ? ids.map(id => algoStats(id, feed.strategies[id], rows, feed.catalog[id], now)) : [], [feed, ids, rows, now]);
  const open = stats.flatMap(s => feed!.strategies[s.id].positions.map(p => ({ id: s.id, p })));
  const live = stats.length > 0 && stats.every(s => s.state !== 'offline');
  const lastUpdate = stats.map(s => s.updated).filter(Boolean).sort().at(-1);

  const filtered = (id: string) => algoFilter === 'all' || algoFilter === id;
  const filterBar = <div className={styles.pills} role="group" aria-label="Filter by algo">
    {['all', ...ids].map(id => <button key={id} className={algoFilter === id ? styles.pillActive : ''} aria-pressed={algoFilter === id} onClick={() => setAlgoFilter(id)}>
      {id !== 'all' && <Dot color={info(id).color} />}{id === 'all' ? 'All algos' : info(id).title}
    </button>)}
  </div>;

  let body: ReactNode;
  if (!feed) body = <div className={styles.card}><Empty>{loading ? 'Loading paper accounts…' : error || 'No data yet.'}</Empty></div>;
  else if (!ids.length) body = <div className={styles.card}><Empty>The paper worker has not published an account yet.</Empty></div>;
  else if (tab === 'overview') body = <Overview stats={stats} ids={ids} rows={rows} feed={feed} now={now} onOpen={id => { setAlgoFilter(id); setTab('history'); }} />;
  else if (tab === 'open') body = <>{filterBar}<OpenBets rows={open.filter(o => filtered(o.id))} /></>;
  else if (tab === 'history') body = <>{filterBar}<History rows={rows} ids={ids.filter(filtered)} /></>;
  else body = <Backtests stats={stats} feed={feed} />;

  return <section className={styles.lab}>
    <div className={styles.heading}>
      <div>
        <h1>Polymarket Algos</h1>
        <p className={styles.subtitle}>Four strategies, each trading its own $25 paper account on live Polymarket prices. No real money is used.</p>
      </div>
      <span className={styles.paperBadge}><ShieldCheck size={16} /><span><b>Paper trading only</b>No wallet, no real orders</span></span>
    </div>

    <div className={styles.tabs}>
      <nav aria-label="Polymarket sections">
        {TABS.map(([id, name]) => <button key={id} className={tab === id ? styles.tabActive : ''} aria-current={tab === id ? 'page' : undefined} onClick={() => setTab(id)}>
          {name}{id === 'open' && open.length ? <span>{open.length}</span> : null}
        </button>)}
      </nav>
      <div className={styles.tabMeta}>
        <span className={styles.feed} title={lastUpdate ? `Last update ${when(lastUpdate)}` : undefined}>
          <i className={live ? styles.feedLive : ''} />{feed ? live ? `Live · updated ${ago(lastUpdate, now)}` : `Worker offline · last update ${ago(lastUpdate, now)}` : 'Connecting…'}
        </span>
        <button className={styles.refresh} onClick={onExport} disabled={exporting} title="Every paper bet and result since the start, as a spreadsheet"><Download size={14} />{exporting ? 'Exporting…' : 'Export CSV'}</button>
        <button className={styles.refresh} onClick={onRefresh} disabled={loading}><RefreshCw size={14} className={loading ? styles.spin : ''} />Refresh</button>
      </div>
    </div>

    {error && feed && <div className={styles.notice} role="status"><AlertCircle size={16} />{error}<button onClick={onRefresh}>Retry</button></div>}
    <div className={styles.content}>{body}</div>

    <footer className={styles.disclaimer}><Info size={15} /><p>
      Every bet is simulated against the live Polymarket order book at the moment the algo decides, including Polymarket&apos;s fee. Bets are held until the market resolves, then pay $1 per share if right and $0 if wrong.
      “Worth now” values open bets at the price you could sell them for right now. Backtests use past trade prices and are usually more optimistic than live results. Times are IST.
    </p></footer>
  </section>;
}

// ------------------------------------------------------------------ overview
function Overview({ stats, ids, rows, feed, now, onOpen }: { stats: AlgoStats[]; ids: string[]; rows: LedgerRow[]; feed: Feed; now: number; onOpen: (id: string) => void }) {
  const sum = (f: (s: AlgoStats) => number) => stats.reduce((t, s) => t + f(s), 0);
  const start = sum(s => s.start), value = sum(s => s.value), settled = sum(s => s.settled), wins = sum(s => s.wins);
  const openCount = sum(s => s.openCount);
  return <>
    <div className={`${styles.card} ${styles.summary}`}>
      <Stat label="Started with" value={usd(start)} sub={`${plural(stats.length, 'algo')} × ${usd(start / Math.max(stats.length, 1), 0)}`} />
      <Stat label="Worth now" value={usd(value)} sub="cash + open bets at today's prices" />
      <Stat label="Profit / loss" value={signedUsd(value - start)} className={tone(value - start)} sub={<span className={tone(value - start)}>{signedPct((value - start) / start)} since start</span>} />
      <Stat label="From finished bets" value={signedUsd(sum(s => s.realized))} className={tone(sum(s => s.realized))} sub={`${plural(settled, 'bet')} · ${wins} won · ${settled - wins} lost`} />
      <Stat label="Open bets" value={usd(sum(s => s.inBets))} sub={<>{plural(openCount, 'bet')} · <span className={tone(sum(s => s.unrealized))}>{signedUsd(sum(s => s.unrealized))} if sold now</span></>} />
      <Stat label="Cash free" value={usd(sum(s => s.cash))} sub="available for new bets" />
    </div>

    <PnlChart ids={ids} rows={rows} feed={feed} now={now} />

    <div className={styles.sectionHead}><h2>The algos</h2><span className={styles.muted}>Click one to see its bets.</span></div>
    <div className={styles.algoGrid}>{stats.map(s => <AlgoCard key={s.id} s={s} feed={feed} onOpen={() => onOpen(s.id)} />)}</div>
  </>;
}

function PnlChart({ ids, rows, feed, now }: { ids: string[]; rows: LedgerRow[]; feed: Feed; now: number }) {
  const [mode, setMode] = useState<'algos' | 'total'>('algos');
  const data = useMemo(() => pnlSeries(ids, rows, feed, now), [ids, rows, feed, now]);
  const fmtTime = (t: number) => new Date(t).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
  return <div className={styles.card}>
    <div className={styles.cardHead}>
      <div><h2>Profit / loss over time</h2><p className={styles.caption}>Each step is a bet that finished. The last point also counts open bets at today&apos;s prices.</p></div>
      <div className={styles.pills} role="group" aria-label="Chart lines">
        <button className={mode === 'algos' ? styles.pillActive : ''} aria-pressed={mode === 'algos'} onClick={() => setMode('algos')}>By algo</button>
        <button className={mode === 'total' ? styles.pillActive : ''} aria-pressed={mode === 'total'} onClick={() => setMode('total')}>Total</button>
      </div>
    </div>
    {mode === 'algos' && <div className={styles.legend}>{ids.map(id => <span key={id}><Dot color={info(id).color} />{info(id).title}</span>)}</div>}
    <div className={styles.chartBox}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 4 }}>
          <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="t" type="number" scale="time" domain={['dataMin', 'dataMax']} tickFormatter={fmtTime} stroke="var(--muted-foreground)" fontSize={11} tickLine={false} minTickGap={40} />
          <YAxis tickFormatter={v => `${v < 0 ? '−' : ''}$${Math.abs(v).toFixed(0)}`} stroke="var(--muted-foreground)" fontSize={11} tickLine={false} axisLine={false} width={44} />
          <ReferenceLine y={0} stroke="var(--muted-foreground)" strokeOpacity={0.5} />
          <Tooltip
            labelFormatter={v => fmtTime(Number(v))}
            formatter={(v, name) => [signedUsd(Number(v)), name === 'total' ? 'All algos' : info(String(name)).title]}
            contentStyle={{ background: 'var(--card)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12, color: 'var(--foreground)' }}
            itemSorter={item => -Number(item.value)}
          />
          {mode === 'total'
            ? <Line dataKey="total" type="stepAfter" stroke="var(--primary)" strokeWidth={2} dot={false} isAnimationActive={false} />
            : ids.map(id => <Line key={id} dataKey={id} type="stepAfter" stroke={info(id).color} strokeWidth={2} dot={false} isAnimationActive={false} />)}
        </LineChart>
      </ResponsiveContainer>
    </div>
  </div>;
}

function AlgoCard({ s, feed, onOpen }: { s: AlgoStats; feed: Feed; onOpen: () => void }) {
  const a = feed.strategies[s.id], i = info(s.id);
  const stateText = s.state === 'offline' ? `Offline · ${ago(s.updated)}` : s.state === 'holding' ? `Holding ${plural(s.openCount, 'bet')}` : s.lowCash ? 'Out of cash' : 'Watching markets';
  return <button className={styles.algoCard} onClick={onOpen}>
    <div className={styles.algoTop}>
      <span className={styles.algoName}><Dot color={i.color} /><b>{i.title}</b><small>{i.short}</small></span>
      <span className={`${styles.state} ${styles[`state_${s.state}`]}`}><i />{stateText}</span>
    </div>
    <div className={styles.algoPnl}>
      <strong className={tone(s.pnl)}>{s.pnl >= 0 ? <ArrowUpRight size={18} /> : <ArrowDownRight size={18} />}{signedUsd(s.pnl)}</strong>
      <span><b className={tone(s.pnl)}>{signedPct(s.pnlPct)}</b> · worth {usd(s.value)} of {usd(s.start, 0)}</span>
    </div>
    <p className={styles.how}>{i.how(a.params ?? {})}</p>
    <dl className={styles.facts}>
      <div><dt>In open bets</dt><dd>{usd(s.inBets)} <small>{s.openCount ? `· ${plural(s.openCount, 'bet')}` : ''}</small></dd></div>
      <div><dt>Cash free</dt><dd className={s.lowCash ? styles.red : ''}>{usd(s.cash)}</dd></div>
      <div><dt>Bets placed</dt><dd>{s.bets} <small>· {usd(s.staked, 0)} staked in total</small></dd></div>
      <div><dt>Finished bets</dt><dd>{s.settled ? <>{s.wins} won · {s.losses} lost <small>({pct(s.winRate, 0)})</small></> : 'none yet'}</dd></div>
      <div><dt>Average win / loss</dt><dd><span className={styles.green}>{signedUsd(s.avgWin)}</span> / <span className={styles.red}>{signedUsd(s.avgLoss)}</span></dd></div>
      <div><dt>Return per bet</dt><dd className={tone(s.liveRoi)}>{signedPct(s.liveRoi)} <small className={styles.muted}>· backtest {signedPct(s.backtest?.roi_per_bet)}</small></dd></div>
    </dl>
    {s.lowCash && <p className={`${styles.verdict} ${styles.verdict_warn}`}>Out of cash: only {usd(s.cash)} free, so it cannot place new bets{s.openCount ? ` until its ${plural(s.openCount, 'open bet')} finish` : ''}.</p>}
    <p className={`${styles.verdict} ${styles[`verdict_${s.verdict.tone}`]}`}>{s.verdict.text}</p>
    {(a.previous ?? []).map(p => <p key={p.version} className={styles.caption}>Rules changed {when(p.ended_at)}. Version {p.version} ended at {usd(p.equity)} of {usd(p.start_cash, 0)} ({signedUsd((p.equity ?? 0) - (p.start_cash ?? 0))}) after {plural(p.n_settled ?? 0, 'bet')}, {p.n_wins ?? 0} won. This account restarted with the new rules.</p>)}
    {a.last_error && <p className={styles.caption}>Last worker issue: {a.last_error}</p>}
  </button>;
}

// ------------------------------------------------------------------ open bets
function OpenBets({ rows }: { rows: { id: string; p: Feed['strategies'][string]['positions'][number] }[] }) {
  const total = rows.reduce((t, r) => t + (r.p.mark == null ? 0 : r.p.mark * r.p.shares - r.p.cost), 0);
  return <div className={styles.tableCard}><div className={styles.tableScroll}><table className={styles.table}>
    <thead><tr><th>Market</th><th>Algo</th><th>Bet on</th><th className={styles.num}>Bought at</th><th className={styles.num}>Price now</th><th className={styles.num}>Stake</th><th className={styles.num}>Worth now</th><th className={styles.num}>Profit / loss</th></tr></thead>
    <tbody>{rows.map(({ id, p }) => {
      const worth = p.mark == null ? null : p.mark * p.shares, pnl = worth == null ? null : worth - p.cost;
      return <tr key={p.cid + p.outcome}>
        <td className={styles.wrap}><b>{p.question}</b><small>Opened {when(p.opened)}{p.end ? ` · ends ${when(p.end)}` : ''}</small></td>
        <td><span className={styles.algoTag}><Dot color={info(id).color} />{info(id).title}</span></td>
        <td><span className={styles.sideTag}>{p.outcome_name ?? (p.outcome ? 'No' : 'Yes')}</span></td>
        <td className={styles.num}>{cents(p.entry_price)}</td>
        <td className={styles.num}>{cents(p.mark)}</td>
        <td className={styles.num}>{usd(p.cost)}<small>{p.shares.toFixed(2)} shares</small></td>
        <td className={styles.num}>{usd(worth)}<small>{usd(p.shares, 2)} if it wins</small></td>
        <td className={`${styles.num} ${tone(pnl)}`}>{signedUsd(pnl)}</td>
      </tr>;
    })}</tbody>
    {rows.length > 0 && <tfoot><tr><td colSpan={7}>If all open bets were sold now</td><td className={`${styles.num} ${tone(total)}`}>{signedUsd(total)}</td></tr></tfoot>}
  </table></div>{!rows.length && <Empty>No open bets right now. They appear here as soon as an algo buys.</Empty>}</div>;
}

// ------------------------------------------------------------------ history
function History({ rows, ids }: { rows: LedgerRow[]; ids: string[] }) {
  const buys = useMemo(() => {
    const m = new Map<string, LedgerRow>();
    for (const r of rows) if (r.kind === 'fill') m.set(`${r.strategy}:${r.cid}:${r.outcome}`, r);
    return m;
  }, [rows]);
  const done = rows.filter(r => r.kind === 'settled' && ids.includes(r.strategy ?? '')).reverse();
  const [limit, setLimit] = useState(100);
  const total = done.reduce((t, r) => t + (r.pnl ?? 0), 0), won = done.filter(r => (r.pnl ?? 0) > 0).length;
  return <>
    <p className={styles.caption}>{plural(done.length, 'finished bet')} · {won} won · {done.length - won} lost · total <b className={tone(total)}>{signedUsd(total)}</b></p>
    <div className={styles.tableCard}><div className={styles.tableScroll}><table className={styles.table}>
      <thead><tr><th>Finished</th><th>Market</th><th>Algo</th><th>Bet on</th><th className={styles.num}>Bought at</th><th className={styles.num}>Stake</th><th className={styles.num}>Paid out</th><th className={styles.num}>Profit / loss</th><th>Result</th></tr></thead>
      <tbody>{done.slice(0, limit).map(r => {
        const buy = buys.get(`${r.strategy}:${r.cid}:${r.outcome}`), win = (r.pnl ?? 0) > 0;
        return <tr key={`${r.strategy}${r.cid}${r.outcome}${r.t}`}>
          <td className={styles.muted}>{when(r.ts)}</td>
          <td className={styles.wrap}><b>{r.question}</b>{buy && <small>Bought {when(buy.ts)}</small>}</td>
          <td><span className={styles.algoTag}><Dot color={info(r.strategy ?? '').color} />{info(r.strategy ?? '').title}</span></td>
          <td><span className={styles.sideTag}>{r.outcome_name ?? '—'}</span></td>
          <td className={styles.num}>{cents(buy?.price)}</td>
          <td className={styles.num}>{usd(r.cost)}</td>
          <td className={styles.num}>{usd(r.payout)}</td>
          <td className={`${styles.num} ${tone(r.pnl)}`}>{signedUsd(r.pnl)}</td>
          <td><span className={win ? styles.wonTag : styles.lostTag}>{win ? 'Won' : 'Lost'}</span></td>
        </tr>;
      })}</tbody>
    </table></div>
      {!done.length && <Empty>No bets have finished yet. Up/Down bets finish within minutes, sports within hours, crypto price bets within days.</Empty>}
      {done.length > limit && <button className={styles.more} onClick={() => setLimit(l => l + 200)}>Show {Math.min(200, done.length - limit)} more</button>}
    </div>
  </>;
}

// ------------------------------------------------------------------ backtests
function Backtests({ stats, feed }: { stats: AlgoStats[]; feed: Feed }) {
  return <>
    <p className={styles.caption}>The backtest was tuned on older data and then checked on a later period it never saw (&ldquo;held-out&rdquo;). Live results should land near the held-out numbers; a big gap after 30+ bets means the edge may not be real.</p>
    <div className={styles.tableCard}><div className={styles.tableScroll}><table className={styles.table}>
      <thead>
        <tr><th rowSpan={2}>Algo</th><th colSpan={4} className={styles.groupHead}>Backtest (held-out period)</th><th colSpan={4} className={styles.groupHead}>Live paper trading</th></tr>
        <tr><th className={styles.num}>Bets</th><th className={styles.num}>Won</th><th className={styles.num}>Avg price</th><th className={styles.num}>Return / bet</th>
          <th className={styles.num}>Bets</th><th className={styles.num}>Won</th><th className={styles.num}>Avg price</th><th className={styles.num}>Return / bet</th></tr>
      </thead>
      <tbody>{stats.map(s => <tr key={s.id}>
        <td><span className={styles.algoTag}><Dot color={info(s.id).color} />{info(s.id).title}</span></td>
        <td className={styles.num}>{s.backtest?.n ?? '—'}</td>
        <td className={styles.num}>{pct(s.backtest?.win_rate, 0)}</td>
        <td className={styles.num}>{cents(s.backtest?.avg_price)}</td>
        <td className={`${styles.num} ${tone(s.backtest?.roi_per_bet)}`}>{signedPct(s.backtest?.roi_per_bet)}</td>
        <td className={styles.num}>{s.settled}</td>
        <td className={styles.num}>{pct(s.winRate, 0)}</td>
        <td className={styles.num}>{cents(s.avgEntry)}</td>
        <td className={`${styles.num} ${tone(s.liveRoi)}`}>{signedPct(s.liveRoi)}</td>
      </tr>)}</tbody>
    </table></div></div>

    <div className={styles.algoGrid}>{stats.map(s => {
      const c = feed.catalog[s.id];
      return <div key={s.id} className={styles.card}>
        <div className={styles.cardHead}><h2><Dot color={info(s.id).color} />{info(s.id).title}</h2></div>
        <p className={`${styles.verdict} ${styles[`verdict_${s.verdict.tone}`]}`}>{s.verdict.text}</p>
        {c ? <div className={styles.tableScroll}><table className={`${styles.table} ${styles.compact}`}>
          <thead><tr><th>Backtest period</th><th className={styles.num}>Bets</th><th className={styles.num}>Won</th><th className={styles.num}>Return / bet</th><th className={styles.num}>Confidence</th></tr></thead>
          <tbody>{([[c.train_label ?? 'Tuning period', c.train], [c.test_label ?? 'Held-out period', c.test]] as const).map(([name, row]) => <tr key={name}>
            <td>{name}</td><td className={styles.num}>{row?.n ?? '—'}</td><td className={styles.num}>{pct(row?.win_rate, 0)}</td>
            <td className={`${styles.num} ${tone(row?.roi_per_bet)}`}>{signedPct(row?.roi_per_bet)}</td>
            <td className={styles.num}>{row?.t_stat == null ? '—' : Math.abs(row.t_stat) >= 3 ? 'strong' : Math.abs(row.t_stat) >= 2 ? 'moderate' : 'weak'}</td>
          </tr>)}</tbody>
        </table></div> : <p className={styles.caption}>No backtest published.</p>}
        {c?.note && <p className={styles.caption}>{c.note}</p>}
      </div>;
    })}</div>
  </>;
}
