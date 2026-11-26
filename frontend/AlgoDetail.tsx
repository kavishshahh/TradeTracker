'use client';

import { Check, ChevronLeft, ChevronRight, Plus } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { algoState, blurb, dailyPnl, dayBefore, istParts, money, monthLabel, monthsBefore, matchingDays, pastTrades, percent, periodReturn, pnlBetween, periodShort, ruleText, signedPercent, stateLabel, time, type BacktestLedger, type Day, type EquityDays, type Month, type Paper, type PastTrade, type Period, type Strategy, type Trade } from './algoData';
import { AlgoIcon, BacktestTag, EmptyRow, Pills, PositionTable, Return, Tabs, tone } from './algoUi';
import { AccessCard, openAccess, type LabAccess } from './AlgoAccessCard';
import EquityChart, { type EquityPoint } from './EquityChart';
import styles from './algos.module.css';

type Tab = 'performance' | 'trades' | 'monthly' | 'rules';
type Preset = '1m' | '3m' | '6m' | '1y' | '2y' | '3y' | 'all';
type Range = Preset | 'custom';
/** Chart ranges in calendar months back from the last day. 2Y and 3Y appear only when the backtest is longer than that. */
const RANGES: { id: Preset; label: string; months: number }[] = [{ id: '1m', label: '1M', months: 1 }, { id: '3m', label: '3M', months: 3 }, { id: '6m', label: '6M', months: 6 }, { id: '1y', label: '1Y', months: 12 }, { id: '2y', label: '2Y', months: 24 }, { id: '3y', label: '3Y', months: 36 }, { id: 'all', label: 'All', months: Infinity }];
const rowsReturn = (rows: Month[], capital: number) => rows.reduce((total, row) => total + row.pnl, 0) / capital * 100;

type LoadBacktest = (id: string) => Promise<BacktestLedger | null>;
type LoadEquity = (id: string) => Promise<EquityDays | null>;
type Props = { strategy: Strategy; account: Paper | null | undefined; paperLoaded: boolean; following: boolean; saving: boolean; period: Period; access?: LabAccess; onFollow: (enabled: boolean) => void; onDownload: () => void; loadBacktest: LoadBacktest; loadEquity?: LoadEquity };

export default function AlgoDetail({ strategy, account, paperLoaded, following, saving, period, access = openAccess, onFollow, onDownload, loadBacktest, loadEquity }: Props) {
  const [tab, setTab] = useState<Tab>('performance');
  // Day-by-day P&L for the chart, from the backtest ledger. Until it arrives, or if it is missing, the chart is monthly.
  const [equity, setEquity] = useState<EquityDays | null>(null);
  useEffect(() => {
    let live = true;
    setEquity(null);
    loadEquity?.(strategy.id).then(body => { if (live) setEquity(body); }).catch(() => {});
    return () => { live = false; };
  }, [strategy.id, loadEquity]);
  const days = matchingDays(strategy, equity);
  const state = algoState(account);
  return <>
    <div className={`${styles.card} ${styles.detailHead}`}>
      <AlgoIcon version={strategy.version} size="lg" />
      <div className={styles.detailTitle}>
        <h2>{strategy.name}</h2>
        <p>{strategy.underlying}<i />{strategy.category}<i /><span className={`${styles.state} ${styles[`state_${state.replace('-', '_')}`]}`}><i />{paperLoaded ? stateLabel[state] : 'Loading'}</span></p>
      </div>
      <div className={styles.detailStat}><span>Model capital</span><b>{money(account?.capital ?? strategy.capital)}</b></div>
      <div className={styles.detailStat}><span>{periodShort[period]} returns <BacktestTag /></span><b><Return value={periodReturn(strategy, period, days)} /></b></div>
      <button className={following ? styles.followingButton : styles.followButton} onClick={() => onFollow(!following)} disabled={saving || !paperLoaded} title={following ? 'Click to stop following' : 'Follow this algo’s paper trades'}>{following ? <Check size={15} /> : <Plus size={15} />}{saving ? 'Saving…' : following ? 'Following' : 'Follow'}</button>
    </div>
    <Tabs label="Algo sections" value={tab} onChange={setTab} items={[{ id: 'performance', label: 'Algo performance' }, { id: 'trades', label: 'Past trades' }, { id: 'monthly', label: 'Monthly returns' }, { id: 'rules', label: 'About algo' }]} />
    {tab === 'performance' && <Performance strategy={strategy} account={account} ledgerDays={days} />}
    {tab === 'trades' && (access.allowed ? <PastTrades strategy={strategy} account={account} onDownload={onDownload} loadBacktest={loadBacktest} /> : <AccessCard access={access} what="Past trades" />)}
    {tab === 'monthly' && <Monthly strategy={strategy} />}
    {tab === 'rules' && <Rules strategy={strategy} owner={access.owner} />}
  </>;
}

const shortDate = (value: string, withDay = false) => new Date(`${value}T00:00:00Z`).toLocaleDateString('en-IN', { day: withDay ? 'numeric' : undefined, month: 'short', year: 'numeric', timeZone: 'UTC' });

function Performance({ strategy, account, ledgerDays }: { strategy: Strategy; account: Paper | null | undefined; ledgerDays: Day[] | null }) {
  const [range, setRange] = useState<Range>('all');
  const [span, setSpan] = useState<{ from: string; to: string } | null>(null);
  const days = useMemo(() => dailyPnl(strategy, ledgerDays), [strategy, ledgerDays]);
  const detailed = !!ledgerDays;                                      // else one figure per month
  const rows = strategy.monthly;
  const end = strategy.period_end, origin = dayBefore(strategy.period_start);
  const presets = RANGES.filter(item => item.months <= 12 || !Number.isFinite(item.months) || monthsBefore(end, item.months) > strategy.period_start);
  const lastYear = { from: rows[Math.max(0, rows.length - 12)].month, to: rows[rows.length - 1].month };
  const wanted = span || lastYear;                                    // Custom opens on the last 12 months
  const to = rows.reduce((found, row, index) => row.month <= wanted.to ? index : found, 0);
  const from = Math.min(to, Math.max(0, rows.findIndex(row => row.month >= wanted.from)));
  const shown = rows.slice(from, to + 1);
  /** A range as (the day its equity is reset to the model capital, its last day). */
  const bounds = (id: Range): [string, string] => {
    if (id === 'custom') {
      const [year, month] = rows[to].month.split('-').map(Number);
      const monthEnd = new Date(Date.UTC(year, month, 0)).toISOString().slice(0, 10);
      const start = dayBefore(`${rows[from].month}-01`);
      return [start > origin ? start : origin, monthEnd < end ? monthEnd : end];
    }
    const months = RANGES.find(item => item.id === id)?.months ?? Infinity;
    const start = Number.isFinite(months) ? monthsBefore(end, months) : origin;
    return [start > origin ? start : origin, end];
  };
  const rangeReturn = (id: Range) => {
    if (!detailed && id !== 'custom') { const count = RANGES.find(item => item.id === id)!.months; return id === 'all' || count <= 12 ? periodReturn(strategy, id as Period | 'all') : rowsReturn(rows.slice(-count), strategy.capital); }
    const [after, until] = bounds(id);
    return pnlBetween(days, after, until) / strategy.capital * 100;
  };
  const [after, until] = bounds(range);
  // Every weekday from the reset day to the end of the range, starting again from the model capital.
  const points = useMemo(() => {
    const closed = new Map(days.filter(item => item.day > after && item.day <= until).map(item => [item.day, item.pnl]));
    const curve: EquityPoint[] = [{ day: after, value: strategy.capital }];
    let equity = strategy.capital;
    for (let stamp = Date.parse(`${after}T00:00:00Z`) + 86_400_000; stamp <= Date.parse(`${until}T00:00:00Z`); stamp += 86_400_000) {
      const day = new Date(stamp).toISOString().slice(0, 10), pnl = closed.get(day), weekday = new Date(stamp).getUTCDay();
      if (pnl == null && (weekday === 0 || weekday === 6) && day !== until) continue;
      if (pnl != null) equity += pnl;
      curve.push(pnl == null ? { day, value: equity } : { day, value: equity, pnl });
    }
    return curve;
  }, [days, after, until, strategy.capital]);
  const customReturn = rangeReturn('custom');
  const capital = account?.capital ?? strategy.capital;
  const up = strategy.monthly.filter(month => month.pnl > 0);
  return <>
    <div className={styles.card}>
      <div className={styles.chartHead}>
        <div><h3>Backtest equity</h3><p className={styles.caption}>Starts at {money(strategy.capital)} model capital · {shortDate(after, true)} – {shortDate(until, true)}{detailed ? ' · by trading day' : ' · by month'}</p></div>
        <div className={styles.rangePills} role="group" aria-label="Chart range">
          {presets.map(item => { const value = rangeReturn(item.id); return <button key={item.id} className={range === item.id ? styles.rangeActive : ''} aria-pressed={range === item.id} onClick={() => setRange(item.id)}>{item.label}<span className={tone(value)}>{signedPercent(value)}</span></button>; })}
          <button className={range === 'custom' ? styles.rangeActive : ''} aria-pressed={range === 'custom'} onClick={() => setRange('custom')}>Custom{range === 'custom' ? <span className={tone(customReturn)}>{signedPercent(customReturn)}</span> : <span>Pick months</span>}</button>
        </div>
      </div>
      {range === 'custom' && <div className={styles.rangeCustom}>
        <label>From<select className={styles.select} value={rows[from].month} onChange={event => setSpan({ from: event.target.value, to: rows[to].month })}>{rows.slice(0, to + 1).map(row => <option key={row.month} value={row.month}>{monthLabel(row.month, 'long')}</option>)}</select></label>
        <label>To<select className={styles.select} value={rows[to].month} onChange={event => setSpan({ from: rows[from].month, to: event.target.value })}>{rows.slice(from).map(row => <option key={row.month} value={row.month}>{monthLabel(row.month, 'long')}</option>)}</select></label>
        <span>{shown.length} {shown.length === 1 ? 'month' : 'months'} · {shown.reduce((total, row) => total + row.closed_trades, 0)} trades · P&L <b className={tone(customReturn)}>{money(shown.reduce((total, row) => total + row.pnl, 0))}</b></span>
      </div>}
      <EquityChart points={points} base={strategy.capital} />
      <p className={styles.caption}>Realised P&L on the day each trade closed, on fixed model capital. Drag to pan, drag the date axis to zoom, double-click it to reset.</p>
    </div>
    <div className={styles.twoCol}>
      <div className={styles.card}>
        <h3 className={styles.cardTitle}>Backtest</h3>
        <dl className={styles.stats}>
          <div><dt>Total P&L</dt><dd className={tone(strategy.metrics.total_pnl)}>{money(strategy.metrics.total_pnl)}</dd></div>
          <div><dt>CAGR</dt><dd className={tone(strategy.metrics.cagr_pct)}>{percent(strategy.metrics.cagr_pct)}</dd></div>
          <div><dt>Max drawdown</dt><dd className={strategy.metrics.max_drawdown_pct ? styles.red : ''}>{percent(-Math.abs(strategy.metrics.max_drawdown_pct))}</dd></div>
          <div><dt>Win rate</dt><dd>{percent(strategy.metrics.win_rate_pct)}</dd></div>
          <div><dt>Trades</dt><dd>{strategy.metrics.trade_count}</dd></div>
          <div><dt>Profitable months</dt><dd>{up.length} of {strategy.monthly.length}</dd></div>
        </dl>
        <p className={styles.caption}>Gross of costs; intratrade drawdowns are excluded.{strategy.exit_policy ? ` Exit: ${strategy.exit_policy}.` : ''}</p>
      </div>
      <div className={styles.card}>
        <h3 className={styles.cardTitle}>Paper account</h3>
        {account ? <dl className={styles.stats}>
          <div><dt>Realized P&L</dt><dd className={tone(account.realized_pnl)}>{money(account.realized_pnl)} <small>{percent(account.realized_pnl == null ? null : account.realized_pnl / capital * 100)}</small></dd></div>
          <div><dt>Unrealized P&L</dt><dd className={tone(account.open_position ? account.unrealized_pnl : 0)}>{account.open_position ? money(account.unrealized_pnl) : '—'}</dd></div>
          <div><dt>Closed trades</dt><dd>{account.closed_trades}</dd></div>
          <div><dt>Win rate</dt><dd>{percent(account.win_rate_pct)}</dd></div>
          <div><dt>Last evaluation</dt><dd>{time(account.last_evaluation)}</dd></div>
          <div><dt>Worker result</dt><dd className={styles.capitalize}>{account.status.replaceAll('_', ' ')}</dd></div>
        </dl> : <EmptyRow>The paper worker has not published this algo yet.</EmptyRow>}
        {account && <p className={styles.caption}>Feed updated {time(account.updated_at)}{account.open_position ? ` · marked ${time(account.valuation_ts)}` : ''}.</p>}
      </div>
    </div>
  </>;
}

function PastTrades({ strategy, account, onDownload, loadBacktest }: { strategy: Strategy; account: Paper | null | undefined; onDownload: () => void; loadBacktest: LoadBacktest }) {
  const [ledger, setLedger] = useState<BacktestLedger | null>(null);
  const [ledgerState, setLedgerState] = useState<'loading' | 'ready' | 'missing' | 'error'>('loading');
  useEffect(() => {
    let live = true;
    loadBacktest(strategy.id).then(body => { if (live) { setLedger(body); setLedgerState(body ? 'ready' : 'missing'); } }).catch(() => { if (live) setLedgerState('error'); });
    return () => { live = false; };
  }, [strategy.id, loadBacktest]);
  const trades = useMemo(() => pastTrades(ledger, account), [ledger, account]);
  const capital = account?.capital ?? strategy.capital;
  const note = ledgerState === 'missing' ? 'No backtest ledger has been uploaded for this algo, so only forward paper trades appear.'
    : ledgerState === 'error' ? 'Backtest trades could not be loaded (the API may not have the /algos/backtest route deployed yet); only forward paper trades appear.'
    : ledger && ledger.trade_count !== strategy.metrics.trade_count ? `The exported backtest ledger has ${ledger.trade_count} trades but the catalogue lists ${strategy.metrics.trade_count}; re-run backend/export_backtest_trades.py after updating the backtest.`
    : null;
  return <>
    {ledgerState === 'loading' ? <div className={styles.card}><EmptyRow>Loading past trades…</EmptyRow></div> : <TradeCalendar trades={trades} capital={capital} note={note} />}
    <ForwardPositions account={account} onDownload={onDownload} />
  </>;
}

function monthRange(first: string, last: string) {
  const months: string[] = [];
  let [year, month] = first.split('-').map(Number);
  const [endYear, endMonth] = last.split('-').map(Number);
  while (year < endYear || (year === endYear && month <= endMonth)) {
    months.push(`${year}-${String(month).padStart(2, '0')}`);
    month += 1; if (month > 12) { month = 1; year += 1; }
  }
  return months;
}

const price = (value: number | null) => value == null ? '—' : value.toFixed(2);
/** The two options of a spread as separate positions: the one sold, then the one bought as its hedge. */
function tradeLegs(trade: PastTrade) {
  const leg = (sold: boolean, strike: number, entry: number | null, exit: number | null) => ({ sold, name: `NIFTY ${trade.expiry} ${strike} ${trade.type}`, entry, exit,
    pnl: entry == null || exit == null ? null : (sold ? entry - exit : exit - entry) * trade.units });
  const bought = leg(false, trade.buy, trade.buyEntry, trade.buyExit);
  return trade.single ? [bought] : [leg(true, trade.sell, trade.sellEntry, trade.sellExit), bought];
}
const dayLabel = (day: string) => new Date(`${day}T00:00:00Z`).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', timeZone: 'UTC' });

function TradeCalendar({ trades, capital, note }: { trades: PastTrade[]; capital: number; note: string | null }) {
  const current = istParts().month;
  // Every month from the first trade to now, so quiet stretches show up as empty months.
  const months = useMemo(() => monthRange(trades[0]?.day.slice(0, 7) || current, current), [trades, current]);
  const lastTraded = trades.at(-1)?.day.slice(0, 7) || current;
  const [month, setMonth] = useState(lastTraded);
  const [day, setDay] = useState<string | null>(null);
  const index = Math.max(0, months.indexOf(month));
  const inMonth = trades.filter(trade => trade.day.startsWith(month));
  const byDay = inMonth.reduce<Record<string, { backtest: number; paper: number; b: number; p: number }>>((total, trade) => {
    const cell = total[trade.day] ??= { backtest: 0, paper: 0, b: 0, p: 0 };
    if (trade.source === 'backtest') { cell.backtest += trade.pnl ?? 0; cell.b += 1; } else { cell.paper += trade.pnl ?? 0; cell.p += 1; }
    return total;
  }, {});
  const sum = (source: PastTrade['source']) => inMonth.filter(trade => trade.source === source).reduce((total, trade) => total + (trade.pnl ?? 0), 0);
  const backtestCount = inMonth.filter(trade => trade.source === 'backtest').length, paperCount = inMonth.length - backtestCount;
  const [year, monthIndex] = month.split('-').map(Number);
  const days = new Date(Date.UTC(year, monthIndex, 0)).getUTCDate();
  const lead = (new Date(Date.UTC(year, monthIndex - 1, 1)).getUTCDay() + 6) % 7;
  const today = istParts().day;
  const listed = day ? inMonth.filter(trade => trade.day === day) : inMonth;
  const go = (next: number) => { setMonth(months[Math.min(months.length - 1, Math.max(0, next))]); setDay(null); };
  return <div className={styles.card}>
    <div className={styles.chartHead}>
      <div>
        <h3>Past trades</h3>
        <p className={styles.caption}>
          {backtestCount ? <>Backtest <b className={tone(sum('backtest'))}>{money(sum('backtest'))}</b> ({backtestCount}) </> : null}
          {paperCount ? <>{backtestCount ? '· ' : ''}Paper <b className={tone(sum('paper'))}>{money(sum('paper'))}</b> ({paperCount})</> : null}
          {!inMonth.length && 'No trades closed this month'}
        </p>
      </div>
      <div className={styles.monthNav}>
        <button onClick={() => go(index - 1)} disabled={index === 0} aria-label="Previous month"><ChevronLeft size={15} /></button>
        <select className={styles.select} value={month} onChange={event => { setMonth(event.target.value); setDay(null); }} aria-label="Calendar month">{[...months].reverse().map(option => <option key={option} value={option}>{monthLabel(option, 'long')}{trades.some(trade => trade.day.startsWith(option)) ? '' : ' · no trades'}</option>)}</select>
        <button onClick={() => go(index + 1)} disabled={index === months.length - 1} aria-label="Next month"><ChevronRight size={15} /></button>
      </div>
    </div>
    <div className={styles.calendar}>
      {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map(name => <span key={name} className={styles.calendarDay}>{name}</span>)}
      {Array.from({ length: lead }, (_, offset) => <span key={`lead-${offset}`} />)}
      {Array.from({ length: days }, (_, offset) => {
        const date = `${month}-${String(offset + 1).padStart(2, '0')}`;
        const cell = byDay[date];
        const net = cell ? cell.backtest + cell.paper : 0;
        const className = [styles.calendarCell, cell ? (net < 0 ? styles.cellLoss : styles.cellProfit) : '', date === today ? styles.cellToday : '', date === day ? styles.cellSelected : ''].join(' ');
        const body = <><span>{offset + 1}</span>{cell && <span className={styles.cellLines}>
          {cell.b > 0 && <b className={tone(cell.backtest)}><i className={styles.backtestMark} title="Backtest">B</i>{money(cell.backtest)}<small>{signedPercent(cell.backtest / capital * 100)}</small></b>}
          {cell.p > 0 && <b className={tone(cell.paper)}>{money(cell.paper)}<small>{signedPercent(cell.paper / capital * 100)}</small></b>}
        </span>}</>;
        return cell ? <button key={date} className={className} onClick={() => setDay(value => value === date ? null : date)} aria-pressed={date === day} title={`${cell.b + cell.p} trade${cell.b + cell.p > 1 ? 's' : ''} closed`}>{body}</button> : <div key={date} className={className}>{body}</div>;
      })}
    </div>
    <p className={styles.legend}><i className={styles.backtestMark}>B</i> Backtest: simulated on historical data · Unmarked: forward paper trade · Returns on {money(capital)} model capital, by exit date (IST).</p>
    {note && <p className={styles.caption}>{note}</p>}
    {listed.length > 0 && <>
      <div className={styles.subHead}><h3>{day ? `Trades closed on ${dayLabel(day)}` : `Trades closed in ${monthLabel(month, 'long')}`}</h3>{day && <button className={styles.linkButton} onClick={() => setDay(null)}>Show whole month</button>}</div>
      <div className={styles.tableCard}><div className={styles.tableScroll}><table className={styles.table}>
        <thead><tr><th>Exit</th><th>Position</th><th>Entry</th><th className={styles.num}>Qty</th><th className={styles.num}>Entry price</th><th className={styles.num}>Exit price</th><th className={styles.num}>Leg P&L</th><th>Exit reason</th><th className={styles.num}>Trade P&L</th></tr></thead>
        <tbody>{listed.flatMap(trade => tradeLegs(trade).map((leg, index, all) => <tr key={trade.key + index} className={all.length === 1 ? undefined : index ? styles.legSecond : styles.legFirst}>
          {index === 0 && <td rowSpan={all.length}>{trade.source === 'backtest' && <i className={styles.backtestMark} title="Backtest">B</i>}{time(trade.exit)}</td>}
          <td><span className={leg.sold ? styles.sellTag : styles.buyTag}>{leg.sold ? 'SELL' : 'BUY'}</span><b>{leg.name}</b></td>
          {index === 0 && <td rowSpan={all.length} className={styles.muted}>{time(trade.entry)}</td>}
          <td className={styles.num} title={`${trade.lots} lots`}>{trade.units}</td>
          <td className={styles.num}>{price(leg.entry)}</td>
          <td className={styles.num}>{price(leg.exit)}</td>
          <td className={`${styles.num} ${tone(leg.pnl)}`}>{money(leg.pnl)}</td>
          {index === 0 && <td rowSpan={all.length} className={styles.muted}>{trade.reason || '—'}</td>}
          {index === 0 && <td rowSpan={all.length} className={`${styles.num} ${tone(trade.pnl)}`}><b>{money(trade.pnl)}</b></td>}
        </tr>))}</tbody>
      </table></div></div>
    </>}
  </div>;
}

function ForwardPositions({ account, onDownload }: { account: Paper | null | undefined; onDownload: () => void }) {
  const [filter, setFilter] = useState<'all' | 'profit' | 'loss'>('all');
  if (!account) return <div className={styles.card}><h3 className={styles.cardTitle}>Forward paper trades</h3><EmptyRow>No paper trades yet. Entries and exits appear here once the paper worker records them.</EmptyRow></div>;
  const closed = account.closed_positions || [];
  const profits = closed.filter(trade => trade.pnl != null && trade.pnl > 0);
  const losses = closed.filter(trade => trade.pnl != null && trade.pnl < 0);
  const visible: Trade[] = filter === 'profit' ? profits : filter === 'loss' ? losses : closed;
  return <>
    <div className={styles.sectionHead}><h2>Forward paper · open</h2><span className={styles.muted}>{account.valuation_ts ? `Marked ${time(account.valuation_ts)}` : 'Awaiting quotes'}</span></div>
    {account.open_position ? <PositionTable trades={[account.open_position]} open totalPnl={account.unrealized_pnl} /> : <div className={styles.tableCard}><EmptyRow>No open paper position.</EmptyRow></div>}
    <div className={styles.sectionHead}><h2>Forward paper · closed legs</h2><Pills label="Filter closed positions" value={filter} onChange={setFilter} items={[{ id: 'all', label: 'All', count: closed.length }, { id: 'profit', label: 'In profit', count: profits.length }, { id: 'loss', label: 'In loss', count: losses.length }]} /><button className={styles.outlineButton} onClick={onDownload} disabled={!closed.length}>Download CSV</button></div>
    {visible.length ? <PositionTable trades={visible} /> : <div className={styles.tableCard}><EmptyRow>{filter === 'all' ? 'No closed paper positions yet.' : `No closed positions ${filter === 'profit' ? 'in profit' : 'in loss'}.`}</EmptyRow></div>}
    <p className={styles.caption}>Realized P&L across the full paper ledger: <b className={tone(account.realized_pnl)}>{money(account.realized_pnl)}</b>. Showing the latest {closed.length} closed trades (maximum {account.ledger_limit}). A trade closed before each leg’s exit price was recorded shows what the whole spread closed at.</p>
  </>;
}

function Monthly({ strategy }: { strategy: Strategy }) {
  const months = strategy.monthly;
  const [selected, setSelected] = useState<number | null>(null);
  const best = months.reduce((top, row, index) => row.return_pct > months[top].return_pct ? index : top, 0);
  const worst = months.reduce((low, row, index) => row.return_pct < months[low].return_pct ? index : low, 0);
  return <>
    <div className={styles.card}>
      <div className={styles.chartHead}><div><h3>Monthly realized P&L</h3><p className={styles.caption}>Backtest · gross P&L booked on exit date. First and last months may be partial.</p></div>
        <div className={styles.inlineStats}><span>Best <b className={styles.green}>{monthLabel(months[best].month)} {signedPercent(months[best].return_pct)}</b></span><span>Worst <b className={tone(months[worst].return_pct)}>{monthLabel(months[worst].month)} {signedPercent(months[worst].return_pct)}</b></span></div></div>
      <MonthlyChart months={months} selected={selected} onSelect={setSelected} />
    </div>
    <div className={styles.tableCard}><div className={styles.tableScroll}><table className={styles.table}>
      <thead><tr><th>Month</th><th className={styles.num}>Closed trades</th><th className={styles.num}>Win rate</th><th className={styles.num}>Return</th><th className={styles.num}>Realized P&L</th></tr></thead>
      <tbody>{months.map((row, index) => ({ row, index })).reverse().map(({ row, index }) => <tr key={row.month} className={index === selected ? styles.rowSelected : ''} onMouseEnter={() => setSelected(index)} onMouseLeave={() => setSelected(null)}>
        <td>{monthLabel(row.month, 'long')}{row.partial_month ? <small>Partial month</small> : null}</td>
        <td className={styles.num}>{row.closed_trades}</td>
        <td className={styles.num}>{percent(row.win_rate_pct)}</td>
        <td className={`${styles.num} ${tone(row.return_pct)}`}>{signedPercent(row.return_pct)}</td>
        <td className={`${styles.num} ${tone(row.pnl)}`}>{money(row.pnl)}</td>
      </tr>)}</tbody>
    </table></div></div>
  </>;
}

function MonthlyChart({ months, selected, onSelect }: { months: Month[]; selected: number | null; onSelect: (index: number | null) => void }) {
  const width = 900, height = 220, left = 40, top = 10, bottom = 190;
  const max = Math.max(1, ...months.map(item => item.pnl)), min = Math.min(0, ...months.map(item => item.pnl));
  const y = (value: number) => top + (max - value) / (max - min || 1) * (bottom - top);
  const step = (width - left) / Math.max(1, months.length);
  return <svg className={styles.chartSvg} viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Monthly gross realized profit and loss; exact values are in the table below." onMouseLeave={() => onSelect(null)}>
    {[min, 0, max].filter((value, index, values) => values.indexOf(value) === index).map(value => <g key={value}><line x1={left} x2={width} y1={y(value)} y2={y(value)} className={styles.grid} /><text x={0} y={y(value) + 4} className={styles.axis}>{(value / 1000).toFixed(0)}k</text></g>)}
    {months.map((item, index) => <g key={item.month} onMouseEnter={() => onSelect(index)}><title>{monthLabel(item.month, 'long')}: {money(item.pnl)}</title>
      <rect x={left + index * step + 4} y={top} width={step - 8} height={bottom - top} rx="4" className={index === selected ? styles.barHover : styles.barHit} />
      <rect x={left + index * step + step * 0.22} y={Math.min(y(0), y(item.pnl))} width={Math.max(3, step * 0.56)} height={Math.max(1, Math.abs(y(item.pnl) - y(0)))} rx="3" className={item.pnl < 0 ? styles.barDown : styles.barUp} />
      <text x={left + index * step + step / 2} y={height - 6} textAnchor="middle" className={styles.axis}>{monthLabel(item.month).split(' ')[0]}</text></g>)}
  </svg>;
}

/** About algo. The API sends rules, limitations, exit policy and the full description to the owner only, and this
 *  view shows them only to the owner too, so an API that still sends everything cannot expose them. */
function Rules({ strategy, owner }: { strategy: Strategy; owner: boolean }) {
  const detailed = owner && !!strategy.rules?.length;
  return <div className={styles.card}>
    <p className={styles.aboutText}>{blurb(strategy, owner)}</p>
    <dl className={styles.rules}>
      <div><dt>Underlying</dt><dd>{strategy.underlying}</dd></div>
      <div><dt>Style</dt><dd>{strategy.category}</dd></div>
      <div><dt>Model capital</dt><dd>{money(strategy.capital)}</dd></div>
      <div><dt>Backtest</dt><dd>{shortDate(strategy.period_start, true)} – {shortDate(strategy.period_end, true)} · {strategy.metrics.trade_count} trades</dd></div>
      {detailed && strategy.rules!.map((rule, index) => { const { label, description } = ruleText(rule); return <div key={index}><dt>{label || `Rule ${index + 1}`}</dt><dd>{description}</dd></div>; })}
      {detailed && strategy.exit_policy && <div><dt>Exit policy</dt><dd>{strategy.exit_policy}</dd></div>}
    </dl>
    {detailed ? <>
      <p className={styles.limitations}><b>Limitations.</b> {strategy.limitations}</p>
      <p className={styles.caption}>Only you see the rules above. These records describe the versioned Python implementation; editing catalogue text does not change the running engine.</p>
    </> : <p className={styles.limitations}><b>Private.</b> The entry, exit and sizing rules are kept by the algo’s author and are not shown here. The performance, past trades and monthly returns tabs are the full record of what it did.</p>}
  </div>;
}
