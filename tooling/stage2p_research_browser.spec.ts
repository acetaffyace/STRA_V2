import { test, expect } from "@playwright/test";

/**
 * Stage 1–2P Final Seal browser smoke.
 *
 * Run against a local deterministic fixture (the URL may be overridden with
 * STAGE2P_RESEARCH_BROWSER_URL). The fixture represents a completed
 * quantitative-only result: research_report is present, insights is null, and
 * semantic_status is unavailable/no_provider. This smoke intentionally does
 * not require Steam or an LLM provider.
 */
test("quantitative-only Research Core Dashboard is usable without semantic insights", async ({ page }) => {
  const url = process.env.STAGE2P_RESEARCH_BROWSER_URL
    ?? "http://127.0.0.1:3000/dashboard?game=29001";
  await page.goto(url);

  await expect(page.getByText("Research Core", { exact: false }).first()).toBeVisible();
  await expect(page.getByText(/Quantitative Research Overview|定量研究概览/).first()).toBeVisible();
  await expect(page.getByText(/Recommendation Rate|Steam 推荐率/).first()).toBeVisible();
  await expect(page.getByText(/Observed Reviews|观测评论数/).first()).toBeVisible();
  await expect(page.getByText(/Collection Status|采集状态/).first()).toBeVisible();
  await expect(page.getByText(/Semantic Analysis|语义分析/).first()).toBeVisible();
  await expect(page.getByText(/UNAVAILABLE|不可用/).first()).toBeVisible();
  await expect(page.getByText(/Wilson|模型假设下/).first()).toBeVisible();
  await expect(page.getByText(/Unique Text|唯一文本/).first()).toBeVisible();

  // Research-only runs must not be blocked by the old semantic readiness gate.
  await expect(page.getByText(/分析尚未就绪|analysis not ready/i)).toHaveCount(0);

  // Semantic widgets are unavailable, not observed zeros.
  await expect(page.getByText(/Issue Rate 0%|Request Rate 0%|问题率 0%|请求率 0%/i)).toHaveCount(0);
});
