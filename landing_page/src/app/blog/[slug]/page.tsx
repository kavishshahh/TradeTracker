import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { articles, getArticle } from "@/content/articles";

type PageProps = { params: Promise<{ slug: string }> };

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
      publishedTime: article.published,
      modifiedTime: article.updated,
      authors: ["https://tradebud.xyz/about"],
      section: article.category,
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
        image: "https://tradebud.xyz/og.png",
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
    <main className="article-page">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData) }} />
      <header className="legal-header">
        <a href="/" className="legal-brand"><span aria-hidden="true">TB</span>TradeBud</a>
        <nav aria-label="Article navigation"><a href="/blog">All guides</a><a href="/free-trading-journal">Product guide</a><a href="https://app.tradebud.xyz">Open app</a></nav>
      </header>

      <article className="article-shell">
        <nav className="breadcrumbs" aria-label="Breadcrumb"><a href="/">Home</a><span>/</span><a href="/blog">Journal</a><span>/</span><span>{article.category}</span></nav>
        <header className="article-header">
          <p>{article.category.toUpperCase()}</p>
          <h1>{article.title}</h1>
          <p>{article.description}</p>
          <div><span>By <a href="/about">TradeBud Editorial</a></span><time dateTime={article.published}>Published 14 August 2026</time><span>{article.readTime}</span></div>
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

            {article.sources && <section className="article-sources"><h2>Sources and further reading</h2><ul>{article.sources.map((source) => <li key={source.url}><a href={source.url} rel="noopener noreferrer">{source.label}</a></li>)}</ul></section>}

            <aside className="article-disclaimer"><strong>Educational information only.</strong> This guide discusses journaling and performance review. It is not investment, tax, legal, accounting, or brokerage advice, and it does not recommend any security or strategy.</aside>
          </div>
        </div>
      </article>

      <section className="related-reading">
        <div><p>CONTINUE READING</p><h2>Related guides</h2></div>
        <div>{related.map((item) => <article key={item.slug}><span>{item.category}</span><h3><a href={`/blog/${item.slug}`}>{item.title}</a></h3><a href={`/blog/${item.slug}`}>Read guide →</a></article>)}</div>
      </section>

      <footer className="legal-footer"><span>© 2026 TradeBud</span><a href="/blog">Journal</a><a href="/privacy">Privacy</a><a href="/terms">Terms</a></footer>
    </main>
  );
}
