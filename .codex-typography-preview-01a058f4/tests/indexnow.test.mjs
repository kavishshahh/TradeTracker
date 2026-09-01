import assert from "node:assert/strict";
import test from "node:test";
import { normalizeIndexableUrls } from "../scripts/submit-indexnow.mjs";

test("normalizeIndexableUrls keeps unique URLs on the configured origin", () => {
  const entries = [
    { url: "https://tradebud.xyz/" },
    { url: "https://tradebud.xyz/blog/example" },
    { url: "https://tradebud.xyz/blog/example" },
    { url: "https://app.tradebud.xyz/login" },
  ];

  assert.deepEqual(normalizeIndexableUrls(entries, "https://tradebud.xyz"), [
    "https://tradebud.xyz",
    "https://tradebud.xyz/blog/example",
  ]);
});

test("normalizeIndexableUrls preserves URL query parameters", () => {
  assert.deepEqual(normalizeIndexableUrls([
    { url: "https://tradebud.xyz/search?q=one&page=2" },
  ], "https://tradebud.xyz"), [
    "https://tradebud.xyz/search?q=one&page=2",
  ]);
});
