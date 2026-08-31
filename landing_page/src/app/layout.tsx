import type { Metadata, Viewport } from "next";
import PublicAnalytics from "@/components/PublicAnalytics";
import "./globals.css";

const siteUrl = "https://tradebud.xyz";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  icons: {
    icon: [{ url: "/tradebud-icon.svg", type: "image/svg+xml" }],
    shortcut: "/favicon.ico",
  },
  applicationName: "TradeBud",
  title: {
    default: "TradeBud — Trading Journal & Performance Analytics",
    template: "%s | TradeBud",
  },
  description: "A free trading journal for recording decisions, reviewing fee-aware performance, and finding useful patterns in your history.",
  authors: [{ name: "TradeBud", url: siteUrl }],
  creator: "TradeBud",
  publisher: "TradeBud",
  category: "Finance",
  referrer: "origin-when-cross-origin",
  alternates: { canonical: "/", types: { "application/rss+xml": "https://tradebud.xyz/feed.xml" } },
  openGraph: {
    title: "TradeBud — Trading Journal & Performance Analytics",
    description: "Record decisions, review fee-aware performance, and find useful patterns in your trading history.",
    url: siteUrl,
    siteName: "TradeBud",
    type: "website",
    locale: "en_US",
    images: [{ url: "/og-demo.png", width: 1200, height: 630, alt: "TradeBud — illustrative trading journal dashboard preview." }],
  },
  twitter: {
    card: "summary_large_image",
    title: "TradeBud — Trading Journal & Performance Analytics",
    description: "Record decisions, review fee-aware performance, and find useful patterns in your trading history.",
    images: ["/og-demo.png"],
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
  ],
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="antialiased">
        <a className="skip-link" href="#main-content">Skip to content</a>
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData) }}
        />
        <PublicAnalytics />
        {children}
      </body>
    </html>
  );
}
