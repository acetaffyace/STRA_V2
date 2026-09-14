import { chromium } from '../../.stage4c_playwright/node_modules/playwright/index.mjs';
import fs from 'node:fs/promises';
import path from 'node:path';

const base = process.env.STAGE4D_BASE_URL || 'http://127.0.0.1:3000';
const out = path.resolve(process.cwd(), 'docs', 'stage4d', 'screenshots');
await fs.mkdir(out, { recursive: true });

const viewports = [
  { width: 1440, height: 900 },
  { width: 1366, height: 768 },
  { width: 1024, height: 768 },
];

const browser = await chromium.launch({ headless: true });
const results = [];

async function inspectPage(page, pageName, state, viewport, loop) {
  const consoleErrors = [];
  const pageErrors = [];
  const failedResponses = [];
  page.on('console', (message) => { if (message.type() === 'error') consoleErrors.push(message.text()); });
  page.on('pageerror', (error) => pageErrors.push(String(error)));
  page.on('response', (response) => { if (response.status() >= 400) failedResponses.push(`${response.status()} ${response.url()}`); });
  await page.goto(`${base}${pageName}`, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForTimeout(2500);
  const bodyText = await page.locator('body').innerText();
  const screenshot = path.join(out, `${state}-loop${loop}-${viewport.width}x${viewport.height}.png`);
  await page.screenshot({ path: screenshot, fullPage: true });
  return {
    viewport,
    state,
    loop,
    screenshot,
    consoleErrors,
    pageErrors,
    failedResponses,
    checks: {
      rendered: bodyText.length > 100,
      noHorizontalOverflow: await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
      hasComparisonSurface: bodyText.includes('游戏对比') || bodyText.includes('Game Comparison'),
      hasVersionSurface: bodyText.includes('版本复盘') || bodyText.includes('Version Review'),
      hasCanonicalWarningOrMetric: bodyText.includes('推荐率') || bodyText.includes('Recommendation'),
    },
  };
}

for (const viewport of viewports) {
  for (const loop of [1, 2, 3]) {
    const comparePage = await browser.newPage({ viewport });
    results.push(await inspectPage(comparePage, '/compare', 'compare', viewport, loop));
    await comparePage.close();

    const versionPage = await browser.newPage({ viewport });
    results.push(await inspectPage(versionPage, '/version-review?run=stage4d-version-run', 'version-review', viewport, loop));
    await versionPage.close();
  }
}

await browser.close();
await fs.writeFile(path.join(out, 'qa.json'), JSON.stringify({ results }, null, 2));
console.log(JSON.stringify({ results }, null, 2));
