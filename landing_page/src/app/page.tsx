'use client';

import {
  ArrowRight,
  BarChart3,
  BookOpen,
  CalendarDays,
  Check,
  CircleDollarSign,
  Menu,
  ShieldCheck,
  Target,
  TrendingUp,
  X,
} from 'lucide-react';
import { useState } from 'react';

const APP_URL = 'https://app.tradebud.xyz';

const features = [
  {
    number: '01',
    icon: BarChart3,
    title: 'Know what is working',
    description:
      'See win rate, profit factor, expectancy, average win and loss, and your equity curve in one clean view.',
  },
  {
    number: '02',
    icon: BookOpen,
    title: 'Keep the context',
    description:
      'Record the setup, thesis, execution, and notes behind each trade—not just the final P&L.',
  },
  {
    number: '03',
    icon: ShieldCheck,
    title: 'Account for real costs',
    description:
      'Track brokerage and exchange fees so your results reflect what actually reached your account.',
  },
];

const workflow = [
  ['Log', 'Add the trade, position size, entry, exit, and your reasoning.'],
  ['Review', 'Use calendar and journal views to spot recurring decisions.'],
  ['Improve', 'Turn your history into rules you can repeat—and mistakes you can avoid.'],
];

function BrandMark() {
  return (
    <span className="brand-mark" aria-hidden="true">
      <span />
      <span />
      <span />
    </span>
  );
}

function ProductPreview() {
  const chartPath =
    'M8 142 C42 139, 57 128, 84 132 S125 119, 151 121 S194 96, 222 104 S267 72, 292 78 S335 55, 362 62 S405 35, 442 44';

  return (
    <div className="product-frame" aria-label="TradeBud dashboard preview">
      <div className="app-sidebar">
        <div className="sidebar-logo"><BrandMark /></div>
        {[BarChart3, CircleDollarSign, CalendarDays, BookOpen].map((Icon, index) => (
          <span className={index === 0 ? 'side-icon active' : 'side-icon'} key={index}>
            <Icon size={16} strokeWidth={1.8} />
          </span>
        ))}
      </div>

      <div className="app-main">
        <div className="preview-head">
          <div>
            <small>OVERVIEW</small>
            <strong>Trading performance</strong>
          </div>
          <span>May 2026</span>
        </div>

        <div className="metric-row">
          <div><small>Net P&amp;L</small><strong className="positive">+$4,286</strong><em>+12.4%</em></div>
          <div><small>Win rate</small><strong>63.8%</strong><em>30 / 47 trades</em></div>
          <div><small>Profit factor</small><strong>2.14</strong><em>Healthy</em></div>
        </div>

        <div className="chart-card">
          <div className="chart-title"><span>Account equity</span><small>$38,420</small></div>
          <div className="chart-wrap">
            <div className="chart-grid"><span /><span /><span /><span /></div>
            <svg viewBox="0 0 450 160" preserveAspectRatio="none" role="img" aria-label="Upward account equity chart">
              <path className="chart-area" d={`${chartPath} L442 160 L8 160 Z`} />
              <path className="chart-line" d={chartPath} />
            </svg>
          </div>
          <div className="chart-labels"><span>May 01</span><span>May 08</span><span>May 15</span><span>May 22</span><span>May 29</span></div>
        </div>

        <div className="trade-strip">
          <div><span className="ticker">NVDA</span><small>Breakout · Long</small></div>
          <span>May 28</span><strong className="positive">+$618.40</strong>
        </div>
      </div>
    </div>
  );
}

export default function Home() {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <main>
      <header className="site-header">
        <div className="shell nav-wrap">
          <a className="brand" href="#top" aria-label="TradeBud home">
            <BrandMark />
            <span>TradeBud</span>
          </a>

          <nav className="desktop-nav" aria-label="Main navigation">
            <a href="#features">Features</a>
            <a href="#how-it-works">How it works</a>
            <a href="#pricing">Pricing</a>
          </nav>

          <div className="nav-actions">
            <a className="text-link" href={APP_URL}>Sign in</a>
            <a className="button button-small" href={APP_URL}>Start tracking</a>
          </div>

          <button
            className="menu-button"
            onClick={() => setMenuOpen(!menuOpen)}
            aria-expanded={menuOpen}
            aria-label={menuOpen ? 'Close menu' : 'Open menu'}
          >
            {menuOpen ? <X size={22} /> : <Menu size={22} />}
          </button>
        </div>

        {menuOpen && (
          <nav className="mobile-nav" aria-label="Mobile navigation">
            <a href="#features" onClick={() => setMenuOpen(false)}>Features</a>
            <a href="#how-it-works" onClick={() => setMenuOpen(false)}>How it works</a>
            <a href="#pricing" onClick={() => setMenuOpen(false)}>Pricing</a>
            <a href={APP_URL}>Sign in</a>
            <a className="button" href={APP_URL}>Start tracking</a>
          </nav>
        )}
      </header>

      <section className="hero" id="top">
        <div className="shell hero-grid">
          <div className="hero-copy">
            <p className="eyebrow"><span /> A clearer view of your trading</p>
            <h1>Your trading history should teach you something.</h1>
            <p className="hero-lede">
              TradeBud turns every trade into useful feedback. Journal decisions, measure performance, and build a process you can trust.
            </p>
            <div className="hero-actions">
              <a className="button button-large" href={APP_URL}>
                Start tracking free <ArrowRight size={18} />
              </a>
              <a className="quiet-link" href="#features">Explore the product</a>
            </div>
            <div className="proof-line">
              <span><Check size={15} /> No credit card</span>
              <span><Check size={15} /> Unlimited trades</span>
              <span><Check size={15} /> Fees included</span>
            </div>
          </div>

          <div className="preview-column">
            <ProductPreview />
            <p className="preview-note"><span>LIVE INSIGHT</span> Net results after estimated trading fees</p>
          </div>
        </div>
      </section>

      <section className="signal-bar" aria-label="TradeBud capabilities">
        <div className="shell signal-grid">
          <p>Built for deliberate traders</p>
          <span>Performance analytics</span>
          <span>Trade journal</span>
          <span>Risk tracking</span>
          <span>Fee calculations</span>
        </div>
      </section>

      <section className="section features-section" id="features">
        <div className="shell">
          <div className="section-heading">
            <p className="kicker">THE FEEDBACK LOOP</p>
            <h2>Less noise. Better decisions.</h2>
            <p>TradeBud brings your execution, results, and notes together so you can review the whole decision—not a disconnected spreadsheet row.</p>
          </div>

          <div className="feature-list">
            {features.map(({ number, icon: Icon, title, description }) => (
              <article className="feature-row" key={number}>
                <span className="feature-number">{number}</span>
                <div className="feature-icon"><Icon size={21} strokeWidth={1.7} /></div>
                <h3>{title}</h3>
                <p>{description}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="section workflow-section" id="how-it-works">
        <div className="shell workflow-grid">
          <div className="workflow-intro">
            <p className="kicker">A SIMPLE PRACTICE</p>
            <h2>From execution to insight in three steps.</h2>
            <p>The journal stays out of your way during the session, then gives you the structure to review it honestly.</p>
          </div>

          <div className="workflow-list">
            {workflow.map(([title, description], index) => (
              <div className="workflow-step" key={title}>
                <span>0{index + 1}</span>
                <div><h3>{title}</h3><p>{description}</p></div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="section detail-section">
        <div className="shell detail-grid">
          <div className="calendar-card" aria-label="Trading calendar example">
            <div className="calendar-head"><strong>May 2026</strong><span>Monthly P&amp;L <b>+$4,286</b></span></div>
            <div className="weekdays">{['MON','TUE','WED','THU','FRI'].map(day => <span key={day}>{day}</span>)}</div>
            <div className="calendar-days">
              {[
                ['', ''], ['', ''], ['', ''], ['1', '+$214'], ['2', '—'],
                ['5', '+$386'], ['6', '-$94'], ['7', '+$712'], ['8', '+$128'], ['9', '—'],
                ['12', '+$440'], ['13', '+$96'], ['14', '-$182'], ['15', '+$804'], ['16', '+$215'],
                ['19', '—'], ['20', '+$326'], ['21', '-$76'], ['22', '+$510'], ['23', '+$190'],
              ].map(([day, pnl], index) => (
                <span className={pnl.startsWith('+') ? 'day win' : pnl.startsWith('-') ? 'day loss' : 'day'} key={index}>
                  <small>{day}</small><b>{pnl}</b>
                </span>
              ))}
            </div>
          </div>

          <div className="detail-copy">
            <p className="kicker">PATTERNS, MADE VISIBLE</p>
            <h2>See the days behind the numbers.</h2>
            <p>A single monthly result can hide a lot. The trading calendar shows consistency, drawdowns, and clusters of good or poor execution at a glance.</p>
            <ul>
              <li><Target size={18} /> Review performance by day and month</li>
              <li><TrendingUp size={18} /> Separate process trends from one-off outcomes</li>
              <li><CalendarDays size={18} /> Move from a date straight into the underlying trades</li>
            </ul>
          </div>
        </div>
      </section>

      <section className="section pricing-section" id="pricing">
        <div className="shell pricing-grid">
          <div>
            <p className="kicker">PRICING</p>
            <h2>Use the full journal. Pay nothing.</h2>
          </div>
          <div className="price-card">
            <div><span>TradeBud</span><strong>$0</strong><small>Free to use</small></div>
            <ul>
              <li><Check size={16} /> Unlimited trade entries</li>
              <li><Check size={16} /> Complete performance analytics</li>
              <li><Check size={16} /> Journal and calendar views</li>
              <li><Check size={16} /> Fee-aware net P&amp;L</li>
            </ul>
            <a className="button button-large" href={APP_URL}>Create your journal <ArrowRight size={18} /></a>
            <p>No trial clock. No card required.</p>
          </div>
        </div>
      </section>

      <footer>
        <div className="shell footer-grid">
          <div>
            <a className="brand footer-brand" href="#top"><BrandMark /><span>TradeBud</span></a>
            <p>A clearer record of every trading decision.</p>
          </div>
          <div className="footer-links">
            <a href="#features">Features</a>
            <a href="#how-it-works">How it works</a>
            <a href="#pricing">Pricing</a>
            <a href="mailto:kavishshah30@gmail.com">Support</a>
          </div>
          <p className="copyright">© {new Date().getFullYear()} TradeBud</p>
        </div>
      </footer>
    </main>
  );
}
