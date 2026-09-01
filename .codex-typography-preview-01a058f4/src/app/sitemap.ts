import type { MetadataRoute } from "next";
import { articles } from "../content/articles.ts";
import { glossary } from "../content/glossary.ts";
import { tools } from "../content/tools.ts";

const lastModified = new Date("2026-08-31T00:00:00.000Z");

export default function sitemap(): MetadataRoute.Sitemap {
  const corePages: MetadataRoute.Sitemap = [
    { url: "https://tradebud.xyz", lastModified, changeFrequency: "weekly", priority: 1 },
    { url: "https://tradebud.xyz/free-trading-journal", lastModified, changeFrequency: "monthly", priority: 0.9 },
    { url: "https://tradebud.xyz/blog", lastModified, changeFrequency: "weekly", priority: 0.8 },
    { url: "https://tradebud.xyz/tools", lastModified, changeFrequency: "monthly", priority: 0.9 },
    { url: "https://tradebud.xyz/methodology", lastModified, changeFrequency: "monthly", priority: 0.8 },
    { url: "https://tradebud.xyz/glossary", lastModified, changeFrequency: "monthly", priority: 0.8 },
    { url: "https://tradebud.xyz/about", lastModified, changeFrequency: "yearly", priority: 0.6 },
    { url: "https://tradebud.xyz/privacy", lastModified, changeFrequency: "yearly", priority: 0.4 },
    { url: "https://tradebud.xyz/terms", lastModified, changeFrequency: "yearly", priority: 0.4 },
  ];

  const articlePages: MetadataRoute.Sitemap = articles.map((article) => ({
    url: `https://tradebud.xyz/blog/${article.slug}`,
    lastModified: new Date(`${article.updated}T00:00:00.000Z`),
    changeFrequency: "monthly",
    priority: 0.7,
  }));

  const toolPages: MetadataRoute.Sitemap = tools.map((tool) => ({
    url: `https://tradebud.xyz/tools/${tool.slug}`,
    lastModified: new Date(`${tool.updated}T00:00:00.000Z`),
    changeFrequency: "monthly",
    priority: 0.8,
  }));

  const glossaryPages: MetadataRoute.Sitemap = glossary.map((entry) => ({
    url: `https://tradebud.xyz/glossary/${entry.slug}`,
    lastModified: new Date(`${entry.updated}T00:00:00.000Z`),
    changeFrequency: "monthly",
    priority: 0.7,
  }));

  return [...corePages, ...articlePages, ...toolPages, ...glossaryPages];
}
