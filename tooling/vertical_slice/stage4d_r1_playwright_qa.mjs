import { chromium } from '../../.stage4c_playwright/node_modules/playwright/index.mjs';
import fs from 'node:fs/promises';
import path from 'node:path';

const base = process.env.STAGE4D_BASE_URL || 'http://127.0.0.1:3000';
const out = path.resolve(process.cwd(), '.stage4d_runtime2', 'r1-qa');
await fs.mkdir(out, { recursive: true });

const viewports = [
  { width: 1440, height: 900 },
  { width: 1366, height: 768 },
  { width: 1024, height: 768 },
];

const browser = await chromium.launch({ headless: true });
const results = [];

async function inspect({ name, url, viewport, failCanonical = false, expectedText, forbiddenText }) {
  const page = await browser.newPage({ viewport });
  const consoleErrors = [];
  const pageErrors = [];
  const failedResponses = [];
  page.on('console', (message) => { if (message.type() === 'error') consoleErrors.push(message.text()); });
  page.on('pageerror', (error) => pageErrors.push(String(error)));
  page.on('response', (response) => {
    if (response.status() >= 400) failedResponses.push(`${response.status()} ${response.url()}`);
  });
  if (failCanonical) {
    await page.route('**/*', async (route) => {
      if (route.request().url().includes('/comparison')) return route.abort();
      return route.continue();
    });
  }
  await page.goto(`${base}${url}`, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForTimeout(2200);
  const bodyText = await page.locator('body').innerText();
  const screenshot = path.join(out, `${name}-${failCanonical ? 'unavailable' : 'success'}-${viewport.width}x${viewport.height}.png`);
  await page.screenshot({ path: screenshot, fullPage: true });
  const expected = bodyText.includes(expectedText);
  const forbidden = forbiddenText ? bodyText.includes(forbiddenText) : false;
  const unexpectedConsoleErrors = consoleErrors.filter((message) => !(failCanonical && message.includes('ERR_FAILED')));
  results.push({
    name,
    viewport,
    failCanonical,
    screenshot,
    expected,
    forbidden,
    rendered: bodyText.length > 100,
    noHorizontalOverflow: await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
    consoleErrors: unexpectedConsoleErrors,
    pageErrors,
    failedResponses: failedResponses.filter((item) => !(failCanonical && item.includes('/comparison'))),
  });
  await page.close();
}

for (const viewport of viewports) {
  await inspect({
    name: 'compare',
    url: '/compare',
    viewport,
    expectedText: 'Filtered descriptive view',
  });
  await inspect({
    name: 'version-review',
    url: '/version-review?run=stage4d-version-run',
    viewport,
    expectedText: '推荐率变化：+5.0pp',
  });
}

await inspect({
  name: 'compare',
  url: '/compare',
  viewport: viewports[0],
  failCanonical: true,
  expectedText: 'Official comparison is unavailable',
});
await inspect({
  name: 'version-review',
  url: '/version-review?run=stage4d-version-run',
  viewport: viewports[0],
  failCanonical: true,
  expectedText: '无法读取这次分析的正式对比结果。',
  forbiddenText: '推荐率变化：+5.0pp',
});

const canonical = await fetch(`${process.env.STAGE4D_API_BASE_URL || 'http://127.0.0.1:8000'}/comparison?left_run=b92ba25b9f9b4230945d8eb6f92126ff&right_run=stage4d-right-run`).then((response) => response.json());
const exactSideIsolation = canonical.left.source_id === 'b92ba25b9f9b4230945d8eb6f92126ff' && canonical.right.source_id === 'stage4d-right-run';
const semanticMismatchFailClosed = canonical.compatibility.semantic_delta_comparable === false && canonical.semantic.delta === null;
const failed = results.some((item) => !item.rendered || !item.expected || item.forbidden || !item.noHorizontalOverflow || item.consoleErrors.length || item.pageErrors.length || item.failedResponses.length) || !exactSideIsolation || !semanticMismatchFailClosed;
const summary = { results, exactSideIsolation, semanticMismatchFailClosed, failed };
await fs.writeFile(path.join(out, 'qa.json'), JSON.stringify(summary, null, 2));
console.log(JSON.stringify(summary, null, 2));
await browser.close();
if (failed) process.exitCode = 1;
