import { chromium } from '../../.stage4c_playwright/node_modules/playwright/index.mjs';
import fs from 'node:fs/promises';
import path from 'node:path';

const base = 'http://127.0.0.1:3000';
const run = 'b92ba25b9f9b4230945d8eb6f92126ff';
const out = path.resolve(process.cwd(), '.stage4c_runtime', 'qa');
await fs.mkdir(out, { recursive: true });

const browser = await chromium.launch({ headless: true });
const results = [];
for (const viewport of [{ width: 1440, height: 900 }, { width: 1366, height: 768 }, { width: 1024, height: 768 }]) {
  const page = await browser.newPage({ viewport });
  const consoleErrors = [];
  const pageErrors = [];
  const failedResponses = [];
  page.on('console', (message) => { if (message.type() === 'error') consoleErrors.push(message.text()); });
  page.on('pageerror', (error) => pageErrors.push(String(error)));
  page.on('response', (response) => { if (response.status() >= 400) failedResponses.push(`${response.status()} ${response.url()}`); });
  const suffix = `${viewport.width}x${viewport.height}`;

  await page.goto(`${base}/dashboard?game=553850&run=${run}`, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForTimeout(3000);
  await page.screenshot({ path: `${out}/loop1-dashboard-${suffix}.png`, fullPage: true });
  const dashboardText = await page.locator('body').innerText();
  const structural = {
    hasGame: dashboardText.includes('HELLDIVERS 2'),
    hasProvisional: dashboardText.includes('暂定结果'),
    hasCoverage: dashboardText.includes('80 / 80'),
    hasTopics: dashboardText.includes('主要讨论内容') || dashboardText.includes('玩家关注'),
    hasIssues: dashboardText.includes('主要问题'),
    hasRequests: dashboardText.includes('玩家需求'),
    hasContext: dashboardText.includes('其他内容'),
    hidesTechnicalTerms: !dashboardText.includes('ClassificationMaterialization') && !dashboardText.includes('Semantic geometry') && !dashboardText.includes('Details & provenance'),
  };

  await page.locator('[data-testid="canonical-dashboard"]').scrollIntoViewIfNeeded();
  await page.waitForTimeout(200);
  await page.screenshot({ path: `${out}/loop2-dashboard-${suffix}.png`, fullPage: true });
  const hierarchy = { provisionalIndex: dashboardText.indexOf('暂定结果'), topicIndex: Math.max(dashboardText.indexOf('主要讨论内容'), dashboardText.indexOf('玩家关注')) };

  const setupButton = page.getByRole('button', { name: /更新分析|分析设置/ }).first();
  if (await setupButton.count()) {
    await setupButton.click();
    await page.waitForTimeout(250);
    await page.screenshot({ path: `${out}/loop3-setup-${suffix}.png`, fullPage: true });
    await page.getByRole('button', { name: 'Close' }).click();
  }

  const reviewsLink = page.locator(`a[href*="/reviews?"][href*="run=${run}"]`).first();
  if (await reviewsLink.count()) {
    await reviewsLink.click();
    await page.waitForTimeout(2500);
    await page.screenshot({ path: `${out}/loop3-reviews-${suffix}.png`, fullPage: true });
    const reviewText = await page.locator('body').innerText();
    const pagination = reviewText.includes('上一页') && reviewText.includes('下一页');
    const reviewLink = page.locator('button').filter({ hasText: '下一页' }).first();
    if (await reviewLink.count() && await reviewLink.isEnabled()) {
      await reviewLink.click();
      await page.waitForTimeout(500);
      await page.screenshot({ path: `${out}/loop3-reviews-page2-${suffix}.png`, fullPage: true });
    }
    results.push({ viewport, reviewUrl: page.url(), pagination });
  }
  results.push({ viewport, structural, hierarchy, consoleErrors, pageErrors, failedResponses, url: page.url() });
  await page.close();
}
await browser.close();
await fs.writeFile(`${out}/qa.json`, JSON.stringify({ results }, null, 2));
console.log(JSON.stringify({ results }, null, 2));
