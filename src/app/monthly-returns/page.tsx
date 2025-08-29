import Layout from '@/components/Layout';
import MonthlyReturns from '@/components/MonthlyReturns';
import ProtectedRoute from '@/components/ProtectedRoute';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Monthly Returns',
  description: 'Analyze your monthly trading performance and returns. Track profit and loss trends, compare monthly results, and identify seasonal patterns.',
  openGraph: {
    title: 'Monthly Returns - TradeBud',
    description: 'Analyze your monthly trading performance and returns over time.',
    url: '/monthly-returns',
  },
};

export default function MonthlyReturnsPage() {
  return (
    <ProtectedRoute>
      <Layout>
        <MonthlyReturns />
      </Layout>
    </ProtectedRoute>
  );
}
