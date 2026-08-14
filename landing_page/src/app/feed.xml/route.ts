import { articles } from "@/content/articles";

function escapeXml(value: string) {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&apos;");
}

export function GET() {
  const items = articles.map((article) => `
    <item>
      <title>${escapeXml(article.title)}</title>
      <link>https://tradebud.xyz/blog/${article.slug}</link>
      <guid isPermaLink="true">https://tradebud.xyz/blog/${article.slug}</guid>
      <description>${escapeXml(article.description)}</description>
      <category>${article.category}</category>
      <pubDate>${new Date(`${article.published}T00:00:00Z`).toUTCString()}</pubDate>
    </item>`).join("");

  const xml = `<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
  <channel>
    <title>TradeBud Journal</title>
    <link>https://tradebud.xyz/blog</link>
    <description>Practical guides about trading journals, performance metrics, costs, and review process.</description>
    <language>en</language>
    <lastBuildDate>${new Date("2026-08-14T00:00:00Z").toUTCString()}</lastBuildDate>${items}
  </channel>
</rss>`;

  return new Response(xml, { headers: { "Content-Type": "application/rss+xml; charset=utf-8", "Cache-Control": "public, max-age=3600, s-maxage=86400" } });
}
