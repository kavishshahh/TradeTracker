# TradeBud public site

This directory contains the public, indexable TradeBud website. It is a separate Next.js app from the authenticated journal in the repository root.

## Surface

- `/` — product overview with clearly labelled illustrative UI
- `/free-trading-journal` — product guide and FAQ
- `/tools` and `/tools/[slug]` — eight deterministic, client-side calculators
- `/glossary` and `/glossary/[slug]` — metric definitions and limitations
- `/methodology` — the current journal data model and calculation conventions
- `/blog` and `/blog/[slug]` — practical, educational trading-journal guides
- `/sitemap.xml`, `/robots.txt`, `/feed.xml`, `/llms.txt` — discovery resources

The public site does not collect trading data. Calculator inputs stay in the browser and are not sent to the authenticated API. Optional GA4 is loaded only when `NEXT_PUBLIC_GA_MEASUREMENT_ID` is configured; public events contain coarse action/resource names, never symbols, prices, balances, notes, or calculator values.

## Development

```bash
cd landing_page
npm install
npm run dev
```

Production checks:

```bash
npm run test
npm run typecheck
npm run lint
npm run build
```

The calculator tests use Node's built-in test runner with TypeScript stripping. The build is intentionally independent of Google Fonts so it can run in an offline CI environment; the stylesheet uses system fallbacks.

## Content conventions

Article and tool dates are stored in `src/content/` and surfaced in the sitemap. Every calculator includes a formula, worked example, interpretation, common mistakes, FAQ, and an educational disclaimer. Update the methodology page whenever the authenticated app's data model or fee convention changes.
