import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const siteUrl = "https://tradebud.xyz";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  applicationName: "TradeBud",
  title: {
    default: "TradeBud — Free Trading Journal and Performance Analytics",
    template: "%s | TradeBud",
  },
  description: "TradeBud is a completely free trading journal for recording trades, reviewing decisions, calculating fee-aware P&L, and analyzing performance. Free forever, with no credit card required.",
  keywords: [
    "free trading journal",
    "trading journal app",
    "trade tracker",
    "trading performance analytics",
    "trade diary",
    "trading calendar",
    "profit and loss tracker",
    "risk management journal",
  ],
  authors: [{ name: "TradeBud", url: siteUrl }],
  creator: "TradeBud",
  publisher: "TradeBud",
  category: "Finance",
  referrer: "origin-when-cross-origin",
  alternates: { canonical: "/", types: { "application/rss+xml": "https://tradebud.xyz/feed.xml" } },
  openGraph: {
    title: "TradeBud — Free Trading Journal and Performance Analytics",
    description: "Record every trade, review your decisions, and understand your performance. TradeBud is free forever.",
    url: siteUrl,
    siteName: "TradeBud",
    type: "website",
    locale: "en_US",
    images: [{ url: "/og.png", width: 1736, height: 907, alt: "TradeBud — Your trading history should teach you something." }],
  },
  twitter: {
    card: "summary_large_image",
    title: "TradeBud — Free Trading Journal",
    description: "Record trades, review decisions, and analyze performance. Completely free forever.",
    images: ["/og.png"],
  },
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      "max-image-preview": "large",
      "max-snippet": -1,
      "max-video-preview": -1,
    },
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#f4f1e9",
  colorScheme: "light",
};

const structuredData = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Organization",
      "@id": `${siteUrl}/#organization`,
      name: "TradeBud",
      url: siteUrl,
      email: "kavishshah30@gmail.com",
      description: "TradeBud builds a completely free trading journal for traders who want a clearer record of their decisions and performance.",
    },
    {
      "@type": "WebSite",
      "@id": `${siteUrl}/#website`,
      url: siteUrl,
      name: "TradeBud",
      description: "A free trading journal and performance analytics application.",
      publisher: { "@id": `${siteUrl}/#organization` },
      inLanguage: "en",
    },
    {
      "@type": "SoftwareApplication",
      "@id": `${siteUrl}/#software`,
      name: "TradeBud",
      alternateName: "TradeBud Trading Journal",
      url: siteUrl,
      applicationCategory: "FinanceApplication",
      applicationSubCategory: "Trading journal and performance analytics",
      operatingSystem: "Web browser",
      isAccessibleForFree: true,
      description: "A completely free trading journal for recording trades, reviewing trading decisions, calculating fee-aware profit and loss, and analyzing performance over time.",
      author: { "@id": `${siteUrl}/#organization` },
      offers: {
        "@type": "Offer",
        price: "0",
        priceCurrency: "USD",
        availability: "https://schema.org/InStock",
        url: "https://app.tradebud.xyz",
      },
      featureList: [
        "Unlimited trade entries",
        "Trading journal and notes",
        "Performance analytics",
        "Fee-aware net profit and loss",
        "Trading calendar",
        "Monthly returns tracking",
        "Position quantity calculator",
      ],
    },
  ],
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased`}>
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData) }}
        />
        {children}
      </body>
    </html>
  );
}
