import Layout from '@/components/Layout';
import Profile from '@/components/Profile';
import ProtectedRoute from '@/components/ProtectedRoute';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Profile Settings',
  description: 'Manage your trading profile, account settings, and preferences. Update personal information and customize your trading journal experience.',
  openGraph: {
    title: 'Profile Settings - TradeBud',
    description: 'Manage your trading profile and account settings.',
    url: '/profile',
  },
};

export default function ProfilePage() {
  return (
    <ProtectedRoute>
      <Layout>
        <Profile />
      </Layout>
    </ProtectedRoute>
  );
}
