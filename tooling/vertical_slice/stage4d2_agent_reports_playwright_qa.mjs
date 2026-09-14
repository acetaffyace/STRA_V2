import { chromium } from '../../.stage4c_playwright/node_modules/playwright/index.mjs';
import fs from 'node:fs/promises';
import path from 'node:path';

const base = process.env.STAGE4D2_BASE_URL || 'http://127.0.0.1:3000';
const out = path.resolve(process.cwd(), 'docs/stage4d/screenshots');
const runId = process.env.STAGE4D2_RUN_ID || 'b92ba25b9f9b4230945d8eb6f92126ff';
await fs.mkdir(out, { recursive: true });

const viewports = [
  { width: 1440, height: 900 },
  { width: 1366, height: 768 },
  { width: 1024, height: 768 },
];

const browser = await chromium.launch({ headless: true });
const results = [];

async function inspect(name, url, viewport, expected) {
  const page = await browser.newPage({ viewport });
  const consoleErrors = [];
  const pageErrors = [];
  const failedResponses = [];
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text());
  });
  page.on('pageerror', (error) => pageErrors.push(String(error)));
  page.on('response', (response) => {
    if (response.status() >= 400) failedResponses.push(`${response.status()} ${response.url()}`);
  });
  await page.goto(`${base}${url}`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(5000);
  const bodyText = await page.locator('body').innerText();
  const file = path.join(out, `stage4d2-${name}-${viewport.width}x${viewport.height}.png`);
  await page.screenshot({ path: file, fullPage: true });
  results.push({
    name,
    viewport,
    screenshot: file,
    expected: expected.every((text) => bodyText.includes(text)),
    rendered: bodyText.length > 100,
    noHorizontalOverflow: await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
    consoleErrors,
    pageErrors,
    failedResponses,
  });
  await page.close();
}

for (const viewport of viewports) {
  await inspect('chat', `/chat?game=553850&run=${runId}`, viewport, ['STRA']);
  await inspect('reports', `/reports?game=553850&run=${runId}`, viewport, ['报告']);
}

const failed = results.some((item) =>
  !item.expected || !item.rendered || !item.noHorizontalOverflow ||
  item.consoleErrors.length || item.pageErrors.length || item.failedResponses.length,
);
const summary = { runId, results, failed };
await fs.writeFile(path.join(out, 'stage4d2-agent-reports-qa.json'), JSON.stringify(summary, null, 2));
console.log(JSON.stringify(summary, null, 2));
await browser.close();
if (failed) process.exitCode = 1;
