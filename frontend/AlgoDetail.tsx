'use client';

import { Check, ChevronLeft, ChevronRight, Plus } from 'lucide-react';
import { useEffect, useMemo, useState, type MouseEvent } from 'react';
import { algoState, istParts, lakhs, money, monthLabel, pastTrades, percent, periodReturn, ruleText, signedPercent, stateLabel, time, type BacktestLedger, type Month, type Paper, type PastTrade, type Strategy, type Trade } from './algoData';
import { AlgoIcon, EmptyRow, Pills, PositionTable, tone } from './algoUi';
import styles from './algos.module.css';

type Tab = 'performance' | 'trades' | 'monthly' | 'rules';
type Range = '1m' | '3m' | '6m' | '1y' | 'all';
const RANGES: { id: Range; label: string; months: number }[] = [{ id: '1m', label: '1M', months: 1 }, { id: '3m', label: '3M', months: 3 }, { id: '6m', label: '6M', months: 6 }, { id: '1y', label: '1Y', months: 12 }, { id: 'all', label: 'All', months: Infinity }];

type LoadBacktest = (id: string) => Promise<BacktestLedger | null>;
type Props = { strategy: Strategy; account: Paper | null | undefined; paperLoaded: boolean; following: boolean; saving: boolean; onFollow: (enabled: boolean) => void; onDownload: () => void; loadBacktest: LoadBacktest };

export default function AlgoDetail({ strategy, account, paperLoaded, following, saving, onFollow, onDownload, loadBacktest }: Props) {
  const [tab, setTab] = useState<Tab>('performance');
  const state = algoState(account);
  return <>
    <div className={`${styles.card} ${styles.detailHead}`}>
      <AlgoIcon version={strategy.version} size="lg" />
      <div className={styles.detailTitle}>
        <h2>{strategy.name}</h2>
        <p>{strategy.underlying} · {strategy.category} · <span className={`${styles.state} ${styles[`state_${state.replace('-', '_')}`]}`}><i />{paperLoaded ? stateLabel[state] : 'Loading'}</span></p>
      </div>
      <div className={styles.detailStat}><span>Model capital</span><b>{money(account?.capital ?? strategy.capital)}</b></div>
      <div className={styles.detailStat}><span>Backtest 3M</span><b className={tone(strategy.metrics.return_3m_pct)}>{signedPercent(strategy.metrics.return_3m_pct)}</b></div>
      <button className={following ? styles.followingButton : styles.followButton} onClick={() => onFollow(!following)} disabled={saving || !paperLoaded} title={following ? 'Click to stop following' : 'Follow this algo’s paper trades'}>{following ? <Check size={15} /> : <Plus size={15} />}{saving ? 'Saving…' : following ? 'Following' : 'Follow'}</button>
    </div>
    <Pills label="Algo sections" value={tab} onChange={setTab} items={[{ id: 'performance', label: 'Performance' }, { id: 'trades', label: 'Past trades' }, { id: 'monthly', label: 'Monthly' }, { id: 'rules', label: 'Rules' }]} />
    {tab === 'performance' && <Performance strategy={strategy} account={account} />}
    {tab === 'trades' && <PastTrades strategy={strategy} account={account} onDownload={onDownload} loadBacktest={loadBacktest} />}
    {tab === 'monthly' && <Monthly strategy={strategy} />}
    {tab === 'rules' && <Rules strategy={strategy} />}
  </>;
}

/** Backtest equity: model capital plus cumulative gross P&L at each month end. */
function equityPoints(strategy: Strategy) {
  let value = strategy.capital;
  return [{ label: strategy.period_start, value }, ...strategy.monthly.map(month => { value += month.pnl; return { label: (month as Month & { observed_end?: string }).observed_end || `${month.month}-28`, value }; })];
}
const shortDate = (value: string, withDay = false) => new Date(`${value}T00:00:00Z`).toLocaleDateString('en-IN', { day: withDay ? 'numeric' : undefined, month: 'short', year: 'numeric', timeZone: 'UTC' });

function EquityChart({ points }: { points: { label: string; value: number }[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const width = 900, height = 280, left = 8, right = 56, top = 12, bottom = height - 30;
  const values = points.map(point => point.value);
  const rawMin = Math.min(...values), rawMax = Math.max(...values);
  const pad = Math.max((rawMax - rawMin) * 0.12, rawMax * 0.02, 1);
  const min = Math.max(0, rawMin - pad), max = rawMax + pad;
  const x = (index: number) => left + (points.length < 2 ? 0 : index / (points.length - 1)) * (width - left - right);
  const y = (value: number) => top + (max - value) / (max - min) * (bottom - top);
  const line = points.map((point, index) => `${index ? 'L' : 'M'}${x(index).toFixed(1)},${y(point.value).toFixed(1)}`).join(' ');
  const ticks = Array.from({ length: 4 }, (_, index) => min + (max - min) * index / 3);
  const labelEvery = Math.max(1, Math.ceil(points.length / 6));
  const onMove = (event: MouseEvent<SVGSVGElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    const position = (event.clientX - box.left) / box.width * width;
    setHover(Math.max(0, Math.min(points.length - 1, Math.round((position - left) / ((width - left - right) / Math.max(1, points.length - 1))))));
  };
  const point = hover == null ? null : points[hover];
  const up = points[points.length - 1].value >= points[0].value;
  return <svg className={`${styles.chartSvg} ${up ? styles.chartUp : styles.chartDown}`} viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Cumulative backtest equity by month" onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
    <defs><linearGradient id="equityFill" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" className={styles.fillTop} /><stop offset="100%" className={styles.fillBottom} /></linearGradient></defs>
    {ticks.map(value => <g key={value}><line x1={left} x2={width - right} y1={y(value)} y2={y(value)} className={styles.grid} /><text x={width - right + 8} y={y(value) + 4} className={styles.axis}>{lakhs(value)}</text></g>)}
    <path d={`${line} L${x(points.length - 1)},${bottom} L${x(0)},${bottom} Z`} fill="url(#equityFill)" />
    <path d={line} className={styles.line} />
    {points.map((item, index) => index % labelEvery === 0 && index > 0 && <text key={item.label} x={x(index)} y={height - 8} textAnchor="middle" className={styles.axis}>{shortDate(item.label)}</text>)}
    {point && hover != null && <g pointerEvents="none">
      <line x1={x(hover)} x2={x(hover)} y1={top} y2={bottom} className={styles.crosshair} />
      <circle cx={x(hover)} cy={y(point.value)} r="4" className={styles.dot} />
      <g transform={`translate(${Math.min(x(hover) + 10, width - right - 150)},${Math.max(top, y(point.value) - 56)})`}><rect width="140" height="44" rx="6" className={styles.tooltip} /><text x="10" y="18" className={styles.axis}>{shortDate(point.label, true)}</text><text x="10" y="35" className={styles.tooltipValue}>{money(point.value)}</text></g>
    </g>}
  </svg>;
}

function Performance({ strategy, account }: { strategy: Strategy; account: Paper | null | undefined }) {
  const [range, setRange] = useState<Range>('all');
  const points = equityPoints(strategy);
  const months = RANGES.find(item => item.id === range)!.months;
  const visible = Number.isFinite(months) ? points.slice(-(months + 1)) : points;
  const capital = account?.capital ?? strategy.capital;
  const up = strategy.monthly.filter(month => month.pnl > 0);
  return <>
    <div className={styles.card}>
      <div className={styles.chartHead}>
        <div><h3>Backtest equity</h3><p className={styles.caption}>{money(strategy.capital)} model capital · {shortDate(strategy.period_start, true)} – {shortDate(strategy.period_end, true)}</p></div>
        <div className={styles.rangePills}>{RANGES.map(item => { const value = periodReturn(strategy, item.id); return <button key={item.id} className={range === item.id ? styles.rangeActive : ''} aria-pressed={range === item.id} onClick={() => setRange(item.id)}>{item.label}<span className={tone(value)}>{signedPercent(value)}</span></button>; })}</div>
      </div>
      <EquityChart points={visible} />
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

const spreadName = (trade: PastTrade) => `NIFTY ${trade.expiry} ${trade.sell}/${trade.buy} ${trade.type}`;
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
        <thead><tr><th>Exit</th><th>Spread</th><th>Entry</th><th className={styles.num}>Lots</th><th>Exit reason</th><th className={styles.num}>P&L</th></tr></thead>
        <tbody>{listed.map(trade => <tr key={trade.key}>
          <td>{trade.source === 'backtest' && <i className={styles.backtestMark} title="Backtest">B</i>}{time(trade.exit)}</td>
          <td><b>{spreadName(trade)}</b></td>
          <td className={styles.muted}>{time(trade.entry)}</td>
          <td className={styles.num}>{trade.lots}</td>
          <td className={styles.muted}>{trade.reason || '—'}</td>
          <td className={`${styles.num} ${tone(trade.pnl)}`}>{money(trade.pnl)}</td>
        </tr>)}</tbody>
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
    <p className={styles.caption}>Realized P&L across the full paper ledger: <b className={tone(account.realized_pnl)}>{money(account.realized_pnl)}</b>. Showing the latest {closed.length} closed trades (maximum {account.ledger_limit}); legs without a quote show —.</p>
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

function Rules({ strategy }: { strategy: Strategy }) {
  return <div className={styles.card}>
    <p className={styles.aboutText}>{strategy.description}</p>
    <dl className={styles.rules}>{strategy.rules.map((rule, index) => { const { label, description } = ruleText(rule); return <div key={index}><dt>{label || `Rule ${index + 1}`}</dt><dd>{description}</dd></div>; })}</dl>
    <p className={styles.limitations}><b>Limitations.</b> {strategy.limitations}</p>
    <p className={styles.caption}>These records describe the versioned Python implementation. Editing catalogue text does not change the running engine.</p>
  </div>;
}
