import Layout from '@/components/Layout';
import ProtectedRoute from '@/components/ProtectedRoute';
import AlgoDashboard from '../../../frontend/AlgoDashboard';
import type { Metadata } from 'next';

export const metadata: Metadata = { title: 'Algo Lab', description: 'Explore strategies and follow paper trades with TradeBud.' };

export default function AlgosPage() {
  return <ProtectedRoute><Layout><AlgoDashboard /></Layout></ProtectedRoute>;
}
