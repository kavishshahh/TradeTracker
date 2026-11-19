'use client';

import { Clock, Lock } from 'lucide-react';
import { useState } from 'react';
import styles from './algos.module.css';
import type { RequestState } from './useAlgoAccess';

/** What the lab needs to know about the viewer: may they see trades, do they own the lab, and where their request stands. */
export type LabAccess = { allowed: boolean; owner: boolean; request: RequestState; requestAccess: () => Promise<void> };
export const openAccess: LabAccess = { allowed: true, owner: true, request: 'granted', requestAccess: async () => {} };

function useAsk(access: LabAccess) {
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const ask = async () => {
    setSending(true); setError('');
    try { await access.requestAccess(); } catch (err) { setError(err instanceof Error ? err.message : 'Could not send your request.'); } finally { setSending(false); }
  };
  return { ask, sending, error, pending: access.request === 'pending', denied: access.request === 'denied' };
}

/** Stands in for a trades section when the viewer has no access. Nothing about the trades is on it. */
export function AccessCard({ access, what = 'Past trades, open positions and simulated orders' }: { access: LabAccess; what?: string }) {
  const { ask, sending, error, pending, denied } = useAsk(access);
  return <div className={`${styles.card} ${styles.locked}`}>
    <span className={styles.lockIcon}>{pending ? <Clock size={22} /> : <Lock size={22} />}</span>
    <h2>{pending ? 'Your request is waiting' : denied ? 'Your request was not approved' : 'Shared by invitation'}</h2>
    <p>{pending ? 'The owner reviews requests by hand. Once approved, the trades appear here the next time you open this page.'
      : denied ? 'You can ask again if something has changed.'
      : `${what} are shared by invitation. Ask for access and the owner will review it.`}</p>
    {!pending && <button className={styles.followButton} onClick={() => void ask()} disabled={sending}>{sending ? 'Sending…' : denied ? 'Ask again' : 'Request access'}</button>}
    {error && <p className={styles.lockError}>{error}</p>}
  </div>;
}

/** One line under the section tabs so a viewer on the card grid knows what more there is and how to ask. */
export function AccessBanner({ access }: { access: LabAccess }) {
  const { ask, sending, error, pending, denied } = useAsk(access);
  return <div className={styles.accessBanner} role="status">
    <Lock size={14} />
    <span>Backtest results and live status are open to everyone. Past trades and positions are shared by invitation.{error ? ` ${error}` : ''}</span>
    {pending ? <em>Request pending</em> : <button onClick={() => void ask()} disabled={sending}>{sending ? 'Sending…' : denied ? 'Ask again' : 'Request access'}</button>}
  </div>;
}
