import Login from '@/components/Login';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Login',
  description: 'Sign in to your TradeBud trading journal account. Access your trades, analytics, and performance tracking dashboard.',
  openGraph: {
    title: 'Login - TradeBud',
    description: 'Sign in to access your trading journal and performance analytics.',
    url: '/login',
  },
};

export default function LoginPage() {
  return <Login />;
}
