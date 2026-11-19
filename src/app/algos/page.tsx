import Layout from '@/components/Layout';
import ProtectedRoute from '@/components/ProtectedRoute';
import AlgoDashboard from '../../../frontend/AlgoDashboard';
import type { Metadata } from 'next';

// Not indexed: the trades sections open only to accounts the API grants access.
export const metadata: Metadata = { title: 'Algo Lab', description: 'Explore strategies and follow paper trades with TradeBud.', robots: { index: false, follow: false } };

export default function AlgosPage() {
  return <ProtectedRoute><Layout><AlgoDashboard /></Layout></ProtectedRoute>;
}
