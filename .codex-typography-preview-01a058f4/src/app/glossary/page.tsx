import Link from "next/link";
import type { Metadata } from "next";
import { glossary } from "@/content/glossary";

export const metadata: Metadata = {
  title: "Trading Performance Glossary",
  description: "Clear definitions, formulas, examples, and limitations for the trading performance metrics TradeBud helps you review.",
  alternates: { canonical: "/glossary" },
  openGraph: {
    type: "website",
    title: "Trading Performance Glossary | TradeBud",
    description: "Understand win rate, expectancy, profit factor, drawdown, payoff, and risk/reward.",
    url: "https://tradebud.xyz/glossary",
    siteName: "TradeBud",
    locale: "en_US",
    images: [{ url: "https://tradebud.xyz/og-demo.png", width: 1200, height: 630, alt: "TradeBud trading performance glossary" }],
  },
  twitter: { card: "summary_large_image", title: "Trading Performance Glossary | TradeBud", description: "Definitions and formulas for core trading metrics.", images: ["https://tradebud.xyz/og-demo.png"] },
};

export default function GlossaryPage() {
  const structuredData = {
    "@context": "https://schema.org",
    "@type": "CollectionPage",
    name: "Trading Performance Glossary",
    description: metadata.description,
    url: "https://tradebud.xyz/glossary",
    mainEntity: {
      "@type": "ItemList",
      itemListElement: glossary.map((entry, index) => ({ "@type": "ListItem", position: index + 1, name: entry.term, url: `https://tradebud.xyz/glossary/${entry.slug}` })),
    },
  };

  return (
    <main id="main-content" className="tools-page">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData) }} />
      <header className="legal-header"><Link href="/" className="legal-brand"><span aria-hidden="true">TB</span>TradeBud</Link><nav aria-label="Glossary navigation"><Link href="/tools">Free tools</Link><Link href="/blog">Guides</Link><Link href="/methodology">Methodology</Link><a href="https://app.tradebud.xyz">Open app</a></nav></header>
      <section className="tools-hero"><p>TRADING PERFORMANCE GLOSSARY</p><h1>Definitions you can use in a real review.</h1><span>Formulas, worked examples, and limitations for the metrics behind a trading journal. Each entry links to a free calculator and related guidance.</span></section>
      <section className="tools-grid" aria-label="Glossary entries">{glossary.map((entry) => <article className="tool-card" key={entry.slug}><p className="tool-card-label">GLOSSARY ENTRY</p><h2><Link href={`/glossary/${entry.slug}`}>{entry.term}</Link></h2><p>{entry.definition}</p><code>{entry.formula}</code><Link className="tool-card-link" href={`/glossary/${entry.slug}`}>Read definition <span aria-hidden="true">→</span></Link></article>)}</section>
      <section className="tools-note"><p>CALCULATE, THEN REVIEW</p><h2>Metrics are evidence, not verdicts.</h2><p>A number becomes useful when its denominator, cost convention, sample, and limitations are explicit. Use the glossary alongside the methodology and your complete journal history.</p><div><Link href="/tools">Explore free calculators <span aria-hidden="true">→</span></Link><Link href="/methodology">Read TradeBud&apos;s methodology <span aria-hidden="true">→</span></Link></div></section>
      <footer className="legal-footer"><span>© 2026 TradeBud</span><Link href="/tools">Tools</Link><Link href="/blog">Guides</Link><Link href="/about">About</Link><Link href="/privacy">Privacy</Link></footer>
    </main>
  );
}
