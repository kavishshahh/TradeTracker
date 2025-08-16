import Journal from '@/components/Journal';
import Layout from '@/components/Layout';
import ProtectedRoute from '@/components/ProtectedRoute';

export default function JournalPage() {
  return (
    <ProtectedRoute>
      <Layout>
        <Journal />
      </Layout>
    </ProtectedRoute>
  );
}
