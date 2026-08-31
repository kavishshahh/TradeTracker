import type { MetadataRoute } from "next";

/**
 * The authenticated app has no public, indexable URLs. Public discovery lives on
 * tradebud.xyz, whose sitemap is declared from this subdomain's robots file.
 */
export default function sitemap(): MetadataRoute.Sitemap {
  return [];
}
