import sitemap from "@/app/sitemap";

export const dynamic = "force-static";

/**
 * Plain-text sitemap (one URL per line), built from the same list as sitemap.xml.
 * Google Search Console has been unable to read XML sitemaps served from Vercel on
 * several sites in 2026 while reading the text form fine, so robots.txt advertises both.
 */
export function GET() {
  const body = sitemap().map((entry) => entry.url).join("\n") + "\n";
  return new Response(body, {
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "public, max-age=3600, s-maxage=86400",
    },
  });
}
