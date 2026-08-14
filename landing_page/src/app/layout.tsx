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

export const metadata: Metadata = {
  metadataBase: new URL("https://tradebud.xyz"),
  title: "TradeBud — A clearer view of your trading",
  description: "Journal your trades, measure performance, account for fees, and turn your trading history into a process you can trust.",
  keywords: "trading journal, trading analytics, performance tracking, trade management, risk management, trading calendar, free trading tools",
  authors: [{ name: "Kavish Shah" }],
  openGraph: {
    title: "TradeBud — A clearer view of your trading",
    description: "Journal decisions, measure performance, and build a trading process you can trust.",
    type: "website",
    locale: "en_US",
    images: [{ url: "/og.png", width: 1736, height: 907, alt: "TradeBud — Your trading history should teach you something." }],
  },
  twitter: {
    card: "summary_large_image",
    title: "TradeBud — A clearer view of your trading",
    description: "Journal decisions, measure performance, and build a trading process you can trust.",
    images: ["/og.png"],
  },
  robots: "index, follow",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        {children}
      </body>
    </html>
  );
}
