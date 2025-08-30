import type { Metadata } from "next";
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
  title: "TradeBud - Professional Trading Journal | Track Your Trading Journey",
  description: "Professional trading journal with comprehensive analytics and performance tracking. Document, analyze, and learn from every trade - completely free. Start tracking your trading journey today.",
  keywords: "trading journal, trading analytics, performance tracking, trade management, risk management, trading calendar, free trading tools",
  authors: [{ name: "Kavish Shah" }],
  openGraph: {
    title: "TradeBud - Professional Trading Journal",
    description: "Track your trading journey with comprehensive analytics and performance tracking. Completely free.",
    type: "website",
    locale: "en_US",
  },
  twitter: {
    card: "summary_large_image",
    title: "TradeBud - Professional Trading Journal",
    description: "Track your trading journey with comprehensive analytics and performance tracking. Completely free.",
  },
  robots: "index, follow",
  viewport: "width=device-width, initial-scale=1",
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
