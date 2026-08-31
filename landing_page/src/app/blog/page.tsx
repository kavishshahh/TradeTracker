import type { Metadata } from "next";
import Link from "next/link";
import { articles, formatArticleDate } from "@/content/articles";

export const metadata: Metadata = {
  title: "Trading Journal Guides and Practical Reviews",
  description: "Clear, practical guides about trading journals, performance metrics, post-trade reviews, trading costs, and building a repeatable review process.",
  alternates: {
    canonical: "/blog",
    types: { "application/rss+xml": "https://tradebud.xyz/feed.xml" },
  },
  openGraph: {
    type: "website",
    title: "TradeBud Journal — Trading Journal Guides",
    description: "Practical explanations for recording trades, reviewing decisions, and understanding performance.",
    url: "/blog",
    siteName: "TradeBud",
    locale: "en_US",
    images: [{ url: "https://tradebud.xyz/og-demo.png", width: 1200, height: 630, alt: "TradeBud trading journal guides" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "TradeBud Journal — Trading Journal Guides",
    description: "Practical explanations for recording trades, reviewing decisions, and understanding performance.",
    images: ["https://tradebud.xyz/og-demo.png"],
  },
};

export default function BlogPage() {
  return (
    <main id="main-content" className="blog-page">
      <header className="legal-header">
        <Link href="/" className="legal-brand"><span aria-hidden="true">TB</span>TradeBud</Link>
        <nav aria-label="Blog navigation"><Link href="/free-trading-journal">Product guide</Link><Link href="/tools">Free tools</Link><Link href="/about">About</Link><a href="https://app.tradebud.xyz">Open app</a></nav>
      </header>

      <section className="blog-hero">
        <div><p>TRADEBUD JOURNAL</p><h1>Practical thinking for a better trading review.</h1></div>
        <p>Clear guides about journaling, performance metrics, costs, and process. Educational—not trading signals or investment advice.</p>
      </section>

      <section className="blog-list" aria-label="Trading journal articles">
        {articles.map((article, index) => (
          <article className={index === 0 ? "blog-card featured" : "blog-card"} key={article.slug}>
            <div className="blog-card-meta"><span>{article.category}</span><time dateTime={article.published}>{formatArticleDate(article.published)}</time><span>{article.readTime}</span></div>
            <h2><Link href={`/blog/${article.slug}`}>{article.title}</Link></h2>
            <p>{article.description}</p>
            <Link href={`/blog/${article.slug}`} aria-label={`Read ${article.title}`}>Read guide <span aria-hidden="true">→</span></Link>
          </article>
        ))}
      </section>

      <section className="blog-principles">
        <p>EDITORIAL STANDARD</p>
        <h2>Written to support review—not predict markets.</h2>
        <div><p>Every guide focuses on record-keeping, calculations, and decision review. We distinguish estimates from official broker records, cite primary sources where claims require them, and avoid securities recommendations.</p><Link href="/about">About TradeBud</Link></div>
      </section>

      <footer className="legal-footer"><span>© 2026 TradeBud</span><a href="/feed.xml">RSS</a><Link href="/privacy">Privacy</Link><Link href="/terms">Terms</Link></footer>
    </main>
  );
}
