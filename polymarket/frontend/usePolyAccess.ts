'use client';

import { useAuth } from '@/contexts/AuthContext';
import { useEffect, useState } from 'react';

const apiBase = (process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');

/**
 * Whether the signed-in user may see the Polymarket section. The answer comes from the API,
 * which reads the allowed emails from Firestore (feature_access/polymarket_algos); nothing
 * about who is allowed lives in this code. null = not known yet; any failure = hidden.
 * The answer is kept for the browser session so navigation does not re-ask on every page.
 */
export function usePolyAccess(): boolean | null {
  const { currentUser } = useAuth();
  const [allowed, setAllowed] = useState<boolean | null>(null);

  useEffect(() => {
    if (!currentUser) { setAllowed(null); return; }
    const key = `poly_access:${currentUser.uid}`;
    try {
      const cached = window.sessionStorage.getItem(key);
      if (cached === '1') { setAllowed(true); return; }
    } catch { /* storage unavailable: ask the API */ }
    let cancelled = false;
    (async () => {
      let result = false;
      try {
        const token = await currentUser.getIdToken();
        const response = await fetch(`${apiBase}/poly/access`, { headers: { Authorization: `Bearer ${token}` }, cache: 'no-store' });
        if (response.ok) {
          result = (await response.json() as { allowed?: boolean }).allowed === true;
          // Only a grant is remembered. A denial is re-asked on each page load, so a later grant shows up.
          if (result) { try { window.sessionStorage.setItem(key, '1'); } catch { /* ignore */ } }
        }
      } catch { /* hidden on any failure */ }
      if (!cancelled) setAllowed(result);
    })();
    return () => { cancelled = true; };
  }, [currentUser]);

  return allowed;
}
