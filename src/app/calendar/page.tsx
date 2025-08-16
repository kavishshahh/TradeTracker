import CalendarView from '@/components/CalendarView';
import Layout from '@/components/Layout';
import ProtectedRoute from '@/components/ProtectedRoute';

export default function CalendarPage() {
  return (
    <ProtectedRoute>
      <Layout>
        <CalendarView />
      </Layout>
    </ProtectedRoute>
  );
}
