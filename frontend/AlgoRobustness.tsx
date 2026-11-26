'use client';

import { Check, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Area, Bar, BarChart, CartesianGrid, Cell, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { lakhs, money } from './algoData';
import { EmptyRow } from './algoUi';
import styles from './algos.module.css';

/** One listed algo's reliability checks, served by GET /algos/robustness/{id} from backend/seed_data/algo_robustness.json. */
export type Robustness = {
  strategy_id: string; basis?: string; checked: string; capital: number; trades: number; first: string; last: string; profit: number; split_years: boolean;
  monte_carlo: { runs: number; trades: number; actual_dd: number; p50: number; p95: number; p99: number; past_25: number; luckier_than: number; x: number[]; actual: number[];
    bands: Record<'p5' | 'p25' | 'p50' | 'p75' | 'p95', number[]>; hist: { edges: number[]; counts: number[] } };
  years: { year: number; unseen: number; published: number; trades: number }[];
  placebo?: { period: string; runs: number; p5?: number; median: number; p95: number; best: number; real: number; beats: number }[];
  sensitivity?: { base_profit: number | null; base_dd: number | null; rows: { change: string; trades: number; profit: number; vs: number; dd: number }[] };
  stress?: { label: string; profit: number; dd: number; trades: number }[];
  rules?: { code: string; label: string; passed: boolean }[];
  walk_forward?: { windows: { start: string; end: string; test_trades: number; search_pick: number; listed: number }[]; stitched: { profit: number; per_year: number; dd: number } | null; listed: { profit: number; per_year: number; dd: number } | null };
};
export type LoadRobustness = (id: string) => Promise<Robustness | null>;

const LIMIT = 25;                                   // the drawdown limit for listing, % of model capital
const pct = (value: number, digits = 1) => `${value.toFixed(digits)}%`;
const signed = (value: number, digits = 1) => `${value > 0 ? '+' : ''}${value.toFixed(digits)}%`;
const rupeesShort = (value: number) => `${value < 0 ? '-' : ''}₹${lakhs(Math.abs(value))}`;
const monthYear = (day: string) => new Date(`${day}T00:00:00Z`).toLocaleDateString('en-IN', { month: 'short', year: '2-digit', timeZone: 'UTC' });
const tip = { contentStyle: { background: 'var(--card)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 11, color: 'var(--foreground)' }, labelStyle: { color: 'var(--muted-foreground)' }, cursor: { fill: 'var(--muted)', opacity: .5 } };
const axis = { tick: { fontSize: 11, fill: 'var(--muted-foreground)' }, axisLine: false, tickLine: false } as const;

export default function AlgoRobustness({ strategyId, load }: { strategyId: string; load: LoadRobustness }) {
  const [data, setData] = useState<Robustness | null>(null);
  const [state, setState] = useState<'loading' | 'ready' | 'missing' | 'error'>('loading');
  useEffect(() => {
    let live = true;
    setState('loading');
    load(strategyId).then(body => { if (live) { setData(body); setState(body ? 'ready' : 'missing'); } }).catch(() => { if (live) setState('error'); });
    return () => { live = false; };
  }, [strategyId, load]);
  if (state !== 'ready' || !data) return <div className={styles.card}><EmptyRow>{state === 'loading' ? 'Loading checks…' : state === 'missing' ? 'This algo has not been through the reliability checks yet.' : 'The checks could not be loaded.'}</EmptyRow></div>;
  return <div className={styles.robust}>
    <Verdict data={data} />
    <MonteCarlo data={data} />
    {data.placebo?.length ? <Placebo data={data} /> : null}
    {data.sensitivity?.rows.length ? <Sensitivity data={data} /> : null}
    <Years data={data} />
    {data.stress?.length ? <Stress data={data} /> : null}
    {data.walk_forward?.windows.length ? <WalkForward data={data} /> : null}
  </div>;
}

function Verdict({ data }: { data: Robustness }) {
  const rules = data.rules || [];
  const passed = rules.filter(rule => rule.passed).length;
  return <div className={styles.card}>
    <div className={styles.chartHead}>
      <div><h3>Reliability checks</h3><p className={styles.caption}>Checked {data.checked} · {data.trades} trades, {monthYear(data.first)} – {monthYear(data.last)} · after costs {money(data.profit)}</p></div>
      {rules.length > 0 && <div className={styles.robustScore}><b className={passed / rules.length >= .8 ? styles.green : passed / rules.length >= .5 ? styles.amber : styles.red}>{passed}</b><span>of {rules.length} rules passed</span></div>}
    </div>
    {rules.length > 0 && <ul className={styles.ruleChips}>{rules.map(rule => <li key={rule.code} className={rule.passed ? styles.rulePass : styles.ruleFail} title={rule.code}>{rule.passed ? <Check size={12} /> : <X size={12} />}{rule.label}</li>)}</ul>}
    <p className={styles.caption}>{data.basis}</p>
  </div>;
}

function Stat({ label, value, tone, note }: { label: string; value: string; tone?: string; note?: string }) {
  return <div className={styles.robustStat}><span>{label}</span><b className={tone}>{value}</b>{note && <small>{note}</small>}</div>;
}

function MonteCarlo({ data }: { data: Robustness }) {
  const mc = data.monte_carlo, b = mc.bands;
  const fan = mc.x.map((trade, i) => ({ trade, actual: mc.actual[i], outer: [b.p5[i], b.p95[i]], inner: [b.p25[i], b.p75[i]], median: b.p50[i] }));
  const bins = mc.hist.counts.map((count, i) => ({ from: mc.hist.edges[i], label: `${mc.hist.edges[i]}–${mc.hist.edges[i + 1]}%`, count }));
  const lucky = mc.luckier_than >= 80;
  return <div className={styles.card}>
    <div className={styles.chartHead}><div><h3>Luck of the trade order</h3><p className={styles.caption}>The same {mc.trades} trades replayed in {mc.runs.toLocaleString('en-IN')} random orders. Profit never changes; the path and the drawdown do.</p></div></div>
    <div className={styles.robustStats}>
      <Stat label="Drawdown in the actual order" value={pct(mc.actual_dd)} />
      <Stat label="Bad luck, 1 order in 20" value={pct(mc.p95)} tone={mc.p95 > 30 ? styles.red : mc.p95 > LIMIT ? styles.amber : undefined} note={`${(mc.p95 / mc.actual_dd).toFixed(1)}× the actual`} />
      <Stat label={`Orders past ${LIMIT}%`} value={pct(mc.past_25, 0)} tone={mc.past_25 > 50 ? styles.red : undefined} />
      <Stat label="Actual order luckier than" value={pct(mc.luckier_than, 0)} tone={lucky ? styles.amber : undefined} note={lucky ? 'the drawdown shown is a lucky path' : 'a typical path'} />
    </div>
    <div className={styles.robustLegend}><span><i className={styles.swatchLine} />Actual order</span><span><i className={styles.swatchInner} />Middle half of orders</span><span><i className={styles.swatchOuter} />90% of orders</span></div>
    <div className={styles.robustChart}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={fan} margin={{ top: 6, right: 8, bottom: 0, left: -12 }}>
          <CartesianGrid vertical={false} stroke="var(--border)" />
          <XAxis dataKey="trade" {...axis} tickCount={8} type="number" domain={[1, mc.trades]} />
          <YAxis {...axis} tickFormatter={value => `${value}%`} />
          <Tooltip {...tip} labelFormatter={value => `After trade ${value}`} formatter={(value: number | number[], name: string) => [Array.isArray(value) ? `${value[0]}% to ${value[1]}%` : `${value}%`, name]} />
          <Area dataKey="outer" name="90% of orders" stroke="none" fill="var(--primary)" fillOpacity={.1} isAnimationActive={false} />
          <Area dataKey="inner" name="Middle half" stroke="none" fill="var(--primary)" fillOpacity={.22} isAnimationActive={false} />
          <Line dataKey="actual" name="Actual order" stroke="var(--foreground)" strokeWidth={2} dot={false} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
    <p className={styles.robustSub}>Cumulative profit after costs, % of {money(data.capital)} model capital, by trade number</p>
    <div className={styles.robustChartShort}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={bins} margin={{ top: 18, right: 8, bottom: 0, left: -12 }} barCategoryGap={2}>
          <CartesianGrid vertical={false} stroke="var(--border)" />
          <XAxis dataKey="label" {...axis} interval="preserveStartEnd" />
          <YAxis {...axis} allowDecimals={false} />
          <Tooltip {...tip} formatter={(value: number) => [`${value} of ${mc.runs.toLocaleString('en-IN')} orders`, 'Worst drawdown']} />
          <Bar dataKey="count" radius={[3, 3, 0, 0]} isAnimationActive={false}>
            {bins.map(bin => <Cell key={bin.from} fill={bin.from + 5 > mc.p95 ? 'var(--down)' : 'var(--primary)'} fillOpacity={.75} />)}
          </Bar>
          <ReferenceLine x={bins.find(bin => mc.actual_dd >= bin.from && mc.actual_dd < bin.from + 5)?.label} stroke="var(--foreground)" strokeDasharray="4 3" label={{ value: `Actual ${pct(mc.actual_dd)}`, position: 'top', fontSize: 11, fill: 'var(--foreground)' }} />
        </BarChart>
      </ResponsiveContainer>
    </div>
    <p className={styles.robustSub}>Worst drawdown in each random order (red: the worst 1 in 20)</p>
  </div>;
}

/** Each period on one strip: the middle 90% of random-entry runs, their median and best, and the algo itself. */
function Placebo({ data }: { data: Robustness }) {
  const rows = data.placebo!;
  return <div className={styles.card}>
    <div className={styles.chartHead}><div><h3>Against random entries</h3><p className={styles.caption}>500 runs that enter at random times but keep this algo’s exits, sizing and costs. A real edge should beat at least 95% of them.</p></div></div>
    <div className={styles.placeboRows}>{rows.map(row => {
      const lo = Math.min(row.p5 ?? row.median, row.real, 0), hi = Math.max(row.best, row.real);
      const span = hi - lo || 1, at = (value: number) => `${(value - lo) / span * 100}%`;
      const pass = row.beats >= 95;
      return <div key={row.period} className={styles.placeboRow}>
        <div className={styles.placeboLabel}><b>{row.period}</b><span className={pass ? styles.green : styles.red}>beats {pct(row.beats, row.beats % 1 ? 1 : 0)}</span></div>
        <div className={styles.placeboTrack} role="img" aria-label={`${row.period}: random runs ${row.p5 != null ? `5% ${money(row.p5)}, ` : ''}median ${money(row.median)}, 95% ${money(row.p95)}, best ${money(row.best)}; this algo ${money(row.real)}`}>
          <i className={styles.placeboZero} style={{ left: at(0) }} />
          <i className={styles.placeboBand} style={{ left: at(row.p5 ?? row.median), width: `calc(${at(row.p95)} - ${at(row.p5 ?? row.median)})` }} title={`Middle ${row.p5 != null ? '90%' : 'half to 95th'} of random runs`} />
          <i className={styles.placeboMedian} style={{ left: at(row.median) }} title={`Random median ${money(row.median)}`} />
          <i className={styles.placeboBest} style={{ left: at(row.best) }} title={`Best random run ${money(row.best)}`} />
          <i className={pass ? styles.placeboReal : styles.placeboRealFail} style={{ left: at(row.real) }} title={`This algo ${money(row.real)}`} />
        </div>
        <div className={styles.placeboNums}><span>random median {rupeesShort(row.median)}</span><span>best {rupeesShort(row.best)}</span><b>algo {rupeesShort(row.real)}</b></div>
      </div>;
    })}</div>
    <div className={styles.robustLegend}><span><i className={styles.swatchOuter} />{rows.some(row => row.p5 != null) ? '5th to 95th percentile of random runs' : 'Median to 95th percentile of random runs'}</span><span><i className={styles.swatchTick} />Random median · best</span><span><i className={styles.swatchDot} />This algo</span></div>
  </div>;
}

/** Each setting moved about 20% either way: profit change as a bar, worst first; amber when the drawdown passes the limit. */
function Sensitivity({ data }: { data: Robustness }) {
  const s = data.sensitivity!;
  const rows = [...s.rows].sort((a, b) => a.vs - b.vs);
  const reach = Math.max(50, ...rows.map(row => Math.abs(row.vs)));
  const past = rows.filter(row => row.dd > LIMIT).length, halved = rows.filter(row => row.vs <= -50).length;
  return <div className={styles.card}>
    <div className={styles.chartHead}><div><h3>Settings moved 20%</h3><p className={styles.caption}>Each setting nudged about 20% up and down, everything else unchanged. A robust algo sits on a plateau: small changes, small effects.</p></div>
      <div className={styles.inlineStats}><span>Halve the profit<b className={halved ? styles.red : styles.green}>{halved} of {rows.length}</b></span><span>Drawdown past {LIMIT}%<b className={past > rows.length / 4 ? styles.red : past ? styles.amber : styles.green}>{past} of {rows.length}</b></span></div></div>
    <div className={styles.sensHead}><span>Change</span><span>Profit vs base{s.base_profit != null ? ` (${rupeesShort(s.base_profit)})` : ''}</span><span>Drawdown{s.base_dd != null ? ` (base ${pct(s.base_dd)})` : ''}</span></div>
    <div className={styles.sensRows}>{rows.map(row => <div key={row.change} className={styles.sensRow} title={`${row.trades} trades, ${money(row.profit)}`}>
      <span className={styles.sensLabel}>{row.change}</span>
      <span className={styles.sensBarBox}>
        <i className={styles.sensAxis} />
        <i className={row.vs < 0 ? styles.sensBarDown : styles.sensBarUp} style={row.vs < 0 ? { right: '50%', width: `${Math.abs(row.vs) / reach * 50}%` } : { left: '50%', width: `${row.vs / reach * 50}%` }} />
        <em style={row.vs < 0 ? { right: `calc(50% + ${Math.abs(row.vs) / reach * 50}% + 4px)` } : { left: `calc(50% + ${row.vs / reach * 50}% + 4px)` }}>{signed(row.vs)}</em>
      </span>
      <span className={styles.sensDd}><i style={{ width: `${Math.min(row.dd, 60) / 60 * 100}%` }} className={row.dd > LIMIT ? styles.sensDdWarn : ''} /><b className={row.dd > LIMIT ? styles.amber : ''}>{pct(row.dd)}</b></span>
    </div>)}</div>
    <p className={styles.caption}>Five-year run with next-candle fills and real costs. The drawdown bar is full at 60% and turns amber past the {LIMIT}% listing limit.</p>
  </div>;
}

function Years({ data }: { data: Robustness }) {
  const rows = data.years.map(row => ({ year: String(row.year), unseen: row.unseen, published: row.published, total: row.unseen + row.published, trades: row.trades }));
  return <div className={styles.card}>
    <div className={styles.chartHead}><div><h3>Year by year</h3><p className={styles.caption}>{data.split_years ? 'Profit after costs per calendar year. Before 4 Oct 2023 no search had seen the data, so those trades are a true out-of-sample test.' : 'Profit after costs per calendar year. Its entry rule was searched on Dec 2025 – Nov 2026 and its exits on 2022 – 2024, so no year here is fully unseen.'}</p></div></div>
    {data.split_years && <div className={styles.robustLegend}><span><i className={styles.swatchUnseen} />Unseen by any search</span><span><i className={styles.swatchPublished} />Period the rules were found on</span></div>}
    <div className={styles.robustChartShort}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} margin={{ top: 6, right: 8, bottom: 0, left: 4 }} barSize={34}>
          <CartesianGrid vertical={false} stroke="var(--border)" />
          <XAxis dataKey="year" {...axis} />
          <YAxis {...axis} tickFormatter={value => rupeesShort(value)} width={52} />
          <ReferenceLine y={0} stroke="var(--border)" />
          <Tooltip {...tip} formatter={(value: number, name: string) => [money(value), name]} labelFormatter={(label, items) => `${label} · ${items?.[0]?.payload?.trades ?? 0} trades · ${money(items?.[0]?.payload?.total ?? 0)}`} />
          {data.split_years && <Bar dataKey="unseen" name="Unseen" stackId="y" fill="var(--warning)" fillOpacity={.75} isAnimationActive={false} />}
          <Bar dataKey="published" name={data.split_years ? 'Rules found on' : 'Profit'} stackId="y" fill="var(--primary)" fillOpacity={.75} radius={[3, 3, 0, 0]} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
    <p className={styles.robustSub}>2021 and 2026 are part years.</p>
  </div>;
}

/** Profit and drawdown when trading gets more expensive or fills come later. */
function Stress({ data }: { data: Robustness }) {
  const rows = data.stress!;
  const top = Math.max(...rows.map(row => Math.abs(row.profit)));
  return <div className={styles.card}>
    <div className={styles.chartHead}><div><h3>Costs and fill timing</h3><p className={styles.caption}>The same five years with costs removed, doubled, or orders filled at a different minute. A fragile algo loses its edge here.</p></div></div>
    <div className={styles.stressRows}>{rows.map(row => { const base = row.label.includes('(base)'); return <div key={row.label} className={`${styles.stressRow} ${base ? styles.stressBase : ''}`}>
      <span>{row.label.replace(' (base)', '')}{base && <small>base</small>}</span>
      <span className={styles.stressBar}><i className={row.profit < 0 ? styles.sensBarDown : styles.sensBarUp} style={{ width: `${Math.abs(row.profit) / top * 100}%`, left: 0 }} /><em>{money(row.profit)}</em></span>
      <b className={row.dd > LIMIT ? styles.amber : ''}>{pct(row.dd)} <small>drawdown</small></b>
    </div>; })}</div>
  </div>;
}

/** Re-running the whole search on each two-year window and trading its winner for the next six months. */
function WalkForward({ data }: { data: Robustness }) {
  const wf = data.walk_forward!;
  const rows = wf.windows.map(row => ({ label: `${monthYear(row.start)}–${monthYear(row.end)}`, search: row.search_pick, listed: row.listed, trades: row.test_trades }));
  return <div className={styles.card}>
    <div className={styles.chartHead}><div><h3>Walk-forward</h3><p className={styles.caption}>The full rule search re-run on each two years of data, and its winner traded on the six months after. This is what the search process earns on data it has not seen.</p></div>
      {wf.stitched && wf.listed && <div className={styles.inlineStats}><span>Search, out of sample<b className={styles.red}>{pct(wf.stitched.per_year)} a year · DD {pct(wf.stitched.dd)}</b></span><span>Listed rule, same months<b>{pct(wf.listed.per_year)} a year · DD {pct(wf.listed.dd)}</b></span></div>}</div>
    <div className={styles.robustLegend}><span><i className={styles.swatchWarn} />Search winner, next six months</span><span><i className={styles.swatchPublished} />Listed rule, same months (not out of sample)</span></div>
    <div className={styles.robustChartShort}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} margin={{ top: 6, right: 8, bottom: 0, left: 4 }} barGap={2}>
          <CartesianGrid vertical={false} stroke="var(--border)" />
          <XAxis dataKey="label" {...axis} interval={0} />
          <YAxis {...axis} tickFormatter={value => rupeesShort(value)} width={52} />
          <ReferenceLine y={0} stroke="var(--border)" />
          <Tooltip {...tip} formatter={(value: number, name: string) => [money(value), name]} />
          <Bar dataKey="search" name="Search winner, out of sample" fill="var(--warning)" fillOpacity={.8} radius={[3, 3, 0, 0]} isAnimationActive={false} />
          <Bar dataKey="listed" name="Listed rule" fill="var(--primary)" fillOpacity={.75} radius={[3, 3, 0, 0]} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  </div>;
}
