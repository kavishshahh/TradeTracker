import { articles } from "@/content/articles";
import { glossary } from "@/content/glossary";
import { tools } from "@/content/tools";

const lines = [
  "# TradeBud",
  "",
  "> TradeBud is a free trading journal and performance review tool for self-directed traders. It helps users record trade decisions, inspect fee-aware P&L, and understand historical performance. It is not a broker, signal service, or financial adviser.",
  "",
  "## Primary resources",
  "- [Free trading journal](https://tradebud.xyz/free-trading-journal): product capabilities, workflow, and FAQ.",
  "- [Trading metrics methodology](https://tradebud.xyz/methodology): current data model, fee convention, formulas, and unsupported analytics.",
  "- [Free trading calculators](https://tradebud.xyz/tools): deterministic calculators with visible assumptions.",
  "- [Trading performance glossary](https://tradebud.xyz/glossary): definitions, formulas, examples, and limitations.",
  "- [TradeBud About](https://tradebud.xyz/about): product purpose, scope, and contact information.",
  "",
  "## Calculators",
  ...tools.map((tool) => `- [${tool.title}](https://tradebud.xyz/tools/${tool.slug}): ${tool.description}`),
  "",
  "## Glossary",
  ...glossary.map((entry) => `- [${entry.term}](https://tradebud.xyz/glossary/${entry.slug}): ${entry.description}`),
  "",
  "## Guides",
  ...articles.map((article) => `- [${article.title}](https://tradebud.xyz/blog/${article.slug}): ${article.description}`),
  "",
  "## Important limitations",
  "- TradeBud's current product model is long-only and uses buy price, sell price, and share quantity for trade P&L.",
  "- Calculations depend on user-entered data and settings and may differ from broker, exchange, tax, or accounting records.",
  "- TradeBud does not currently claim validated forex, futures, options, short-selling, strategy attribution, or AI analysis support.",
  "- Educational content is not investment, tax, legal, accounting, brokerage, or risk advice.",
].join("\n");

export function GET() {
  return new Response(lines, {
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "public, max-age=3600, s-maxage=86400",
    },
  });
}
