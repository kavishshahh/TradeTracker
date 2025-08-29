import Dashboard from '@/components/Dashboard';
import Layout from '@/components/Layout';
import ProtectedRoute from '@/components/ProtectedRoute';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Trading Dashboard',
  description: 'View your trading performance, analytics, and key metrics in one comprehensive dashboard. Track profits, losses, win rates, and portfolio growth.',
  openGraph: {
    title: 'Trading Dashboard - TradeBud',
    description: 'View your trading performance, analytics, and key metrics in one comprehensive dashboard.',
    url: '/',
  },
};

export default function Home() {
  return (
    <ProtectedRoute>
      <Layout>
        <Dashboard />
      </Layout>
    </ProtectedRoute>
  );
}
