import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Add New Trade',
  description: 'Record new trades and manage active positions. Input trade details, set stop losses, take profits, and track your current market positions.',
  openGraph: {
    title: 'Add New Trade - TradeBud',
    description: 'Record new trades and manage active positions in your trading journal.',
    url: '/add-trade',
  },
};

export default function AddTradeLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
