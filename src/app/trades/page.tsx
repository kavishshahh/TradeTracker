import Layout from '@/components/Layout';
import ProtectedRoute from '@/components/ProtectedRoute';
import TradesView from '@/components/TradesView';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Trade History',
  description: 'View and analyze your complete trading history. Filter, sort, and analyze all your trades with detailed performance metrics and trade outcomes.',
  openGraph: {
    title: 'Trade History - TradeBud',
    description: 'View and analyze your complete trading history with detailed performance metrics.',
    url: '/trades',
  },
};

export default function TradesPage() {
  return (
    <ProtectedRoute>
      <Layout>
        <TradesView />
      </Layout>
    </ProtectedRoute>
  );
}
