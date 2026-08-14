import type { Metadata } from "next";
import { articles } from "@/content/articles";

export const metadata: Metadata = {
  title: "Trading Journal Guides and Practical Reviews",
  description: "Clear, practical guides about trading journals, performance metrics, post-trade reviews, trading costs, and building a repeatable review process.",
  alternates: {
    canonical: "/blog",
    types: { "application/rss+xml": "https://tradebud.xyz/feed.xml" },
  },
  openGraph: {
    title: "TradeBud Journal — Trading Journal Guides",
    description: "Practical explanations for recording trades, reviewing decisions, and understanding performance.",
    url: "/blog",
  },
};

export default function BlogPage() {
  return (
    <main className="blog-page">
      <header className="legal-header">
        <a href="/" className="legal-brand"><span aria-hidden="true">TB</span>TradeBud</a>
        <nav aria-label="Blog navigation"><a href="/free-trading-journal">Product guide</a><a href="/about">About</a><a href="https://app.tradebud.xyz">Open app</a></nav>
      </header>

      <section className="blog-hero">
        <div><p>TRADEBUD JOURNAL</p><h1>Practical thinking for a better trading review.</h1></div>
        <p>Clear guides about journaling, performance metrics, costs, and process. Educational—not trading signals or investment advice.</p>
      </section>

      <section className="blog-list" aria-label="Trading journal articles">
        {articles.map((article, index) => (
          <article className={index === 0 ? "blog-card featured" : "blog-card"} key={article.slug}>
            <div className="blog-card-meta"><span>{article.category}</span><time dateTime={article.published}>14 Aug 2026</time><span>{article.readTime}</span></div>
            <h2><a href={`/blog/${article.slug}`}>{article.title}</a></h2>
            <p>{article.description}</p>
            <a href={`/blog/${article.slug}`} aria-label={`Read ${article.title}`}>Read guide <span aria-hidden="true">→</span></a>
          </article>
        ))}
      </section>

      <section className="blog-principles">
        <p>EDITORIAL STANDARD</p>
        <h2>Written to support review—not predict markets.</h2>
        <div><p>Every guide focuses on record-keeping, calculations, and decision review. We distinguish estimates from official broker records, cite primary sources where claims require them, and avoid securities recommendations.</p><a href="/about">About TradeBud</a></div>
      </section>

      <footer className="legal-footer"><span>© 2026 TradeBud</span><a href="/feed.xml">RSS</a><a href="/privacy">Privacy</a><a href="/terms">Terms</a></footer>
    </main>
  );
}
