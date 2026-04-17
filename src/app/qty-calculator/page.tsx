import Layout from '@/components/Layout';
import ProtectedRoute from '@/components/ProtectedRoute';
import QtyCalculator from '@/components/QtyCalculator';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Qty Calculator',
  description: 'Calculate live position quantity using stop-loss points and risk amount in USDT, INR, EUR, or SGD.',
  openGraph: {
    title: 'Qty Calculator - TradeBud',
    description: 'Live quantity calculator with stop-loss and risk-based sizing.',
    url: '/qty-calculator',
  },
};

export default function QtyCalculatorPage() {
  return (
    <ProtectedRoute>
      <Layout>
        <QtyCalculator />
      </Layout>
    </ProtectedRoute>
  );
}
