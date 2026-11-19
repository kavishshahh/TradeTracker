import type { MetadataRoute } from "next";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: { userAgent: "*", allow: "/", disallow: ["/api/"] },
    sitemap: ["https://tradebud.xyz/sitemap.xml", "https://tradebud.xyz/sitemap.txt"],
  };
}
