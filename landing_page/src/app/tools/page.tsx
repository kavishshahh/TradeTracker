import Link from "next/link";
import type { Metadata } from "next";
import { tools } from "@/content/tools";

export const metadata: Metadata = {
  title: "Free Trading Calculators",
  description:
    "Free, transparent trading calculators for expectancy, profit factor, win rate, risk/reward, position sizing, drawdown, and ROI.",
  alternates: { canonical: "/tools" },
  openGraph: {
    type: "website",
    title: "Free Trading Calculators | TradeBud",
    description:
      "Calculate core trading metrics with clear formulas, worked examples, and honest assumptions.",
    url: "https://tradebud.xyz/tools",
    siteName: "TradeBud",
    locale: "en_US",
    images: [{ url: "https://tradebud.xyz/og-demo.png", width: 1200, height: 630, alt: "TradeBud free trading calculators" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "Free Trading Calculators | TradeBud",
    description: "Transparent calculators for trading performance and risk review.",
    images: ["https://tradebud.xyz/og-demo.png"],
  },
};

export default function ToolsPage() {
  const structuredData = {
    "@context": "https://schema.org",
    "@type": "CollectionPage",
    name: "Free Trading Calculators",
    description: metadata.description,
    url: "https://tradebud.xyz/tools",
    isPartOf: { "@type": "WebSite", name: "TradeBud", url: "https://tradebud.xyz" },
    mainEntity: {
      "@type": "ItemList",
      itemListElement: tools.map((tool, index) => ({
        "@type": "ListItem",
        position: index + 1,
        name: tool.title,
        url: `https://tradebud.xyz/tools/${tool.slug}`,
      })),
    },
  };

  return (
    <main id="main-content" className="tools-page">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData) }} />
      <header className="legal-header">
        <Link href="/" className="legal-brand"><span aria-hidden="true">TB</span>TradeBud</Link>
        <nav aria-label="Tools navigation"><Link href="/free-trading-journal">Free journal</Link><Link href="/blog">Guides</Link><Link href="/methodology">Methodology</Link><a href="https://app.tradebud.xyz">Open app</a></nav>
      </header>

      <section className="tools-hero">
        <p>TRADEBUD TOOLS</p>
        <h1>Useful numbers, with the assumptions left visible.</h1>
        <span>Free calculators for reviewing trading performance and planning direct-price risk. No signup is required, and no result is a promise about the future.</span>
      </section>

      <section className="tools-grid" aria-label="Trading calculators">
        {tools.map((tool) => (
          <article className="tool-card" key={tool.slug}>
            <p className="tool-card-label">FREE CALCULATOR</p>
            <h2><Link href={`/tools/${tool.slug}`}>{tool.title}</Link></h2>
            <p>{tool.description}</p>
            <code>{tool.formula}</code>
            <Link className="tool-card-link" href={`/tools/${tool.slug}`}>Open calculator <span aria-hidden="true">→</span></Link>
          </article>
        ))}
      </section>

      <section className="tools-note">
        <p>USE THE NUMBERS IN CONTEXT</p>
        <h2>A calculator is a review aid, not a trading signal.</h2>
        <p>Inputs, fees, execution, sample size, cash flows, and market conditions all affect the meaning of a result. Read the methodology and related guides before comparing periods or changing risk.</p>
        <div><Link href="/methodology">How TradeBud calculates metrics <span aria-hidden="true">→</span></Link><Link href="/free-trading-journal">Record the full history in TradeBud <span aria-hidden="true">→</span></Link></div>
      </section>

      <footer className="legal-footer"><span>© 2026 TradeBud</span><Link href="/about">About</Link><Link href="/blog">Guides</Link><Link href="/privacy">Privacy</Link><Link href="/terms">Terms</Link></footer>
    </main>
  );
}
