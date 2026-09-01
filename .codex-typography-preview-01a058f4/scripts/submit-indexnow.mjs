import { readFile, readdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const DEFAULT_ORIGIN = "https://tradebud.xyz";
const INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow";
const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const publicDirectory = path.resolve(scriptDirectory, "../public");

export function normalizeIndexableUrls(entries, origin) {
  const expectedOrigin = new URL(origin).origin;
  const urls = entries
    .map((entry) => new URL(entry.url))
    .filter((url) => url.origin === expectedOrigin)
    .map((url) => url.href.replace(/\/$/, (slash) => url.pathname === "/" ? "" : slash));

  return [...new Set(urls)];
}

async function readIndexNowKey() {
  const files = await readdir(publicDirectory);
  const candidates = files.filter((file) => /^[a-z0-9-]{8,128}\.txt$/i.test(file));

  for (const file of candidates) {
    const key = (await readFile(path.join(publicDirectory, file), "utf8")).trim();
    if (`${key}.txt` === file) return key;
  }

  throw new Error("No valid IndexNow key file was found in public/. The filename must be <key>.txt and its contents must exactly match <key>.");
}

async function main() {
  const dryRun = process.argv.includes("--dry-run");
  const origin = new URL(process.env.INDEXNOW_ORIGIN || DEFAULT_ORIGIN).origin;
  const key = await readIndexNowKey();
  const { default: sitemap } = await import("../src/app/sitemap.ts");
  const urlList = normalizeIndexableUrls(sitemap(), origin);
  if (urlList.length === 0) throw new Error(`The sitemap contains no ${origin} URLs.`);
  if (urlList.length > 10_000) throw new Error("IndexNow accepts at most 10,000 URLs per request.");

  const payload = {
    host: new URL(origin).host,
    key,
    keyLocation: `${origin}/${key}.txt`,
    urlList,
  };

  if (dryRun) {
    console.log(JSON.stringify(payload, null, 2));
    return;
  }

  const response = await fetch(INDEXNOW_ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/json; charset=utf-8" },
    body: JSON.stringify(payload),
  });

  if (![200, 202].includes(response.status)) {
    const responseBody = await response.text();
    throw new Error(`IndexNow rejected the submission: HTTP ${response.status}${responseBody ? ` — ${responseBody}` : ""}`);
  }

  console.log(`IndexNow accepted ${urlList.length} URLs (HTTP ${response.status}).`);
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.message : error);
    process.exitCode = 1;
  });
}
