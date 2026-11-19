'use client';

import { ArrowDownRight, ArrowUpRight, FileText, History } from 'lucide-react';
import { useId, type CSSProperties, type ReactNode } from 'react';
import { legName, money, signedPercent, time, type Trade } from './algoData';
import styles from './algos.module.css';

export const tone = (value: number | null | undefined) => value == null || value === 0 ? '' : value < 0 ? styles.red : styles.green;

const ICON_TONES = ['#0c9b63', '#4f63d2', '#e8833a', '#0e96c9', '#b5479b'];
export function AlgoIcon({ version, size = 'md' }: { version: string; size?: 'md' | 'lg' }) {
  const color = ICON_TONES[[...version].reduce((total, char) => total + char.charCodeAt(0), 0) % ICON_TONES.length];
  return <span className={size === 'lg' ? styles.algoIconLg : styles.algoIcon} style={{ '--tile': color } as CSSProperties} aria-hidden="true">{version}</span>;
}

/** Segmented control for filters. */
export function Pills<T extends string>({ items, value, onChange, label }: { items: { id: T; label: string; count?: number }[]; value: T; onChange: (id: T) => void; label: string }) {
  return <div className={styles.pills} role="group" aria-label={label}>{items.map(item => <button key={item.id} className={value === item.id ? styles.pillActive : ''} aria-pressed={value === item.id} onClick={() => onChange(item.id)}>{item.label}{item.count != null && <span>{item.count}</span>}</button>)}</div>;
}

/** Outlined section tabs, one bordered pill per section. */
export function Tabs<T extends string>({ items, value, onChange, label }: { items: { id: T; label: string }[]; value: T; onChange: (id: T) => void; label: string }) {
  return <div className={styles.tabPills} role="group" aria-label={label}>{items.map(item => <button key={item.id} className={value === item.id ? styles.tabPillActive : ''} aria-pressed={value === item.id} onClick={() => onChange(item.id)}>{item.label}</button>)}</div>;
}

/** Signed return with a direction arrow. */
export function Return({ value }: { value: number | null | undefined }) {
  const Arrow = value == null || !Number.isFinite(value) || value === 0 ? null : value > 0 ? ArrowUpRight : ArrowDownRight;
  return <span className={`${styles.ret} ${tone(value)}`}>{signedPercent(value)}{Arrow && <Arrow size={14} strokeWidth={2.2} aria-hidden="true" />}</span>;
}

export function BacktestTag() {
  return <span className={styles.backtestTag} title="Simulated on historical data, gross of costs"><History size={10} strokeWidth={2.4} aria-hidden="true" />Backtest</span>;
}

/** Small filled line chart with no axes; the shape is the message, exact values live elsewhere. */
export function Sparkline({ values, label }: { values: number[]; label: string }) {
  const id = `spark${useId().replace(/:/g, '')}`;
  const width = 240, height = 44, pad = 3;
  const min = Math.min(...values), max = Math.max(...values), span = max - min || 1;
  const x = (index: number) => values.length < 2 ? 0 : index / (values.length - 1) * width;
  const y = (value: number) => pad + (max - value) / span * (height - pad * 2);
  const line = values.map((value, index) => `${index ? 'L' : 'M'}${x(index).toFixed(1)},${y(value).toFixed(1)}`).join(' ');
  const up = values[values.length - 1] >= values[0];
  return <svg className={`${styles.spark} ${up ? styles.chartUp : styles.chartDown}`} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="img" aria-label={label}>
    <defs><linearGradient id={id} x1="0" x2="0" y1="0" y2="1"><stop offset="0%" className={styles.fillTop} /><stop offset="100%" className={styles.fillBottom} /></linearGradient></defs>
    <path d={`${line} L${width},${height} L0,${height} Z`} fill={`url(#${id})`} />
    <path d={line} className={styles.sparkLine} />
  </svg>;
}

export function EmptyRow({ children }: { children: ReactNode }) {
  return <div className={styles.emptyRow}><FileText size={22} strokeWidth={1.4} />{children}</div>;
}

const quote = (value: number | null | undefined) => value == null ? '—' : value.toFixed(2);

/** Paper legs, one row per option leg. `algo` adds the algo column for cross-algo tables. */
export function PositionTable({ trades, open = false, totalPnl, algo }: { trades: Trade[]; open?: boolean; totalPnl?: number | null; algo?: (trade: Trade) => string }) {
  return <div className={styles.tableCard}><div className={styles.tableScroll}><table className={styles.table}>
    <thead><tr><th>Name</th>{algo && <th>Algo</th>}<th>Product</th><th className={styles.num}>Qty</th><th className={styles.num}>Buy avg</th><th className={styles.num}>Sell avg</th><th className={styles.num}>{open ? 'LTP' : 'Exit price'}</th><th className={styles.num}>P&L</th></tr></thead>
    <tbody>{trades.flatMap(trade => (['sell', 'buy'] as const).map(side => {
      const sell = side === 'sell';
      const entry = sell ? trade.sell_price : trade.buy_price;
      const current = open ? (sell ? trade.sell_mark : trade.buy_mark) : (sell ? trade.sell_exit_price : trade.buy_exit_price);
      const pnl = current == null ? null : (sell ? entry - current : current - entry) * trade.units;
      return <tr key={trade.signal_id + side}>
        <td><b>{legName(trade, side)}</b><small><span className={sell ? styles.sellTag : styles.buyTag}>{sell ? 'SELL' : 'BUY'}</span> Entry {time(trade.entry_ts)}{!open && ` · Exit ${time(trade.exit_ts)}`}</small></td>
        {algo && <td>{algo(trade)}</td>}
        <td><span className={styles.paperTag}>Paper</span></td>
        <td className={styles.num}>{open && sell ? '−' : ''}{trade.units}<small>{trade.lots} lots</small></td>
        <td className={styles.num}>{quote(sell ? (open ? null : current) : entry)}</td>
        <td className={styles.num}>{quote(sell ? entry : (open ? null : current))}</td>
        <td className={styles.num}>{quote(current)}</td>
        <td className={`${styles.num} ${tone(pnl)}`}>{money(pnl, 2)}</td>
      </tr>;
    }))}</tbody>
    {totalPnl !== undefined && <tfoot><tr><td colSpan={algo ? 7 : 6}>{open ? 'Open positions P&L' : 'Total'}</td><td className={`${styles.num} ${tone(totalPnl)}`}>{money(totalPnl, 2)}</td></tr></tfoot>}
  </table></div></div>;
}
