import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Terms of Service",
  description: "The terms that govern access to and use of the free TradeBud trading journal and performance analytics application.",
  alternates: { canonical: "/terms" },
  openGraph: { type: "website", title: "Terms of Service | TradeBud", description: "Terms governing use of TradeBud.", url: "https://tradebud.xyz/terms", siteName: "TradeBud", locale: "en_US", images: [{ url: "https://tradebud.xyz/og-demo.png", width: 1200, height: 630, alt: "TradeBud terms of service" }] },
  twitter: { card: "summary_large_image", title: "Terms of Service | TradeBud", description: "Terms governing use of TradeBud.", images: ["https://tradebud.xyz/og-demo.png"] },
};

export default function TermsPage() {
  return (
    <main id="main-content" className="legal-page">
      <header className="legal-header">
        <Link href="/" className="legal-brand"><span aria-hidden="true">TB</span>TradeBud</Link>
        <nav aria-label="Legal navigation"><Link href="/free-trading-journal">Product guide</Link><Link href="/tools">Free tools</Link><Link href="/privacy">Privacy</Link><a href="https://app.tradebud.xyz">Open app</a></nav>
      </header>

      <article className="legal-article">
        <div className="legal-title"><p>LEGAL</p><h1>Terms of Service</h1><span>Last updated: 31 August 2026</span></div>
        <p className="legal-summary">These terms govern your access to TradeBud. By creating an account or using the service, you agree to them.</p>

        <section><h2>1. The service</h2><p>TradeBud is a personal trading journal and analytics application. It lets you record trade information, maintain notes, calculate estimated trading costs, and review performance. Features and calculations are provided for informational and organizational purposes.</p></section>

        <section><h2>2. Free forever</h2><p>TradeBud’s core trading journal is free forever. There is no subscription fee, trial clock, or credit card requirement for the current core journal, calendar, trade tracking, and performance analytics features. If optional paid services are ever introduced, they will be clearly identified and will not convert your use into a charge without your express agreement.</p></section>

        <section><h2>3. Eligibility and accounts</h2><p>You must be at least 18 and legally able to agree to these terms. You are responsible for providing accurate account information, safeguarding your credentials, and all activity under your account. Notify us promptly if you suspect unauthorized access.</p></section>

        <section><h2>4. Not financial advice</h2><p>TradeBud does not provide investment, tax, accounting, brokerage, or legal advice. It does not recommend securities or trading strategies, execute trades, hold funds, or connect you with a broker. Trading involves risk, and past performance or journal calculations do not guarantee future results. You remain solely responsible for trading decisions and should consult qualified professionals where appropriate.</p></section>

        <section><h2>5. Calculations and data accuracy</h2><p>Performance, fee, position-size, and other calculations depend on the information and settings you provide. They may contain errors, estimates, rounding differences, or omissions and should be checked against official broker, exchange, tax, and account records. TradeBud is not a system of record.</p></section>

        <section><h2>6. Your content</h2><p>You retain ownership of the trade records, notes, and other content you submit. You grant TradeBud a limited permission to host, process, back up, and display that content only as needed to provide, secure, and improve the service. You represent that you have the right to submit the content and that it does not violate law or another person’s rights.</p></section>

        <section><h2>7. Acceptable use</h2><p>You may not misuse TradeBud, attempt unauthorized access, interfere with service operation, introduce malicious code, scrape or overload the service, reverse engineer protected portions, impersonate another person, use the service for unlawful activity, or help others do so.</p></section>

        <section><h2>8. Third-party services</h2><p>TradeBud uses third-party authentication, hosting, analytics, and email services. Their services may be subject to separate terms. We are not responsible for third-party services outside our reasonable control.</p></section>

        <section><h2>9. Availability and changes</h2><p>We work to keep TradeBud reliable, but the service may occasionally be unavailable because of maintenance, security incidents, provider failures, or events outside our control. We may improve, replace, or discontinue features, provided that we will not begin charging you without clear notice and your express agreement.</p></section>

        <section><h2>10. Intellectual property</h2><p>TradeBud, including its software, design, branding, and original content, is owned by TradeBud or its licensors and protected by applicable intellectual-property laws. These terms give you a personal, limited, non-exclusive, non-transferable right to use the service.</p></section>

        <section><h2>11. Disclaimer</h2><p>To the extent permitted by law, TradeBud is provided “as is” and “as available,” without warranties of uninterrupted availability, accuracy, fitness for a particular purpose, non-infringement, or merchantability. Nothing in these terms excludes rights that cannot legally be excluded.</p></section>

        <section><h2>12. Limitation of liability</h2><p>To the extent permitted by law, TradeBud and its operators will not be liable for indirect, incidental, special, consequential, exemplary, or punitive damages; lost profits or trading losses; loss or corruption of data; or decisions made in reliance on the service. Where liability cannot be excluded, it will be limited to the minimum amount permitted by applicable law.</p></section>

        <section><h2>13. Suspension and termination</h2><p>You may stop using TradeBud at any time. We may suspend or terminate access when reasonably necessary to address security risks, unlawful activity, serious or repeated violations, or threats to other users or the service. You may request deletion of your account and data as described in the Privacy Policy.</p></section>

        <section><h2>14. Changes to these terms</h2><p>We may update these terms to reflect product, legal, or security changes. The updated date above identifies the latest version. If a change materially affects your rights, we will provide reasonable notice where appropriate.</p></section>

        <section><h2>15. Contact</h2><p>Questions about these terms can be sent to <a href="mailto:kavishshah30@gmail.com">kavishshah30@gmail.com</a>.</p></section>
      </article>

      <footer className="legal-footer"><span>© 2026 TradeBud</span><Link href="/">Home</Link><Link href="/privacy">Privacy</Link></footer>
    </main>
  );
}
