import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import test from "node:test";

const templateRoot = new URL("../", import.meta.url);

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("http://localhost/", { headers: { accept: "text/html" } }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

test("server-renders the finished recommendation experience", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<html lang="zh-CN">/i);
  assert.match(html, /<title>北境市场雷达｜加拿大卡车市场机会推荐<\/title>/i);
  assert.match(html, /把运输需求/);
  assert.match(html, /生成市场建议/);
  assert.match(html, /美国出口加拿大 · 卡车运输/);
  assert.doesNotMatch(html, /codex-preview|Your site is taking shape|SkeletonPreview/i);
});

test("keeps secrets server-side and removes the disposable preview", async () => {
  const [recommendProxy, healthProxy, page, packageJson] = await Promise.all([
    readFile(new URL("../app/api/recommend/route.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/api/health/route.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../package.json", import.meta.url), "utf8"),
  ]);

  assert.match(recommendProxy, /RECOMMENDER_API_URL/);
  assert.match(healthProxy, /RECOMMENDER_API_URL/);
  assert.doesNotMatch(`${recommendProxy}${healthProxy}${page}`, /DEEPSEEK_API_KEY|NEXT_PUBLIC_/);
  assert.match(page, /market_trends/);
  assert.match(page, /SHAP 影响因素/);
  assert.doesNotMatch(packageJson, /react-loading-skeleton/);
  await assert.rejects(access(new URL("../app/_sites-preview", templateRoot)));
});
