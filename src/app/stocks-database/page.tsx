import StocksDatabase from '@/components/StocksDatabase';
import Layout from '@/components/Layout';
import ProtectedRoute from '@/components/ProtectedRoute';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Stocks Database',
  description: 'Organize and track your stock analysis with categorized TradingView charts. Create categories and store before/after trading charts for better decision making.',
  openGraph: {
    title: 'Stocks Database - TradeBud',
    description: 'Organize and track your stock analysis with categorized TradingView charts.',
    url: '/stocks-database',
  },
};

export default function StocksDatabasePage() {
  return (
    <ProtectedRoute>
      <Layout>
        <StocksDatabase />
      </Layout>
    </ProtectedRoute>
  );
}

