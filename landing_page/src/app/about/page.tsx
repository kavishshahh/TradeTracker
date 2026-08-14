import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "About TradeBud",
  description: "TradeBud is an independent, free-forever trading journal built to help traders review decisions, understand performance, and improve their process.",
  alternates: { canonical: "/about" },
  openGraph: { title: "About TradeBud", description: "Why TradeBud exists and what it is designed to do.", url: "/about" },
};

export default function AboutPage() {
  return (
    <main className="legal-page">
      <header className="legal-header">
        <a href="/" className="legal-brand"><span aria-hidden="true">TB</span>TradeBud</a>
        <nav aria-label="About navigation"><a href="/free-trading-journal">Product guide</a><a href="/privacy">Privacy</a><a href="https://app.tradebud.xyz">Open app</a></nav>
      </header>

      <article className="about-article">
        <div className="about-hero"><p>ABOUT TRADEBUD</p><h1>Better trading starts with an honest record.</h1><span>TradeBud is an independent trading journal built around a simple idea: your history is useful only when it helps you make better decisions.</span></div>
        <section><h2>Why TradeBud exists</h2><p>Broker statements show transactions. Spreadsheets store numbers. Neither necessarily preserves the full decision. TradeBud brings trade details, risk, notes, fees, calendar context, and performance analytics together so traders can review both process and outcome.</p></section>
        <section><h2>What TradeBud is</h2><p>TradeBud is a web-based journal and analytics tool for self-directed traders. It records information you enter and calculates performance indicators from that information. It is not a broker, exchange, signal provider, or financial adviser.</p></section>
        <section><h2>Free forever</h2><p>The core TradeBud journal is completely free forever. Unlimited trade entries, journal notes, calendar views, fee-aware calculations, and core performance analytics do not require a subscription or credit card.</p></section>
        <section><h2>How we approach the product</h2><ul><li><strong>Clarity over noise:</strong> metrics should help answer a decision, not fill a screen.</li><li><strong>Honest inputs:</strong> estimates are clearly dependent on the data and fee settings a trader provides.</li><li><strong>Process over prediction:</strong> TradeBud helps review decisions; it does not promise outcomes.</li><li><strong>Accessible by default:</strong> the core journal remains free to use.</li></ul></section>
        <section><h2>Contact</h2><p>Questions, support requests, and feedback are welcome at <a href="mailto:kavishshah30@gmail.com">kavishshah30@gmail.com</a>.</p></section>
      </article>

      <footer className="legal-footer"><span>© 2026 TradeBud</span><a href="/">Home</a><a href="/privacy">Privacy</a><a href="/terms">Terms</a></footer>
    </main>
  );
}
