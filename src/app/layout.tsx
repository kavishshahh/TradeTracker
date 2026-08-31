import GoogleAnalytics from '@/components/GoogleAnalytics';
import StructuredData, {
    organizationStructuredData,
    softwareStructuredData,
    websiteStructuredData
} from '@/components/StructuredData';
import { AuthProvider } from '@/contexts/AuthContext';
import { ThemeProvider } from '@/contexts/ThemeContext';
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  icons: {
    icon: [{ url: '/tradebud-icon.svg', type: 'image/svg+xml' }],
    shortcut: '/favicon.ico',
  },
  title: {
    template: '%s | TradeBud',
    default: 'TradeBud — A clearer view of your trading'
  },
  description: "Journal your trades, measure performance, account for fees, and turn your trading history into a process you can trust.",
  keywords: ["trading journal", "trading analytics", "trade tracker", "trading performance", "stock trading", "forex trading", "investment tracking", "trading dashboard", "portfolio analysis", "trading statistics"],
  authors: [{ name: "TradeBud" }],
  creator: "TradeBud",
  publisher: "TradeBud",
  formatDetection: {
    email: false,
    address: false,
    telephone: false,
  },
  metadataBase: new URL(process.env.NEXT_PUBLIC_BASE_URL || 'https://app.tradebud.xyz'),
  robots: {
    index: false,
    follow: false,
    noarchive: true,
    nosnippet: true,
  },
  openGraph: {
    title: 'TradeBud — A clearer view of your trading',
    description: 'Journal decisions, measure performance, and build a trading process you can trust.',
    url: '/',
    siteName: 'TradeBud',
    locale: 'en_US',
    type: 'website',
    images: [
      {
        url: '/og-image.png',
        width: 1736,
        height: 907,
        alt: 'TradeBud Trading Journal Dashboard',
      },
    ],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'TradeBud — A clearer view of your trading',
    description: 'Journal decisions, measure performance, and build a trading process you can trust.',
    images: ['/og-image.png'],
  },
  verification: {
    google: process.env.NEXT_PUBLIC_GOOGLE_VERIFICATION,
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <head>
        <StructuredData data={websiteStructuredData} />
        <StructuredData data={organizationStructuredData} />
        <StructuredData data={softwareStructuredData} />
      </head>
      <body className="antialiased">
        <ThemeProvider>
          <AuthProvider>
            {children}
          </AuthProvider>
        </ThemeProvider>
        {process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID && (
          <GoogleAnalytics GA_MEASUREMENT_ID={process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID} />
        )}
      </body>
    </html>
  );
}
