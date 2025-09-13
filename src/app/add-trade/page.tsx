

'use client';

import Layout from '@/components/Layout';
import LoadingSkeleton from '@/components/LoadingSkeleton';
import ProtectedRoute from '@/components/ProtectedRoute';
import dynamic from 'next/dynamic';

// Lazy load TradeForm to reduce initial bundle size
const TradeForm = dynamic(() => import('@/components/TradeForm'), {
  loading: () => <LoadingSkeleton />,
  ssr: false
});

export default function AddTradePage() {
  return (
    <ProtectedRoute>
      <Layout>
        <TradeForm />
      </Layout>
    </ProtectedRoute>
  );
}
