'use client';

import { useAuth } from '@/contexts/AuthContext';
import { FileText } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { loadCachedLedger, mergeRows, newestTime, saveCachedLedger } from './ledgerCache';
import PolyView from './PolyView';
import type { Feed, FeedReply, LedgerRow } from './polyData';
import styles from './poly.module.css';
import { usePolyAccess } from './usePolyAccess';

const apiBase = (process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');
const POLL_MS = 120_000;   // the worker saves each account every 10 minutes, and at once on a bet or settlement

/**
 * Data loading for the Polymarket page. Reads cost Firestore quota, so:
 *  - the account documents (/poly/paper) are polled every 2 minutes, only while the tab is visible. A poll asks
 *    only for accounts written since the previous reply and merges them in (the full set is several hundred KB);
 *    the first load and Refresh fetch everything;
 *  - the bet ledger (/poly/trades, one read per bet returned) is kept in the browser (ledgerCache), so a
 *    visit, Refresh or CSV export reads only bets placed since the newest cached one; the full ledger is
 *    read only without a cached copy (first visit on a device, or once the copy is a week old). Bets placed
 *    between loads arrive through the account documents, which carry the most recent ones.
 */
export default function PolyDashboard() {
  const { currentUser } = useAuth();
  const allowed = usePolyAccess();
  const [feed, setFeed] = useState<Feed | null>(null);
  const [ledger, setLedger] = useState<LedgerRow[] | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [denied, setDenied] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const held = useRef<{ feed: Feed; asOf: number } | null>(null);   // last full picture, for changed-only polls

  const get = useCallback(async <T,>(path: string, signal?: AbortSignal): Promise<T | null> => {
    const token = await currentUser!.getIdToken();
    const response = await fetch(`${apiBase}${path}`, { headers: { Authorization: `Bearer ${token}` }, signal, cache: 'no-store' });
    if (response.status === 404) { setDenied(true); return null; }
    if (!response.ok) throw new Error(response.status === 401 ? 'Your session has expired. Sign in again.' : 'Polymarket data is unavailable right now. Please retry.');
    return await response.json() as T;
  }, [currentUser]);

  /** Cached ledger topped up with bets at or after its newest one; the full ledger when nothing is cached. */
  const syncLedger = useCallback(async (signal?: AbortSignal): Promise<LedgerRow[] | null> => {
    const uid = currentUser!.uid;
    const cached = await loadCachedLedger(uid);
    const since = cached && cached.rows.length ? newestTime(cached.rows) : null;
    const fresh = await get<{ trades: LedgerRow[] }>(since == null ? '/poly/trades' : `/poly/trades?since=${since}`, signal);
    if (!fresh || signal?.aborted) return null;
    const rows = cached ? mergeRows(cached.rows, fresh.trades) : mergeRows([], fresh.trades);
    const now = Date.now();
    await saveCachedLedger(uid, { rows, savedAt: now, fullAt: cached ? cached.fullAt : now });
    return rows;
  }, [currentUser, get]);

  /** Account documents: only the changed ones when a previous full picture is held, merged into it. */
  const loadPaper = useCallback(async (full: boolean, signal?: AbortSignal): Promise<Feed | null> => {
    const prev = full ? null : held.current;
    const reply = await get<FeedReply>(prev ? `/poly/paper?since=${prev.asOf}` : '/poly/paper', signal);
    if (!reply) return null;
    let strategies = reply.strategies;
    if (reply.partial && prev) {
      const ids = reply.ids ?? Object.keys(prev.feed.strategies);
      if (ids.some(id => !reply.strategies[id] && !prev.feed.strategies[id])) return loadPaper(true, signal);   // cannot merge: fetch all
      strategies = Object.fromEntries(ids.map(id => [id, reply.strategies[id] ?? prev.feed.strategies[id]]));
    }
    const feed: Feed = { strategies, catalog: reply.catalog };
    held.current = reply.as_of != null ? { feed, asOf: reply.as_of } : null;   // no as_of: next poll fetches all
    return feed;
  }, [get]);

  const load = useCallback(async (withLedger: boolean, signal?: AbortSignal) => {
    if (!currentUser) return;
    setLoading(true);
    try {
      const [paper, trades] = await Promise.all([
        loadPaper(withLedger, signal),   // first load and Refresh: everything; polls: changes only
        withLedger ? syncLedger(signal) : Promise.resolve(null),
      ]);
      if (signal?.aborted) return;
      if (paper) setFeed(paper);
      if (trades) setLedger(trades);
      setNow(Date.now());
      setError('');
    } catch (err) {
      if (!signal?.aborted) setError(err instanceof Error ? err.message : 'Unable to load Polymarket data.');
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [currentUser, loadPaper, syncLedger]);

  useEffect(() => {
    if (allowed !== true) return;
    const controller = new AbortController();
    void load(true, controller.signal);
    const poll = window.setInterval(() => { if (document.visibilityState === 'visible') void load(false, controller.signal); }, POLL_MS);
    const clock = window.setInterval(() => setNow(Date.now()), 15_000);   // keeps "updated 20s ago" honest between polls
    const onVisible = () => { if (document.visibilityState === 'visible') void load(false, controller.signal); };
    document.addEventListener('visibilitychange', onVisible);
    return () => { controller.abort(); window.clearInterval(poll); window.clearInterval(clock); document.removeEventListener('visibilitychange', onVisible); };
  }, [allowed, load]);

  const exportCsv = useCallback(async () => {
    if (exporting) return;
    setExporting(true);
    try {
      // The export is the complete ledger, including bets placed under earlier versions of an algo's rules:
      // the cached copy plus anything placed since it (only the new bets are read).
      const synced = await syncLedger();
      if (synced) setLedger(synced);
      const rows = [...(synced ?? ledger ?? [])].sort((x, y) => x.t - y.t);
      const fields: (keyof LedgerRow)[] = ['ts', 'strategy', 'version', 'kind', 'question', 'outcome_name', 'shares', 'price', 'fee', 'cost', 'payout', 'pnl', 'reason', 'cid'];
      const cell = (v: unknown) => `"${String(v ?? '').replace(/"/g, '""')}"`;
      const csv = [fields.join(','), ...rows.map(r => fields.map(f => cell(r[f])).join(','))].join('\r\n');
      const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8;' }));
      const link = document.createElement('a');
      link.href = url; link.download = 'polymarket-paper-trades.csv'; link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not export trades.');
    } finally {
      setExporting(false);
    }
  }, [exporting, ledger, syncLedger]);

  // People without access see the same empty page as an unknown route.
  if (allowed === false || denied) return <section className={styles.lab}><div className={styles.card}><div className={styles.emptyRow}><FileText size={20} strokeWidth={1.4} />This page is not available.</div></div></section>;
  if (allowed === null) return <section className={styles.lab}><div className={styles.card}><div className={styles.emptyRow}><FileText size={20} strokeWidth={1.4} />Loading…</div></div></section>;

  return <PolyView feed={feed} ledger={ledger} loading={loading} error={error} now={now}
    onRefresh={() => void load(true)} onExport={() => void exportCsv()} exporting={exporting} />;
}
