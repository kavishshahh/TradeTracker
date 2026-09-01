import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "TradeBud — Free Trading Journal",
    short_name: "TradeBud",
    description: "A completely free trading journal and performance analytics application.",
    start_url: "/",
    display: "standalone",
    background_color: "#f4f1e9",
    theme_color: "#1f6b46",
    categories: ["finance", "business", "productivity"],
    lang: "en",
  };
}
