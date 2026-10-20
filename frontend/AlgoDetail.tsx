'use client';

import { Check, Plus } from 'lucide-react';
import { useMemo, useState, type MouseEvent } from 'react';
import { algoState, istDay, istParts, lakhs, money, monthLabel, percent, periodReturn, ruleText, signedPercent, stateLabel, time, type Month, type Paper, type Strategy, type Trade } from './algoData';
import { AlgoIcon, EmptyRow, Pills, PositionTable, tone } from './algoUi';
import styles from './algos.module.css';

type Tab = 'performance' | 'paper' | 'monthly' | 'rules';
type Range = '1m' | '3m' | '6m' | '1y' | 'all';
const RANGES: { id: Range; label: string; months: number }[] = [{ id: '1m', label: '1M', months: 1 }, { id: '3m', label: '3M', months: 3 }, { id: '6m', label: '6M', months: 6 }, { id: '1y', label: '1Y', months: 12 }, { id: 'all', label: 'All', months: Infinity }];

type Props = { strategy: Strategy; account: Paper | null | undefined; paperLoaded: boolean; following: boolean; saving: boolean; onFollow: (enabled: boolean) => void; onDownload: () => void };

export default function AlgoDetail({ strategy, account, paperLoaded, following, saving, onFollow, onDownload }: Props) {
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
    <Pills label="Algo sections" value={tab} onChange={setTab} items={[{ id: 'performance', label: 'Performance' }, { id: 'paper', label: 'Paper trades' }, { id: 'monthly', label: 'Monthly' }, { id: 'rules', label: 'Rules' }]} />
    {tab === 'performance' && <Performance strategy={strategy} account={account} />}
    {tab === 'paper' && <PaperTrades strategy={strategy} account={account} onDownload={onDownload} />}
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

function PaperTrades({ strategy, account, onDownload }: { strategy: Strategy; account: Paper | null | undefined; onDownload: () => void }) {
  const [filter, setFilter] = useState<'all' | 'profit' | 'loss'>('all');
  if (!account) return <div className={styles.card}><EmptyRow>No paper trades yet. Entries and exits appear here once the paper worker records them.</EmptyRow></div>;
  const closed = account.closed_positions || [];
  const profits = closed.filter(trade => trade.pnl != null && trade.pnl > 0);
  const losses = closed.filter(trade => trade.pnl != null && trade.pnl < 0);
  const visible: Trade[] = filter === 'profit' ? profits : filter === 'loss' ? losses : closed;
  return <>
    <PaperCalendar account={account} capital={account.capital ?? strategy.capital} />
    <div className={styles.sectionHead}><h2>Open</h2><span className={styles.muted}>{account.valuation_ts ? `Marked ${time(account.valuation_ts)}` : 'Awaiting quotes'}</span></div>
    {account.open_position ? <PositionTable trades={[account.open_position]} open totalPnl={account.unrealized_pnl} /> : <div className={styles.tableCard}><EmptyRow>No open paper position.</EmptyRow></div>}
    <div className={styles.sectionHead}><h2>Closed</h2><Pills label="Filter closed positions" value={filter} onChange={setFilter} items={[{ id: 'all', label: 'All', count: closed.length }, { id: 'profit', label: 'In profit', count: profits.length }, { id: 'loss', label: 'In loss', count: losses.length }]} /><button className={styles.outlineButton} onClick={onDownload} disabled={!closed.length}>Download CSV</button></div>
    {visible.length ? <PositionTable trades={visible} /> : <div className={styles.tableCard}><EmptyRow>{filter === 'all' ? 'No closed paper positions yet.' : `No closed positions ${filter === 'profit' ? 'in profit' : 'in loss'}.`}</EmptyRow></div>}
    <p className={styles.caption}>Realized P&L across the full paper ledger: <b className={tone(account.realized_pnl)}>{money(account.realized_pnl)}</b>. Showing the latest {closed.length} closed trades (maximum {account.ledger_limit}); legs without a quote show —.</p>
  </>;
}

function PaperCalendar({ account, capital }: { account: Paper; capital: number }) {
  const closed = account.closed_positions || [];
  const options = useMemo(() => [...new Set([istParts().month, ...closed.map(trade => istDay(trade.exit_ts).slice(0, 7)).filter(Boolean)])].sort().reverse(), [closed]);
  const [month, setMonth] = useState(options[0]);
  const byDay = closed.reduce<Record<string, { pnl: number; count: number }>>((total, trade) => {
    const day = istDay(trade.exit_ts);
    if (day.startsWith(month)) total[day] = { pnl: (total[day]?.pnl ?? 0) + (trade.pnl ?? 0), count: (total[day]?.count ?? 0) + 1 };
    return total;
  }, {});
  const monthPnl = Object.values(byDay).reduce((total, day) => total + day.pnl, 0);
  const [year, monthIndex] = month.split('-').map(Number);
  const days = new Date(Date.UTC(year, monthIndex, 0)).getUTCDate();
  const lead = (new Date(Date.UTC(year, monthIndex - 1, 1)).getUTCDay() + 6) % 7;
  const today = istParts().day;
  return <div className={styles.card}>
    <div className={styles.chartHead}>
      <div><h3>Paper P&L calendar</h3><p className={styles.caption}>By exit date · {Object.keys(byDay).length ? <>month total <b className={tone(monthPnl)}>{money(monthPnl)}</b></> : 'no exits this month'}</p></div>
      <select className={styles.select} value={month} onChange={event => setMonth(event.target.value)} aria-label="Calendar month">{options.map(option => <option key={option} value={option}>{monthLabel(option, 'long')}</option>)}</select>
    </div>
    <div className={styles.calendar}>
      {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map(day => <span key={day} className={styles.calendarDay}>{day}</span>)}
      {Array.from({ length: lead }, (_, index) => <span key={`lead-${index}`} />)}
      {Array.from({ length: days }, (_, index) => {
        const day = `${month}-${String(index + 1).padStart(2, '0')}`;
        const result = byDay[day];
        return <div key={day} className={`${styles.calendarCell} ${result ? (result.pnl < 0 ? styles.cellLoss : styles.cellProfit) : ''} ${day === today ? styles.cellToday : ''}`} title={result ? `${result.count} exit${result.count > 1 ? 's' : ''}` : undefined}><span>{index + 1}</span>{result && <b className={tone(result.pnl)}>{money(result.pnl)}<small>{signedPercent(result.pnl / capital * 100)}</small></b>}</div>;
      })}
    </div>
  </div>;
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
