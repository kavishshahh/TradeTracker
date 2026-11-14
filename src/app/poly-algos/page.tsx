import Layout from '@/components/Layout';
import ProtectedRoute from '@/components/ProtectedRoute';
import PolyDashboard from '../../../polymarket/frontend/PolyDashboard';
import type { Metadata } from 'next';

// Private section: not indexed, and the page shows nothing unless the API grants access.
export const metadata: Metadata = { title: 'Polymarket Algos', robots: { index: false, follow: false } };

export default function PolyAlgosPage() {
  return <ProtectedRoute><Layout><PolyDashboard /></Layout></ProtectedRoute>;
}
