import type { Metadata } from "next";
import { notFound } from "next/navigation";
import Link from "next/link";
import { articles, formatArticleDate, getArticle } from "@/content/articles";

type PageProps = { params: Promise<{ slug: string }> };

const articleResources: Record<string, { href: string; label: string }[]> = {
  "why-use-a-trading-journal": [
    { href: "/free-trading-journal", label: "See the free trading journal" },
    { href: "/methodology", label: "Read the metric methodology" },
  ],
  "trading-journal-vs-spreadsheet": [
    { href: "/free-trading-journal", label: "See the free trading journal" },
    { href: "/tools", label: "Try the free performance calculators" },
  ],
  "how-to-start-a-trading-journal": [
    { href: "/free-trading-journal", label: "Start a structured journal" },
    { href: "/glossary/trading-expectancy", label: "Understand trading expectancy" },
  ],
  "trading-journal-metrics-that-matter": [
    { href: "/tools", label: "Open the free metric calculators" },
    { href: "/methodology", label: "See how TradeBud defines metrics" },
  ],
  "how-to-calculate-trading-expectancy": [
    { href: "/tools/trading-expectancy-calculator", label: "Calculate expectancy" },
    { href: "/glossary/trading-expectancy", label: "Read the expectancy glossary entry" },
  ],
  "post-trade-review-checklist": [
    { href: "/free-trading-journal", label: "Use the free review journal" },
    { href: "/tools", label: "Review the performance calculators" },
  ],
  "why-track-trading-fees": [
    { href: "/methodology", label: "Read the fee and metric methodology" },
    { href: "/tools/trading-roi-calculator", label: "Calculate simple trading ROI" },
  ],
  "common-trading-journal-mistakes": [
    { href: "/free-trading-journal", label: "Start a consistent journal" },
    { href: "/tools/win-rate-calculator", label: "Check win-rate definitions" },
  ],
};

export function generateStaticParams() {
  return articles.map(({ slug }) => ({ slug }));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { slug } = await params;
  const article = getArticle(slug);
  if (!article) return {};

  return {
    title: article.seoTitle,
    description: article.description,
    authors: [{ name: "TradeBud Editorial", url: "https://tradebud.xyz/about" }],
    alternates: { canonical: `/blog/${article.slug}` },
    openGraph: {
      type: "article",
      title: article.seoTitle,
      description: article.description,
      url: `/blog/${article.slug}`,
      siteName: "TradeBud",
      locale: "en_US",
      publishedTime: article.published,
      modifiedTime: article.updated,
      authors: ["https://tradebud.xyz/about"],
      section: article.category,
      images: [{ url: "https://tradebud.xyz/og-demo.png", width: 1200, height: 630, alt: article.title }],
    },
    twitter: {
      card: "summary_large_image",
      title: article.seoTitle,
      description: article.description,
      images: ["https://tradebud.xyz/og-demo.png"],
    },
  };
}

export default async function ArticlePage({ params }: PageProps) {
  const { slug } = await params;
  const article = getArticle(slug);
  if (!article) notFound();

  const related = articles.filter((item) => item.slug !== article.slug).sort((a, b) => Number(b.category === article.category) - Number(a.category === article.category)).slice(0, 3);
  const canonical = `https://tradebud.xyz/blog/${article.slug}`;
  const structuredData = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "Article",
        "@id": `${canonical}#article`,
        headline: article.title,
        description: article.description,
        datePublished: article.published,
        dateModified: article.updated,
        mainEntityOfPage: canonical,
        inLanguage: "en",
        articleSection: article.category,
        author: { "@type": "Organization", name: "TradeBud Editorial", url: "https://tradebud.xyz/about" },
        publisher: { "@type": "Organization", name: "TradeBud", url: "https://tradebud.xyz" },
        image: "https://tradebud.xyz/og-demo.png",
        isAccessibleForFree: true,
      },
      {
        "@type": "BreadcrumbList",
        itemListElement: [
          { "@type": "ListItem", position: 1, name: "Home", item: "https://tradebud.xyz" },
          { "@type": "ListItem", position: 2, name: "Journal", item: "https://tradebud.xyz/blog" },
          { "@type": "ListItem", position: 3, name: article.title, item: canonical },
        ],
      },
    ],
  };

  return (
    <main id="main-content" className="article-page">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData) }} />
      <header className="legal-header">
        <Link href="/" className="legal-brand"><span aria-hidden="true">TB</span>TradeBud</Link>
        <nav aria-label="Article navigation"><Link href="/blog">All guides</Link><Link href="/free-trading-journal">Product guide</Link><a href="https://app.tradebud.xyz">Open app</a></nav>
      </header>

      <article className="article-shell">
        <nav className="breadcrumbs" aria-label="Breadcrumb"><Link href="/">Home</Link><span>/</span><Link href="/blog">Journal</Link><span>/</span><span>{article.category}</span></nav>
        <header className="article-header">
          <p>{article.category.toUpperCase()}</p>
          <h1>{article.title}</h1>
          <p>{article.description}</p>
          <div><span>By <Link href="/about">TradeBud Editorial</Link></span><time dateTime={article.published}>Published {formatArticleDate(article.published)}</time>{article.updated !== article.published && <time dateTime={article.updated}>Updated {formatArticleDate(article.updated)}</time>}<span>{article.readTime}</span></div>
        </header>

        <div className="article-layout">
          <aside className="article-aside">
            <p>IN THIS GUIDE</p>
            <ol>{article.sections.map((section, index) => <li key={section.heading}><a href={`#section-${index + 1}`}>{section.heading}</a></li>)}</ol>
          </aside>

          <div className="article-body">
            <p className="article-intro">{article.intro}</p>
            {article.sections.map((section, index) => (
              <section id={`section-${index + 1}`} key={section.heading}>
                <h2>{section.heading}</h2>
                {section.paragraphs.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}
                {section.bullets && <ul>{section.bullets.map((bullet) => <li key={bullet}>{bullet}</li>)}</ul>}
              </section>
            ))}

            <section className="article-takeaway"><p>THE TAKEAWAY</p><h2>{article.takeaway}</h2></section>

            {articleResources[article.slug] && <section className="article-resources"><p className="kicker">PRACTICAL NEXT STEPS</p><h2>Continue with a tool or reference.</h2><ul>{articleResources[article.slug].map((resource) => <li key={resource.href}><Link href={resource.href}>{resource.label} <span aria-hidden="true">→</span></Link></li>)}</ul></section>}

            {article.sources && <section className="article-sources"><h2>Sources and further reading</h2><ul>{article.sources.map((source) => <li key={source.url}><a href={source.url} rel="noopener noreferrer">{source.label}</a></li>)}</ul></section>}

            <aside className="article-disclaimer"><strong>Educational information only.</strong> This guide discusses journaling and performance review. It is not investment, tax, legal, accounting, or brokerage advice, and it does not recommend any security or strategy.</aside>
          </div>
        </div>
      </article>

      <section className="related-reading">
        <div><p>CONTINUE READING</p><h2>Related guides</h2></div>
        <div>{related.map((item) => <article key={item.slug}><span>{item.category}</span><h3><Link href={`/blog/${item.slug}`}>{item.title}</Link></h3><Link href={`/blog/${item.slug}`}>Read guide →</Link></article>)}</div>
      </section>

      <footer className="legal-footer"><span>© 2026 TradeBud</span><Link href="/blog">Journal</Link><Link href="/privacy">Privacy</Link><Link href="/terms">Terms</Link></footer>
    </main>
  );
}
