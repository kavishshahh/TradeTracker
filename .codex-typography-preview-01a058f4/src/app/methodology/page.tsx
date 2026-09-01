import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Trading Metrics Methodology",
  description: "How TradeBud calculates P&L, fees, win rate, averages, expectancy, profit factor, equity curves, and monthly returns.",
  alternates: { canonical: "/methodology" },
  openGraph: { type: "article", title: "Trading Metrics Methodology | TradeBud", description: "Transparent definitions for the metrics TradeBud calculates from your journal.", url: "https://tradebud.xyz/methodology", siteName: "TradeBud", locale: "en_US", images: [{ url: "https://tradebud.xyz/og-demo.png", width: 1200, height: 630, alt: "TradeBud trading metrics methodology" }] },
  twitter: { card: "summary_large_image", title: "Trading Metrics Methodology | TradeBud", description: "How TradeBud calculates core trading journal metrics.", images: ["https://tradebud.xyz/og-demo.png"] },
};

const structuredData = {
  "@context": "https://schema.org",
  "@graph": [
    { "@type": "TechArticle", headline: "Trading Metrics Methodology", description: metadata.description, url: "https://tradebud.xyz/methodology", dateModified: "2026-08-31", author: { "@type": "Organization", name: "TradeBud", url: "https://tradebud.xyz/about" }, publisher: { "@type": "Organization", name: "TradeBud", url: "https://tradebud.xyz" }, isAccessibleForFree: true },
    { "@type": "BreadcrumbList", itemListElement: [{ "@type": "ListItem", position: 1, name: "Home", item: "https://tradebud.xyz" }, { "@type": "ListItem", position: 2, name: "Methodology", item: "https://tradebud.xyz/methodology" }] },
  ],
};

export default function MethodologyPage() {
  return (
    <main id="main-content" className="legal-page">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData) }} />
      <header className="legal-header"><Link href="/" className="legal-brand"><span aria-hidden="true">TB</span>TradeBud</Link><nav aria-label="Methodology navigation"><Link href="/tools">Calculators</Link><Link href="/glossary">Glossary</Link><Link href="/blog">Guides</Link><a href="https://app.tradebud.xyz">Open app</a></nav></header>
      <article className="legal-article methodology-article">
        <div className="legal-title"><p>METHODOLOGY</p><h1>Numbers should come with their definitions.</h1><span>Last reviewed: 31 August 2026</span></div>
        <p className="legal-summary">This page documents the conventions used by the current TradeBud journal. It describes arithmetic performed on the fields a trader enters; it does not turn estimates into broker records or investment advice.</p>

        <section><h2>Scope and source data</h2><p>TradeBud currently models a simple long trade with a buy price, optional sell price, share quantity, entry date, optional exit date, status, notes, and a user fee configuration. Performance metrics use closed trades with both buy and sell prices. An open trade is not treated as a completed outcome.</p><p>For a closed trade, the dashboard uses the exit date when one is recorded for date-range views; otherwise it falls back to the entry date. A broker or exchange statement remains the authoritative source for execution, cash movements, taxes, and account balances.</p></section>

        <section><h2>Gross P&amp;L</h2><p>For the current long-only trade model, gross P&amp;L is calculated as:</p><p className="methodology-formula"><code>(sell price − buy price) × shares</code></p><p>A positive value is a gross winner, a negative value is a gross loser, and zero is a breakeven before fees. Short trades, contract multipliers, options premium, and multi-leg execution are not represented by this formula.</p></section>

        <section><h2>Fee-aware net P&amp;L</h2><p>When net view is selected, TradeBud subtracts the configured buy-side and sell-side fees from gross P&amp;L. Brokerage is the lesser of the transaction value multiplied by the brokerage percentage and the per-side brokerage cap. Exchange charges and IFSCA turnover fees are percentage-based on each side’s transaction value. The configured platform fee is applied once to the buy and once to the sell.</p><p className="methodology-formula"><code>net P&amp;L = gross P&amp;L − buy fees − sell fees</code></p><p>Configured withdrawal, annual maintenance, account-opening, tracking, and profile-verification amounts are account-level settings and are not allocated to individual trade P&amp;L in the current dashboard. Do not describe a result as “after all costs” unless those costs have been included separately.</p></section>

        <section><h2>Win rate, averages, and breakevens</h2><p>TradeBud classifies each closed trade using the selected gross or net result. Values above zero are wins, values below zero are losses, and exactly zero is a breakeven. Win rate is winning trades divided by all closed trades, so breakevens remain in the denominator.</p><p>Average win is total winning value divided by the number of winning trades. Average loss is the absolute total losing value divided by the number of losing trades. If a category has no trades, its average is shown as zero in the app. Averages are sample summaries and can be distorted by outliers.</p></section>

        <section><h2>Expectancy</h2><p>Trade expectancy is the average result per closed trade. TradeBud calculates it as total selected P&amp;L divided by all closed trades. This is equivalent to the weighted form:</p><p className="methodology-formula"><code>(win probability × average win) − (loss probability × average loss)</code></p><p>Because the denominator includes breakevens, win and loss probabilities may sum to less than 100%. The result is descriptive of the selected sample; it is not a forecast.</p></section>

        <section><h2>Profit factor</h2><p>Profit factor is the selected gross or net winning value divided by the absolute selected losing value:</p><p className="methodology-formula"><code>profit factor = total winning value ÷ absolute total losing value</code></p><p>The ratio is undefined when there are no wins or losses and unbounded when there are positive wins but no losses. The public calculator labels those cases explicitly. When comparing a dashboard export with a calculator, use the same fee view and sample.</p></section>

        <section><h2>Equity curves and drawdown</h2><p>The trading P&amp;L curve orders closed trades chronologically and starts at zero cumulative selected P&amp;L. The account equity curve uses the manual monthly start/end balances recorded in the monthly-returns feature and adds current-month trade P&amp;L where available. Deposits, withdrawals, and a complete daily balance history are not inferred.</p><p>Maximum drawdown is available as a public calculator for a chronological positive equity series. It finds the largest observed decline from a prior peak to a later trough and reports both amount and percentage.</p></section>

        <section><h2>Monthly returns</h2><p>Monthly returns are user-entered records containing a starting capital, optional closing capital, and optional percentage and dollar return fields. The feature displays the values supplied by the user. A linked series should be compounded from period growth factors rather than averaged when a total multi-period return is needed; external cash flows must be handled separately.</p></section>

        <section><h2>What TradeBud does not calculate today</h2><p>The current product does not provide a validated short/long direction field, strategy or setup attribution, forex pip conversion, futures contract multipliers, options legs, Sortino or Calmar ratios, risk of ruin, tax accounting, or a broker-grade time-weighted return. Those features require additional data and separate validation before they should be presented as supported analytics.</p><p>TradeBud is a journal and analytics tool, not a broker, exchange, signal service, or financial adviser.</p></section>

        <section><h2>Use the definitions in a review</h2><p><Link href="/tools">Run a free calculator</Link>, <Link href="/glossary">look up a metric</Link>, or <Link href="/free-trading-journal">record the full history in the free journal</Link>. Keep the date range, fee convention, denominator, and sample size visible when you share a result.</p></section>
        <aside className="tool-disclaimer"><strong>Educational information only.</strong> TradeBud calculations depend on the data and settings entered by a user and may differ from official broker, exchange, tax, or accounting records.</aside>
      </article>
      <footer className="legal-footer"><span>© 2026 TradeBud</span><Link href="/tools">Tools</Link><Link href="/glossary">Glossary</Link><Link href="/about">About</Link><Link href="/privacy">Privacy</Link><Link href="/terms">Terms</Link></footer>
    </main>
  );
}
