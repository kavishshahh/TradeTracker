import ActiveTrades from '@/components/ActiveTrades';
import Layout from '@/components/Layout';
import ProtectedRoute from '@/components/ProtectedRoute';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Active Trades',
  description: 'View and manage your current open positions. Monitor active trades, set stop losses, take profits, and track your live market positions.',
  openGraph: {
    title: 'Active Trades - TradeBud',
    description: 'View and manage your current open positions with real-time tracking.',
    url: '/active-trades',
  },
};

export default function ActiveTradesPage() {
  return (
    <ProtectedRoute>
      <Layout>
        <div className="space-y-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Active Trades</h1>
            <p className="mt-1 text-sm text-gray-500">
              Manage your current open positions and track live market performance
            </p>
          </div>
          <ActiveTrades />
        </div>
      </Layout>
    </ProtectedRoute>
  );
}
