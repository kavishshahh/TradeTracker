import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Free Trading Journal — Track, Review, and Improve Every Trade",
  description: "Use TradeBud as a free trading journal to record trades, calculate fee-aware P&L, review performance, and identify patterns. Free forever with no credit card.",
  keywords: ["free trading journal", "free trade tracker", "trading diary", "trading journal analytics", "fee aware P&L"],
  alternates: { canonical: "/free-trading-journal" },
  openGraph: {
    title: "Free Trading Journal | TradeBud",
    description: "A practical trading journal with analytics, notes, fee-aware P&L, and unlimited trade entries—free forever.",
    url: "/free-trading-journal",
  },
};

const faq = [
  ["Is TradeBud really free forever?", "Yes. TradeBud’s core journal, trade tracking, calendar, and performance analytics are free forever. There is no trial clock or credit card requirement."],
  ["What can I record in the trading journal?", "You can record dates, ticker symbols, entry and exit prices, quantities, open or closed status, risk, notes, account balances, and configurable trading fees."],
  ["Does TradeBud place trades or connect to my broker?", "No. TradeBud is an independent journal and analytics tool. It does not execute trades, hold funds, provide brokerage services, or recommend securities."],
  ["How does TradeBud calculate performance?", "TradeBud uses the trade data and fee settings you enter to calculate metrics such as net P&L, win rate, profit factor, expectancy, average win and loss, and equity curves."],
  ["Who is TradeBud for?", "TradeBud is for self-directed traders who want a structured record of their process. It can be used for stocks and other instruments that can be recorded by symbol, price, and quantity."],
];

export default function FreeTradingJournalPage() {
  const structuredData = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: faq.map(([name, text]) => ({
      "@type": "Question",
      name,
      acceptedAnswer: { "@type": "Answer", text },
    })),
  };

  return (
    <main className="guide-page">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData) }} />
      <header className="legal-header">
        <a href="/" className="legal-brand"><span aria-hidden="true">TB</span>TradeBud</a>
        <nav aria-label="Product navigation"><a href="/#features">Features</a><a href="/about">About</a><a href="https://app.tradebud.xyz">Open app</a></nav>
      </header>

      <article className="guide-article">
        <div className="guide-hero">
          <p>FREE TRADING JOURNAL</p>
          <h1>A trading record you can actually learn from.</h1>
          <span>TradeBud keeps your trades, reasoning, costs, and performance in one place. It is completely free forever—no credit card and no trial clock.</span>
          <div><a href="https://app.tradebud.xyz">Start your free journal</a><a href="#how-it-works">See how it works</a></div>
        </div>

        <section className="guide-section" id="how-it-works"><div><p>THE PURPOSE</p><h2>What is a trading journal?</h2></div><div><p>A trading journal is a structured record of the decisions behind your trades and the results that followed. A useful journal goes beyond recording profit or loss: it preserves the setup, position size, risk, execution, costs, and notes needed to evaluate whether your process was sound.</p><p>TradeBud turns those records into performance metrics and calendar views so you can distinguish repeatable behavior from isolated outcomes.</p></div></section>

        <section className="guide-section"><div><p>WHAT YOU CAN MEASURE</p><h2>Useful metrics, without spreadsheet upkeep.</h2></div><div className="guide-facts">
          <div><strong>Net P&amp;L</strong><span>Estimated results after the fee settings you configure.</span></div>
          <div><strong>Win rate</strong><span>The share of closed trades that finished profitably.</span></div>
          <div><strong>Profit factor</strong><span>Gross winning value divided by gross losing value.</span></div>
          <div><strong>Expectancy</strong><span>The average expected result across your recorded trades.</span></div>
          <div><strong>Equity curves</strong><span>A chronological view of cumulative performance.</span></div>
          <div><strong>Monthly returns</strong><span>Period-by-period results for longer-term review.</span></div>
        </div></section>

        <section className="guide-section"><div><p>A PRACTICAL ROUTINE</p><h2>How to use TradeBud.</h2></div><ol className="guide-steps">
          <li><span>01</span><div><strong>Record the trade</strong><p>Add the instrument, date, prices, quantity, risk, and status.</p></div></li>
          <li><span>02</span><div><strong>Keep the reasoning</strong><p>Write down the setup, expectation, execution notes, and lessons.</p></div></li>
          <li><span>03</span><div><strong>Review the evidence</strong><p>Use analytics, calendar, and journal views to find patterns.</p></div></li>
          <li><span>04</span><div><strong>Refine the process</strong><p>Turn consistent evidence into rules for future decisions.</p></div></li>
        </ol></section>

        <section className="guide-section guide-faq"><div><p>COMMON QUESTIONS</p><h2>Free trading journal FAQ.</h2></div><div>{faq.map(([question, answer]) => <details key={question}><summary>{question}</summary><p>{answer}</p></details>)}</div></section>

        <section className="guide-cta"><p>KEEP THE RECORD. LEARN FROM IT.</p><h2>Start with your next trade.</h2><a href="https://app.tradebud.xyz">Create your free journal</a><span>Free forever. No credit card required.</span></section>
      </article>

      <footer className="legal-footer"><span>© 2026 TradeBud</span><a href="/about">About</a><a href="/privacy">Privacy</a><a href="/terms">Terms</a></footer>
    </main>
  );
}
