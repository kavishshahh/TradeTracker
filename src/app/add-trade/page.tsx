import ActiveTrades from '@/components/ActiveTrades';
import Layout from '@/components/Layout';
import ProtectedRoute from '@/components/ProtectedRoute';
import TradeForm from '@/components/TradeForm';

export default function AddTradePage() {
  return (
    <ProtectedRoute>
      <Layout>
        <div className="space-y-6">
          <TradeForm />
          <ActiveTrades />
        </div>
      </Layout>
    </ProtectedRoute>
  );
}
