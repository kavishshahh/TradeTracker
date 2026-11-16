// Browser-side copy of the Polymarket paper ledger, so a visit or Refresh reads only bets placed since
// the last load instead of the whole append-only ledger (one Firestore read per bet).
//
// Stored in IndexedDB per signed-in user; a module-level copy also survives in-app navigation.
// The copy expires after MAX_AGE_MS, after which the next load reads the full ledger again, so a
// server-side change to old rows is picked up within a week. Any storage failure just means a full read.
import type { LedgerRow } from './polyData';

const DB = 'tradebud_poly';
const STORE = 'ledger';
const MAX_AGE_MS = 7 * 24 * 60 * 60_000;

type Entry = { rows: LedgerRow[]; savedAt: number; fullAt: number };
const memory = new Map<string, Entry>();

function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB, 1);
    request.onupgradeneeded = () => request.result.createObjectStore(STORE);
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function idb<T>(mode: IDBTransactionMode, run: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const db = await open();
  try {
    return await new Promise<T>((resolve, reject) => {
      const request = run(db.transaction(STORE, mode).objectStore(STORE));
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  } finally {
    db.close();
  }
}

/** Two algos can settle the same market in the same second, so the algo and the exact time are part of the key. */
export const rowKey = (r: LedgerRow) => `${r.strategy}:${r.kind}:${r.cid}:${r.outcome}:${r.t}`;

/** Cached rows for this user, or null when there is no usable (or only an expired) copy. */
export async function loadCachedLedger(uid: string, now = Date.now()): Promise<Entry | null> {
  let entry = memory.get(uid) ?? null;
  if (!entry) {
    try { entry = (await idb<Entry | undefined>('readonly', s => s.get(uid))) ?? null; } catch { entry = null; }
  }
  if (!entry || !Array.isArray(entry.rows) || now - entry.fullAt > MAX_AGE_MS) return null;
  memory.set(uid, entry);
  return entry;
}

export async function saveCachedLedger(uid: string, entry: Entry): Promise<void> {
  memory.set(uid, entry);
  try { await idb('readwrite', s => s.put(entry, uid)); } catch { /* storage unavailable: memory copy only */ }
}

/** The `since` to request: the newest cached bet time. Rows at exactly that time are re-read and de-duplicated. */
export const newestTime = (rows: LedgerRow[]) => rows.reduce((max, r) => (r.t > max ? r.t : max), 0);

/** Cached rows plus newly fetched ones, de-duplicated and oldest first. */
export function mergeRows(cached: LedgerRow[], fresh: LedgerRow[]): LedgerRow[] {
  const rows = new Map<string, LedgerRow>();
  for (const r of cached) rows.set(rowKey(r), r);
  for (const r of fresh) rows.set(rowKey(r), r);
  return [...rows.values()].sort((a, b) => a.t - b.t);
}
