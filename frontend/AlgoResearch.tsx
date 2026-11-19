'use client';

import { FlaskConical } from 'lucide-react';
import { useEffect, useState } from 'react';
import type { Research, ResearchNote } from './researchData';
import { AlgoIcon, EmptyRow, Return, tone } from './algoUi';
import base from './algos.module.css';
import styles from './algoResearch.module.css';

/** Algo Lab > Research (owner only): write-ups of strategies that were tested and not listed.
 *  `load` fetches them once per page load; the notes are never part of the page bundle. */
export default function AlgoResearch({ load }: { load: () => Promise<Research> }) {
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

  return <div className={styles.research}>
    <p className={styles.intro}><FlaskConical size={15} aria-hidden="true" />Strategies we built and tested but did not list. Each note says what was tried, what it earned and why it was left out. Only you can see this tab.</p>
    {research.notes.length ? research.notes.map(note => <ResearchCard key={note.id} note={note} />) : <div className={base.card}><EmptyRow>No research notes yet.</EmptyRow></div>}
    <p className={base.caption}>{research.method}</p>
  </div>;
}

function ResearchCard({ note }: { note: ResearchNote }) {
  return <article className={styles.note} aria-labelledby={`research-${note.id}`}>
    <header className={styles.head}>
      <AlgoIcon version={note.tag} size="lg" />
      <div className={styles.title}>
        <h2 id={`research-${note.id}`}>{note.name}</h2>
        <small>{note.source}<i />Researched {note.researched}</small>
      </div>
      <span className={styles.tag}>Not listed</span>
    </header>
    <p className={styles.verdict}>{note.verdict}</p>
    <p className={styles.summary}>{note.summary}</p>
    <dl className={styles.stats}>{note.stats.map(stat => <div key={stat.label}>
      <dt>{stat.label}</dt>
      <dd className={stat.tone === 'up' ? base.green : stat.tone === 'down' ? base.red : ''}>{stat.value}</dd>
    </div>)}</dl>
    <div className={styles.columns}>
      <section aria-label="Return per year after trading costs">
        <h3>Return per year after trading costs</h3>
        <div className={`${base.tableCard} ${styles.flat}`}><div className={base.tableScroll}><table className={base.table}>
          <thead><tr><th>Strategy</th><th className={base.num}>Profit per trade</th><th className={base.num}>No costs</th><th className={base.num}>2 points</th><th className={base.num}>4.6 points</th></tr></thead>
          <tbody>{note.costs.map(row => <tr key={row.name} className={row.listed ? styles.reference : ''}>
            <td className={styles.name}><b>{row.name}</b><small>{row.note}</small></td>
            <td className={base.num}>{row.edge_points.toFixed(1)} pts</td>
            {[row.gross, row.mid, row.high].map((value, index) => <td key={index} className={`${base.num} ${tone(value)}`}><Return value={value} /></td>)}
          </tr>)}</tbody>
        </table></div></div>
      </section>
      <section aria-label="What we found">
        <h3>What we found</h3>
        <ul className={styles.findings}>{note.findings.map(text => <li key={text}>{text}</li>)}</ul>
        <p className={styles.code}>Rules and reasoning: <code>{note.code}</code></p>
      </section>
    </div>
  </article>;
}
