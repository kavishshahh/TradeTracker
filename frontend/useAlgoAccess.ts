'use client';

import { useAuth } from '@/contexts/AuthContext';
import { useCallback, useEffect, useState } from 'react';

const apiBase = (process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');

export type RequestState = 'none' | 'pending' | 'denied' | 'granted';
export type AlgoAccess = { loaded: boolean; allowed: boolean; owner: boolean; request: RequestState; error: string };
const unknown: AlgoAccess = { loaded: false, allowed: false, owner: false, request: 'none', error: '' };

/**
 * Whether the signed-in user may open Algo Lab, and whether they own it. The API decides from
 * Firestore (feature_access/algo_lab); nothing about who is allowed lives in this code. The
 * answer is asked once per page load, so a grant shows up on the next visit. Any failure
 * leaves the lab closed.
 */
export function useAlgoAccess() {
  const { currentUser } = useAuth();
  const [access, setAccess] = useState<AlgoAccess>(unknown);

  const call = useCallback(async (path: string, method = 'GET', body?: object) => {
    const token = await currentUser!.getIdToken();
    return fetch(`${apiBase}${path}`, { method, headers: { Authorization: `Bearer ${token}`, ...(body ? { 'Content-Type': 'application/json' } : {}) }, body: body ? JSON.stringify(body) : undefined, cache: 'no-store' });
  }, [currentUser]);

  const refresh = useCallback(async () => {
    if (!currentUser) { setAccess(unknown); return; }
    try {
      const response = await call('/algos/access');
      if (!response.ok) throw new Error(response.status === 401 ? 'Your session has expired. Sign in again.' : 'Could not check your access. Please retry.');
      const body = await response.json() as { allowed?: boolean; owner?: boolean; request?: RequestState };
      setAccess({ loaded: true, allowed: body.allowed === true, owner: body.owner === true, request: body.request || 'none', error: '' });
    } catch (err) {
      setAccess({ ...unknown, loaded: true, error: err instanceof Error ? err.message : 'Could not check your access.' });
    }
  }, [currentUser, call]);

  useEffect(() => { void refresh(); }, [refresh]);

  const requestAccess = useCallback(async () => {
    const response = await call('/algos/access/request', 'POST');
    if (!response.ok) throw new Error(response.status === 400 ? 'Verify your email address first, then ask again.' : 'Could not send your request. Please retry.');
    const body = await response.json() as { allowed?: boolean; request?: RequestState };
    setAccess(current => ({ ...current, allowed: body.allowed === true, request: body.request || 'pending' }));
  }, [call]);

  return { ...access, refresh, requestAccess, call };
}
