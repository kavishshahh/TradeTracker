import CalendarView from '@/components/CalendarView';
import Layout from '@/components/Layout';
import ProtectedRoute from '@/components/ProtectedRoute';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Trading Calendar',
  description: 'View your trades in a calendar format. Track trading frequency, identify patterns, and analyze your trading activity over time.',
  openGraph: {
    title: 'Trading Calendar - TradeBud',
    description: 'View your trades in a calendar format and identify trading patterns.',
    url: '/calendar',
  },
};

export default function CalendarPage() {
  return (
    <ProtectedRoute>
      <Layout>
        <CalendarView />
      </Layout>
    </ProtectedRoute>
  );
}
