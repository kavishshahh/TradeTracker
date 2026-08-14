import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Privacy Policy",
  description: "How TradeBud collects, uses, protects, and lets you control account, trading journal, and usage data.",
  alternates: { canonical: "/privacy" },
  openGraph: { title: "Privacy Policy | TradeBud", description: "How TradeBud handles and protects your information.", url: "/privacy" },
};

export default function PrivacyPage() {
  return (
    <main className="legal-page">
      <header className="legal-header">
        <a href="/" className="legal-brand"><span aria-hidden="true">TB</span>TradeBud</a>
        <nav aria-label="Legal navigation"><a href="/free-trading-journal">Product guide</a><a href="/terms">Terms</a><a href="https://app.tradebud.xyz">Open app</a></nav>
      </header>

      <article className="legal-article">
        <div className="legal-title"><p>LEGAL</p><h1>Privacy Policy</h1><span>Last updated: 14 August 2026</span></div>
        <p className="legal-summary">This policy explains what information TradeBud handles, why it is needed, and the choices available to you. TradeBud does not sell your personal information.</p>

        <section><h2>1. Information we collect</h2><p>We may collect the following categories of information when you use TradeBud:</p><ul>
          <li><strong>Account information:</strong> your email address, display name, authentication provider, and account identifier.</li>
          <li><strong>Trading journal information:</strong> trade dates, ticker symbols, prices, quantities, position status, risk information, notes, journal entries, account balances, fee settings, and performance calculations you choose to enter.</li>
          <li><strong>Support communications:</strong> information you include when contacting us for assistance.</li>
          <li><strong>Technical and usage information:</strong> browser and device information, approximate location derived from IP address, page interactions, and diagnostic events when analytics is enabled.</li>
        </ul></section>

        <section><h2>2. How we use information</h2><p>We use information to authenticate your account, store and display your journal, calculate performance metrics, operate and secure the service, answer support requests, send necessary account communications, understand product usage, diagnose problems, and improve TradeBud.</p></section>

        <section><h2>3. Service providers</h2><p>TradeBud relies on service providers that process information on our behalf. These may include Google Firebase for authentication and application infrastructure, Google Analytics when configured for product analytics, Brevo for transactional email, and hosting or infrastructure providers used to deliver the website and application. Their handling of information is governed by their own terms and privacy commitments.</p></section>

        <section><h2>4. Cookies and local storage</h2><p>TradeBud may use cookies and browser storage to maintain your authenticated session, remember preferences such as theme, prevent abuse, and measure product usage. You can control cookies through your browser, although blocking necessary storage may prevent sign-in or other features from working.</p></section>

        <section><h2>5. Sharing and sale of information</h2><p>We do not sell your personal information. We share information only with service providers needed to operate TradeBud, when you ask us to, when required by law, or when reasonably necessary to protect users, TradeBud, or the public from fraud, abuse, or security threats.</p></section>

        <section><h2>6. Data retention and deletion</h2><p>We retain account and journal information while your account is active and as reasonably necessary to provide the service, meet legal obligations, resolve disputes, and protect the service. You may request account or data deletion by emailing us. Some limited records may be retained where required for security, fraud prevention, or legal compliance.</p></section>

        <section><h2>7. Security</h2><p>We use reasonable administrative and technical safeguards intended to protect your information. No internet service can guarantee absolute security, so you should use a unique password and keep access to your account secure.</p></section>

        <section><h2>8. International processing</h2><p>Our service providers may process information in countries other than your own. Where required, we rely on appropriate safeguards for international transfers.</p></section>

        <section><h2>9. Your choices and rights</h2><p>Depending on your location, you may have rights to access, correct, export, restrict, object to processing of, or delete personal information. You may also withdraw consent where processing relies on consent. Contact us to make a request; we may need to verify your identity.</p></section>

        <section><h2>10. Children</h2><p>TradeBud is not intended for children under 18, and we do not knowingly collect personal information from children.</p></section>

        <section><h2>11. Changes to this policy</h2><p>We may update this policy as TradeBud evolves or legal requirements change. The updated date above identifies the latest version. Material changes will be communicated through the website, application, or email when appropriate.</p></section>

        <section><h2>12. Contact</h2><p>For privacy questions or requests, email <a href="mailto:kavishshah30@gmail.com">kavishshah30@gmail.com</a>.</p></section>
      </article>

      <footer className="legal-footer"><span>© 2026 TradeBud</span><a href="/">Home</a><a href="/terms">Terms</a></footer>
    </main>
  );
}
