import Journal from '@/components/Journal';
import Layout from '@/components/Layout';
import ProtectedRoute from '@/components/ProtectedRoute';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Trading Journal',
  description: 'Keep detailed notes and reflections on your trading journey. Document strategies, lessons learned, and market insights to improve your trading performance.',
  openGraph: {
    title: 'Trading Journal - TradeBud',
    description: 'Keep detailed notes and reflections on your trading journey to improve performance.',
    url: '/journal',
  },
};

export default function JournalPage() {
  return (
    <ProtectedRoute>
      <Layout>
        <Journal />
      </Layout>
    </ProtectedRoute>
  );
}
