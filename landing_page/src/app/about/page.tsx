import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "About TradeBud",
  description: "TradeBud is an independent, free-forever trading journal built to help traders review decisions, understand performance, and improve their process.",
  alternates: { canonical: "/about" },
  openGraph: { type: "website", title: "About TradeBud", description: "Why TradeBud exists and what it is designed to do.", url: "https://tradebud.xyz/about", siteName: "TradeBud", locale: "en_US", images: [{ url: "https://tradebud.xyz/og-demo.png", width: 1200, height: 630, alt: "About TradeBud" }] },
  twitter: { card: "summary_large_image", title: "About TradeBud", description: "Why TradeBud exists and what it is designed to do.", images: ["https://tradebud.xyz/og-demo.png"] },
};

export default function AboutPage() {
  return (
    <main id="main-content" className="legal-page">
      <header className="legal-header">
        <Link href="/" className="legal-brand"><span aria-hidden="true">TB</span>TradeBud</Link>
        <nav aria-label="About navigation"><Link href="/free-trading-journal">Product guide</Link><Link href="/tools">Free tools</Link><Link href="/privacy">Privacy</Link><a href="https://app.tradebud.xyz">Open app</a></nav>
      </header>

      <article className="about-article">
        <div className="about-hero"><p>ABOUT TRADEBUD</p><h1>Better trading starts with an honest record.</h1><span>TradeBud is an independent trading journal built around a simple idea: your history is useful only when it helps you make better decisions.</span></div>
        <section><h2>Why TradeBud exists</h2><p>Broker statements show transactions. Spreadsheets store numbers. Neither necessarily preserves the full decision. TradeBud brings trade details, risk, notes, fees, calendar context, and performance analytics together so traders can review both process and outcome.</p></section>
        <section><h2>What TradeBud is</h2><p>TradeBud is a web-based journal and analytics tool for self-directed traders. It records information you enter and calculates performance indicators from that information. It is not a broker, exchange, signal provider, or financial adviser.</p></section>
        <section><h2>Free forever</h2><p>The core TradeBud journal is completely free forever. Unlimited trade entries, journal notes, calendar views, fee-aware calculations, and core performance analytics do not require a subscription or credit card.</p></section>
        <section><h2>How we approach the product</h2><ul><li><strong>Clarity over noise:</strong> metrics should help answer a decision, not fill a screen.</li><li><strong>Honest inputs:</strong> estimates are clearly dependent on the data and fee settings a trader provides.</li><li><strong>Process over prediction:</strong> TradeBud helps review decisions; it does not promise outcomes.</li><li><strong>Accessible by default:</strong> the core journal remains free to use.</li></ul></section>
        <section><h2>Explore the reference layer</h2><p>Use the <Link href="/tools">free calculators</Link> for transparent arithmetic, the <Link href="/glossary">performance glossary</Link> for definitions, and the <Link href="/methodology">methodology page</Link> for the assumptions behind TradeBud&apos;s metrics.</p></section>
        <section><h2>Contact</h2><p>Questions, support requests, and feedback are welcome at <a href="mailto:kavishshah30@gmail.com">kavishshah30@gmail.com</a>.</p></section>
      </article>

      <footer className="legal-footer"><span>© 2026 TradeBud</span><Link href="/">Home</Link><Link href="/privacy">Privacy</Link><Link href="/terms">Terms</Link></footer>
    </main>
  );
}
