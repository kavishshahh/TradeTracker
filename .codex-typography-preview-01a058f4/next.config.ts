import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  turbopack: {
    root: "C:/Users/kavis/OneDrive/Desktop/TradeTracker",
  },
  compress: true,
  poweredByHeader: false,
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-DNS-Prefetch-Control", value: "on" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        ],
      },
      ...["/sitemap.xml", "/robots.txt", "/feed.xml", "/llms.txt"].map((source) => ({
        source,
        headers: [{ key: "Cache-Control", value: "public, max-age=86400, s-maxage=86400" }],
      })),
    ];
  },
};

export default nextConfig;
