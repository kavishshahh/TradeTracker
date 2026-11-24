'use client';

import { AlertTriangle } from 'lucide-react';
import { useEffect, useState } from 'react';
import type { Strategy } from './algoData';
import type { CheckRow, CostRow, Research, ResearchChecks, ResearchNote } from './researchData';
import { AlgoIcon, EmptyRow, tone } from './algoUi';
import base from './algos.module.css';
import styles from './algoResearch.module.css';

const DRAWDOWN_LIMIT = 25, PLACEBO_PASS = 95;

/** Algo Lab > Research (owner only): how the listed algos did on the reliability checks, and write-ups of
 *  strategies that were tested and not listed. `load` fetches them once per page load; the notes are never
 *  part of the page bundle. */
export default function AlgoResearch({ load, catalog }: { load: () => Promise<Research>; catalog: Strategy[] }) {
  const [research, setResearch] = useState<Research | null>(null);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let current = true;
    setError('');
    load().then(body => { if (current) setResearch(body); })
      .catch(() => { if (current) setError('Research notes are unavailable right now.'); });
    return () => { current = false; };
  }, [load, attempt]);

  if (!research) return <div className={base.card}>
    <EmptyRow>{error || 'Loading research notes…'}</EmptyRow>
    {error && <button className={base.outlineButton} onClick={() => setAttempt(value => value + 1)}>Try again</button>}
  </div>;

  const rows = research.checks?.rows || [];
  const done = rows.filter(row => row.passed != null);
  const clean = done.filter(row => row.passed === row.rules);

  return <div className={styles.research}>
    <section className={styles.tiles} aria-label="Research summary">
      <div className={styles.tile}><span>Listed algos checked</span><b>{done.length}<em>of {rows.length || catalog.length}</em></b><small>Next-candle fills, real costs, five years</small></div>
      <div className={styles.tile}><span>Passed every rule</span><b className={done.length && !clean.length ? styles.amber : ''}>{clean.length}<em>of {done.length} checked</em></b><small>{done.length && done.every(row => (row.placebo ?? 0) < PLACEBO_PASS) ? 'None clearly beat random entries on unseen data' : 'Rules are fixed before each run'}</small></div>
      <div className={styles.tile}><span>Tested and not listed</span><b>{research.notes.length}<em>{research.notes.length === 1 ? 'strategy' : 'strategies'}</em></b><small>What was tried, what it earned and why it was left out</small></div>
    </section>

    {research.checks && <Checks checks={research.checks} catalog={catalog} />}

    <div className={styles.sectionHead}><h2>Tested and not listed</h2><small>Built and tested, then left out</small></div>
    {research.notes.length ? research.notes.map(note => <ResearchCard key={note.id} note={note} />) : <div className={base.card}><EmptyRow>No research notes yet.</EmptyRow></div>}
    <p className={base.caption}>{research.method} Only you can see this tab.</p>
  </div>;
}

function Checks({ checks, catalog }: { checks: ResearchChecks; catalog: Strategy[] }) {
  return <section className={base.tableCard} aria-labelledby="research-checks">
    <div className={styles.cardHead}><h2 id="research-checks">Reliability checks on listed algos</h2><small>{checks.basis}</small></div>
    <div className={base.tableScroll}><table className={`${base.table} ${styles.checks}`}>
      <thead><tr><th>Algo</th><th>Rules passed</th><th className={base.num}>Profit after costs</th><th className={base.num}>Per year</th><th>Worst drawdown</th><th className={base.num}>Beat random entries, unseen</th><th>Main finding</th></tr></thead>
      <tbody>{checks.rows.map(row => <CheckLine key={row.id} row={row} strategy={catalog.find(item => item.id === row.id)} />)}</tbody>
    </table></div>
    <p className={styles.cardNote}>{checks.note}</p>
  </section>;
}

function CheckLine({ row, strategy }: { row: CheckRow; strategy: Strategy | undefined }) {
  const name = <td><div className={base.algoCell}><AlgoIcon version={strategy?.version || row.tag || '?'} /><b>{strategy?.name || row.name || row.id}</b></div></td>;
  if (row.passed == null || row.rules == null) return <tr className={styles.pending}>{name}<td>Not checked yet</td><td className={base.num}>—</td><td className={base.num}>—</td><td>—</td><td className={base.num}>—</td><td className={styles.finding}>{row.finding}</td></tr>;
  const over = (row.drawdown ?? 0) > DRAWDOWN_LIMIT;
  return <tr>
    {name}
    <td>{row.passed} of {row.rules}<span className={styles.pips} aria-hidden="true">{Array.from({ length: row.rules }, (_, index) => <i key={index} className={index < row.passed! ? styles.pipOn : ''} />)}</span></td>
    <td className={base.num}>{row.profit == null ? '—' : `₹${(row.profit / 100_000).toFixed(2)} lakh`}</td>
    <td className={base.num}>{row.per_year == null ? '—' : `${row.per_year.toFixed(1)}%`}</td>
    <td>{row.drawdown == null ? '—' : <span className={styles.meter}><i aria-hidden="true"><i className={over ? styles.meterOver : ''} style={{ width: `${Math.min(100, row.drawdown * 2)}%` }} /></i><span className={over ? styles.amber : ''}>{row.drawdown.toFixed(1)}%</span></span>}</td>
    <td className={base.num}>{row.placebo == null ? '—' : `${row.placebo}%`}</td>
    <td className={styles.finding}>{row.finding}{row.checked ? <small>Checked {row.checked}</small> : null}</td>
  </tr>;
}

const signed = (value: number) => `${value > 0 ? '+' : value < 0 ? '−' : ''}${Math.abs(value).toFixed(1)}%`;
const COSTS: { key: 'gross' | 'mid' | 'high'; label: string }[] = [{ key: 'gross', label: 'No costs' }, { key: 'mid', label: '2 points' }, { key: 'high', label: '4.6 points' }];

/** Return per year at three cost levels, as bars from a centre line: right for a gain, left for a loss. */
function CostChart({ costs }: { costs: CostRow[] }) {
  const scale = Math.max(1, ...costs.flatMap(row => COSTS.map(cost => Math.abs(row[cost.key])))) * 1.05;
  const label = costs.map(row => `${row.name}: ${COSTS.map(cost => `${signed(row[cost.key])} at ${cost.label.toLowerCase()}`).join(', ')}`).join('. ');
  return <div className={styles.chart} role="img" aria-label={`Return per year as trading costs rise. ${label}.`}>
    {costs.map(row => <div key={row.name} className={styles.group}>
      <div className={styles.groupHead}><b>{row.name}</b><small>{row.note} · {row.edge_points.toFixed(1)} pts a trade</small></div>
      {COSTS.map(cost => {
        const value = row[cost.key], width = Math.abs(value) / scale * 50;
        return <div key={cost.key} className={styles.barRow}>
          <span>{cost.label}</span>
          <span className={styles.track}><i style={{ left: `${value >= 0 ? 50 : 50 - width}%`, width: `${width}%` }} className={row.listed ? styles.barListed : value >= 0 ? styles.barUp : styles.barDown} /></span>
          <span className={row.listed ? styles.valueListed : tone(value)}>{signed(value)}</span>
        </div>;
      })}
    </div>)}
    <div className={styles.legend}><span><i className={styles.barUp} />This research, gain</span><span><i className={styles.barDown} />This research, loss</span><span><i className={styles.barListed} />Listed algo, for comparison</span></div>
  </div>;
}

function ResearchCard({ note }: { note: ResearchNote }) {
  return <article className={styles.note} aria-labelledby={`research-${note.id}`}>
    <header className={styles.head}>
      <AlgoIcon version={note.tag} size="lg" />
      <div className={styles.title}>
        <h3 id={`research-${note.id}`}>{note.name}</h3>
        <small>{note.source} · researched {note.researched}</small>
      </div>
      <span className={styles.tag}>Not listed</span>
    </header>
    <div className={styles.verdict}>
      <AlertTriangle size={18} aria-hidden="true" />
      <div><b>{note.verdict}</b><p>{note.summary}</p></div>
    </div>
    <dl className={styles.stats}>{note.stats.map(stat => <div key={stat.label}>
      <dt>{stat.label}</dt>
      <dd className={stat.tone === 'up' ? base.green : stat.tone === 'down' ? base.red : ''}>{stat.value}</dd>
    </div>)}</dl>
    <div className={styles.columns}>
      <section aria-label="Return per year as trading costs rise">
        <h4>Return per year as trading costs rise</h4>
        <p className={styles.hint}>Bars grow right for a gain and left for a loss. 4.6 points is what real fills on a similar algo lost.</p>
        <CostChart costs={note.costs} />
      </section>
      <section aria-label="What we found">
        <h4>What we found</h4>
        <ul className={styles.findings}>{note.findings.map(text => <li key={text}>{text}</li>)}</ul>
        <p className={styles.code}>Code: <code>{note.code}</code></p>
      </section>
    </div>
  </article>;
}
