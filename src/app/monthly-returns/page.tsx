import Layout from '@/components/Layout';
import MonthlyReturns from '@/components/MonthlyReturns';
import ProtectedRoute from '@/components/ProtectedRoute';

export default function MonthlyReturnsPage() {
  return (
    <ProtectedRoute>
      <Layout>
        <MonthlyReturns />
      </Layout>
    </ProtectedRoute>
  );
}
