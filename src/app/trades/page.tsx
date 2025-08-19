import Layout from '@/components/Layout';
import ProtectedRoute from '@/components/ProtectedRoute';
import TradesView from '@/components/TradesView';

export default function TradesPage() {
  return (
    <ProtectedRoute>
      <Layout>
        <TradesView />
      </Layout>
    </ProtectedRoute>
  );
}
