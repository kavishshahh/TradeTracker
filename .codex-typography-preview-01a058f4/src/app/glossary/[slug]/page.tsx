import Link from "next/link";
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getGlossaryEntry, glossary } from "@/content/glossary";

type PageProps = { params: Promise<{ slug: string }> };

export function generateStaticParams() { return glossary.map(({ slug }) => ({ slug })); }

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { slug } = await params;
  const entry = getGlossaryEntry(slug);
  if (!entry) return {};
  const canonical = `https://tradebud.xyz/glossary/${entry.slug}`;
  return {
    title: entry.seoTitle,
    description: entry.description,
    alternates: { canonical: `/glossary/${entry.slug}` },
    openGraph: { type: "article", title: `${entry.seoTitle} | TradeBud`, description: entry.description, url: canonical, siteName: "TradeBud", locale: "en_US", images: [{ url: "https://tradebud.xyz/og-demo.png", width: 1200, height: 630, alt: `${entry.term} glossary entry` }] },
    twitter: { card: "summary_large_image", title: `${entry.seoTitle} | TradeBud`, description: entry.description, images: ["https://tradebud.xyz/og-demo.png"] },
  };
}

export default async function GlossaryEntryPage({ params }: PageProps) {
  const { slug } = await params;
  const entry = getGlossaryEntry(slug);
  if (!entry) notFound();
  const canonical = `https://tradebud.xyz/glossary/${entry.slug}`;
  const structuredData = {
    "@context": "https://schema.org",
    "@graph": [
      { "@type": "DefinedTerm", "@id": `${canonical}#term`, name: entry.term, description: entry.definition, termCode: entry.slug, inDefinedTermSet: { "@type": "DefinedTermSet", name: "TradeBud Trading Performance Glossary", url: "https://tradebud.xyz/glossary" }, url: canonical },
      { "@type": "BreadcrumbList", itemListElement: [{ "@type": "ListItem", position: 1, name: "Home", item: "https://tradebud.xyz" }, { "@type": "ListItem", position: 2, name: "Glossary", item: "https://tradebud.xyz/glossary" }, { "@type": "ListItem", position: 3, name: entry.term, item: canonical }] },
    ],
  };

  return (
    <main id="main-content" className="tool-page">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData) }} />
      <header className="legal-header"><Link href="/" className="legal-brand"><span aria-hidden="true">TB</span>TradeBud</Link><nav aria-label="Glossary entry navigation"><Link href="/glossary">All definitions</Link><Link href="/tools">Calculators</Link><Link href="/methodology">Methodology</Link><a href="https://app.tradebud.xyz">Open app</a></nav></header>
      <article className="tool-article"><nav className="breadcrumbs" aria-label="Breadcrumb"><Link href="/">Home</Link><span>/</span><Link href="/glossary">Glossary</Link><span>/</span><span>{entry.term}</span></nav><header className="tool-header"><p>TRADING PERFORMANCE GLOSSARY</p><h1>{entry.term}</h1><p>{entry.definition}</p><span>Updated {new Intl.DateTimeFormat("en-US", { dateStyle: "long" }).format(new Date(`${entry.updated}T00:00:00Z`))} · Educational information only</span></header>
        <div className="tool-content-grid"><section><p className="kicker">THE FORMULA</p><h2>{entry.formula}</h2><p>{entry.formula.includes("÷") ? "Use consistent units and state how breakevens, fees, and incomplete trades are treated." : "Use the exact convention shown when comparing samples."}</p></section><section><p className="kicker">WORKED EXAMPLE</p><h2>See the calculation.</h2><p>{entry.example}</p></section><section><p className="kicker">HOW TO INTERPRET IT</p><h2>Ask what the number leaves out.</h2><ul>{entry.interpretation.map((item) => <li key={item}>{item}</li>)}</ul></section><section><p className="kicker">COMMON MISTAKES</p><h2>Keep comparisons honest.</h2><ul>{entry.mistakes.map((item) => <li key={item}>{item}</li>)}</ul></section></div>
        <aside className="tool-disclaimer"><strong>Educational information only.</strong> This definition explains a performance metric; it is not financial, investment, tax, legal, accounting, brokerage, or risk advice.</aside>
        <nav className="tool-related" aria-label="Related resources"><p className="kicker">CONTINUE YOUR REVIEW</p><div><Link href={`/tools/${entry.relatedTool}`}>Use the {entry.term.toLowerCase()} calculator <span aria-hidden="true">→</span></Link>{entry.relatedArticle && <Link href={`/blog/${entry.relatedArticle}`}>Read the related trading guide <span aria-hidden="true">→</span></Link>}<Link href="/methodology">See TradeBud&apos;s methodology <span aria-hidden="true">→</span></Link></div></nav>
      </article><footer className="legal-footer"><span>© 2026 TradeBud</span><Link href="/glossary">Glossary</Link><Link href="/tools">Tools</Link><Link href="/privacy">Privacy</Link><Link href="/terms">Terms</Link></footer>
    </main>
  );
}
