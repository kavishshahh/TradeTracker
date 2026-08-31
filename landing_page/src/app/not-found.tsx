import Link from "next/link";

export default function NotFound() {
  return (
    <main id="main-content" className="legal-page">
      <header className="legal-header">
        <Link href="/" className="legal-brand"><span aria-hidden="true">TB</span>TradeBud</Link>
        <nav aria-label="Not found navigation"><Link href="/tools">Free tools</Link><Link href="/blog">Guides</Link><a href="https://app.tradebud.xyz">Open app</a></nav>
      </header>
      <article className="legal-article">
        <div className="legal-title"><p>404</p><h1>That page is not in the journal.</h1><span>The link may be out of date, or the page may have moved.</span></div>
        <p className="legal-summary"><Link href="/">Return to TradeBud</Link>, browse the <Link href="/tools">free calculators</Link>, or read the latest <Link href="/blog">trading guides</Link>.</p>
      </article>
      <footer className="legal-footer"><span>© 2026 TradeBud</span><Link href="/privacy">Privacy</Link><Link href="/terms">Terms</Link></footer>
    </main>
  );
}
