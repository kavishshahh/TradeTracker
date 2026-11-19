'use client';

import { Check, Mail, RefreshCw, ShieldCheck, UserMinus, UserPlus, X } from 'lucide-react';
import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { toast } from 'react-toastify';
import type { useAlgoAccess } from './useAlgoAccess';

type Status = 'pending' | 'granted' | 'denied' | 'revoked';
type AccessRequest = { uid: string; email: string; status: Status; requested_at?: string | null; decided_at?: string | null };
type Admin = { owner: string; emails: string[]; requests: AccessRequest[] };

const when = (value: string | null | undefined) => value ? new Date(value).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—';
const badge: Record<Status, string> = {
  pending: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200',
  granted: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-200',
  denied: 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300',
  revoked: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200',
};
const small = 'inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-md border transition-colors disabled:opacity-50 disabled:cursor-not-allowed';
const grantButton = `${small} border-transparent text-white bg-blue-600 hover:bg-blue-700`;
const quietButton = `${small} border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700`;

/** Settings > Admin: who asked for Algo Lab, who has it, and the controls to change that. Rendered only for the owner. */
export default function AlgoAccessAdmin({ call }: { call: ReturnType<typeof useAlgoAccess>['call'] }) {
  const [admin, setAdmin] = useState<Admin | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const [email, setEmail] = useState('');

  const load = useCallback(async () => {
    setError('');
    try {
      const response = await call('/algos/access/admin');
      if (!response.ok) throw new Error(response.status === 404 ? 'Only the Algo Lab owner can manage access.' : 'Access requests could not be loaded.');
      setAdmin(await response.json() as Admin);
    } catch (err) { setError(err instanceof Error ? err.message : 'Access requests could not be loaded.'); }
  }, [call]);
  useEffect(() => { void load(); }, [load]);

  const send = async (key: string, path: string, body: object, done: string) => {
    setBusy(key);
    try {
      const response = await call(path, 'PUT', body);
      if (!response.ok) throw new Error((await response.json().catch(() => ({})) as { detail?: string }).detail || 'Could not update access.');
      toast.success(done);
      await load();
    } catch (err) { toast.error(err instanceof Error ? err.message : 'Could not update access.'); }
    finally { setBusy(null); }
  };
  const decide = (row: AccessRequest, allowed: boolean) => send(row.uid, `/algos/access/admin/requests/${encodeURIComponent(row.uid)}`, { allowed }, `${row.email} ${allowed ? 'can now open Algo Lab' : 'was declined'}`);
  const setListed = (address: string, allowed: boolean) => send(address, '/algos/access/admin/emails', { email: address, allowed }, `${address} ${allowed ? 'can now open Algo Lab' : 'no longer has access'}`);
  const add = (event: FormEvent) => { event.preventDefault(); const address = email.trim().toLowerCase(); if (address) void setListed(address, true).then(() => setEmail('')); };

  const pending = admin?.requests.filter(row => row.status === 'pending') ?? [];
  const settled = admin?.requests.filter(row => row.status !== 'pending') ?? [];
  const requested = new Set(admin?.requests.map(row => row.email));

  return (
    <div className="max-w-3xl mx-auto space-y-8">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-1 flex items-center"><ShieldCheck className="h-5 w-5 mr-2 text-blue-500" />Algo Lab access</h2>
          <p className="text-sm text-gray-600 dark:text-gray-400">Algo Lab is private. People who ask for it appear here; grant them access to let them see the algos and their paper trades. Only you ever see an algo’s rules.</p>
        </div>
        <button type="button" onClick={() => void load()} className={quietButton} aria-label="Reload access requests"><RefreshCw className="h-3.5 w-3.5" />Reload</button>
      </div>

      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
      {!admin && !error && <p className="text-sm text-gray-500 dark:text-gray-400">Loading…</p>}

      {admin && <>
        <section>
          <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-3">Requests waiting {pending.length ? <span className="ml-1 px-2 py-0.5 text-xs rounded-full bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200">{pending.length}</span> : null}</h3>
          {pending.length ? <ul className="divide-y divide-gray-200 dark:divide-gray-700 border border-gray-200 dark:border-gray-700 rounded-lg">
            {pending.map(row => <li key={row.uid} className="flex flex-wrap items-center gap-3 px-4 py-3">
              <Mail className="h-4 w-4 text-gray-400" />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-900 dark:text-white truncate">{row.email}</p>
                <p className="text-xs text-gray-500 dark:text-gray-400">Asked {when(row.requested_at)}</p>
              </div>
              <button type="button" className={grantButton} disabled={busy === row.uid} onClick={() => void decide(row, true)}><Check className="h-3.5 w-3.5" />Grant</button>
              <button type="button" className={quietButton} disabled={busy === row.uid} onClick={() => void decide(row, false)}><X className="h-3.5 w-3.5" />Decline</button>
            </li>)}
          </ul> : <p className="text-sm text-gray-500 dark:text-gray-400">No one is waiting.</p>}
        </section>

        <section>
          <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-3">People with access <span className="ml-1 text-xs font-normal text-gray-500 dark:text-gray-400">{admin.emails.length}</span></h3>
          <form onSubmit={add} className="flex gap-2 mb-3">
            <input type="email" value={email} onChange={event => setEmail(event.target.value)} placeholder="Add an email address" aria-label="Email address to grant access" className="flex-1 px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent dark:bg-gray-700 dark:text-white" />
            <button type="submit" className={grantButton} disabled={!email.trim() || busy === email.trim().toLowerCase()}><UserPlus className="h-3.5 w-3.5" />Grant</button>
          </form>
          <ul className="divide-y divide-gray-200 dark:divide-gray-700 border border-gray-200 dark:border-gray-700 rounded-lg">
            <li className="flex items-center gap-3 px-4 py-3">
              <ShieldCheck className="h-4 w-4 text-blue-500" />
              <p className="flex-1 text-sm font-medium text-gray-900 dark:text-white truncate">{admin.owner}</p>
              <span className="text-xs text-gray-500 dark:text-gray-400">Owner · sees everything</span>
            </li>
            {admin.emails.map(address => <li key={address} className="flex items-center gap-3 px-4 py-3">
              <Mail className="h-4 w-4 text-gray-400" />
              <p className="flex-1 text-sm text-gray-900 dark:text-white truncate">{address}</p>
              {!requested.has(address) && <span className="text-xs text-gray-500 dark:text-gray-400">Added by you</span>}
              <button type="button" className={quietButton} disabled={busy === address} onClick={() => void setListed(address, false)}><UserMinus className="h-3.5 w-3.5" />Revoke</button>
            </li>)}
            {!admin.emails.length && <li className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">Nobody else has access yet.</li>}
          </ul>
          <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">People with access see each algo’s performance, past trades and monthly returns, and only a basic About algo page.</p>
        </section>

        {settled.length > 0 && <section>
          <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-3">Earlier requests</h3>
          <ul className="divide-y divide-gray-200 dark:divide-gray-700 border border-gray-200 dark:border-gray-700 rounded-lg">
            {settled.map(row => <li key={row.uid} className="flex flex-wrap items-center gap-3 px-4 py-3">
              <div className="flex-1 min-w-0">
                <p className="text-sm text-gray-900 dark:text-white truncate">{row.email}</p>
                <p className="text-xs text-gray-500 dark:text-gray-400">Asked {when(row.requested_at)}{row.decided_at ? ` · decided ${when(row.decided_at)}` : ''}</p>
              </div>
              <span className={`px-2 py-0.5 text-xs font-medium rounded-full capitalize ${badge[row.status]}`}>{row.status}</span>
              {row.status === 'granted'
                ? <button type="button" className={quietButton} disabled={busy === row.uid} onClick={() => void decide(row, false)}><UserMinus className="h-3.5 w-3.5" />Revoke</button>
                : <button type="button" className={grantButton} disabled={busy === row.uid} onClick={() => void decide(row, true)}><Check className="h-3.5 w-3.5" />Grant</button>}
            </li>)}
          </ul>
        </section>}
      </>}
    </div>
  );
}
