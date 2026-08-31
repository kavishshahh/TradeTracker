import Link from "next/link";
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import CalculatorForm from "@/components/CalculatorForm";
import { getTool, tools } from "@/content/tools";

type PageProps = { params: Promise<{ slug: string }> };

export function generateStaticParams() {
  return tools.map(({ slug }) => ({ slug }));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { slug } = await params;
  const tool = getTool(slug);
  if (!tool) return {};

  const canonical = `https://tradebud.xyz/tools/${tool.slug}`;
  return {
    title: tool.seoTitle,
    description: tool.description,
    alternates: { canonical: `/tools/${tool.slug}` },
    openGraph: {
      type: "website",
      title: `${tool.seoTitle} | TradeBud`,
      description: tool.description,
      url: canonical,
      siteName: "TradeBud",
      locale: "en_US",
      images: [{ url: "https://tradebud.xyz/og-demo.png", width: 1200, height: 630, alt: `${tool.title} from TradeBud` }],
    },
    twitter: {
      card: "summary_large_image",
      title: `${tool.seoTitle} | TradeBud`,
      description: tool.description,
      images: ["https://tradebud.xyz/og-demo.png"],
    },
  };
}

export default async function ToolPage({ params }: PageProps) {
  const { slug } = await params;
  const tool = getTool(slug);
  if (!tool) notFound();

  const canonical = `https://tradebud.xyz/tools/${tool.slug}`;
  const structuredData = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "WebApplication",
        "@id": `${canonical}#calculator`,
        name: tool.title,
        description: tool.description,
        url: canonical,
        applicationCategory: "FinanceApplication",
        operatingSystem: "Web browser",
        isAccessibleForFree: true,
        offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
        publisher: { "@type": "Organization", name: "TradeBud", url: "https://tradebud.xyz" },
      },
      {
        "@type": "BreadcrumbList",
        itemListElement: [
          { "@type": "ListItem", position: 1, name: "Home", item: "https://tradebud.xyz" },
          { "@type": "ListItem", position: 2, name: "Tools", item: "https://tradebud.xyz/tools" },
          { "@type": "ListItem", position: 3, name: tool.title, item: canonical },
        ],
      },
      {
        "@type": "FAQPage",
        mainEntity: tool.faq.map((item) => ({
          "@type": "Question",
          name: item.question,
          acceptedAnswer: { "@type": "Answer", text: item.answer },
        })),
      },
    ],
  };

  return (
    <main id="main-content" className="tool-page">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData) }} />
      <header className="legal-header">
        <Link href="/" className="legal-brand"><span aria-hidden="true">TB</span>TradeBud</Link>
        <nav aria-label="Calculator navigation"><Link href="/tools">All tools</Link><Link href="/methodology">Methodology</Link><Link href="/blog">Guides</Link><a href="https://app.tradebud.xyz">Open app</a></nav>
      </header>

      <article className="tool-article">
        <nav className="breadcrumbs" aria-label="Breadcrumb"><Link href="/">Home</Link><span>/</span><Link href="/tools">Tools</Link><span>/</span><span>{tool.title}</span></nav>
        <header className="tool-header">
          <p>FREE TRADING TOOL</p>
          <h1>{tool.title}</h1>
          <p>{tool.summary}</p>
          <span>Updated {new Intl.DateTimeFormat("en-US", { dateStyle: "long" }).format(new Date(`${tool.updated}T00:00:00Z`))} · Educational information only</span>
        </header>

        <CalculatorForm tool={tool} />

        <div className="tool-content-grid">
          <section><p className="kicker">THE FORMULA</p><h2>{tool.formula}</h2><p>{tool.formulaNote}</p></section>
          <section><p className="kicker">WORKED EXAMPLE</p><h2>See how the number is produced.</h2><p>{tool.example}</p></section>
          <section><p className="kicker">HOW TO READ IT</p><h2>Interpret the result with context.</h2><ul>{tool.interpretation.map((item) => <li key={item}>{item}</li>)}</ul></section>
          <section><p className="kicker">COMMON MISTAKES</p><h2>Keep the inputs consistent.</h2><ul>{tool.mistakes.map((item) => <li key={item}>{item}</li>)}</ul></section>
        </div>

        {tool.faq.length > 0 && <section className="tool-faq"><p className="kicker">COMMON QUESTIONS</p><h2>{tool.title} FAQ</h2><div>{tool.faq.map((item) => <details key={item.question}><summary>{item.question}</summary><p>{item.answer}</p></details>)}</div></section>}

        <aside className="tool-disclaimer"><strong>Educational information only.</strong> This calculator is a transparent arithmetic aid. It is not investment, tax, legal, accounting, brokerage, or risk advice, and it cannot predict a future trade.</aside>

        <nav className="tool-related" aria-label="Related resources">
          <p className="kicker">CONTINUE YOUR REVIEW</p>
          <div>{tool.relatedGlossary && <Link href={`/glossary/${tool.relatedGlossary}`}>Read the {tool.title.replace(" calculator", "").toLowerCase()} glossary entry <span aria-hidden="true">→</span></Link>}{tool.relatedArticle && <Link href={`/blog/${tool.relatedArticle}`}>Read the related trading guide <span aria-hidden="true">→</span></Link>}<Link href="/methodology">See TradeBud&apos;s metric methodology <span aria-hidden="true">→</span></Link></div>
        </nav>
      </article>

      <footer className="legal-footer"><span>© 2026 TradeBud</span><Link href="/tools">Tools</Link><Link href="/free-trading-journal">Free journal</Link><Link href="/privacy">Privacy</Link><Link href="/terms">Terms</Link></footer>
    </main>
  );
}
