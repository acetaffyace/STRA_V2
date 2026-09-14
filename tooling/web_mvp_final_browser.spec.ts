import { test, expect } from "@playwright/test";

test("STEINS;GATE RE:BOOT final Web MVP smoke", async ({ page }) => {
  await page.goto("http://127.0.0.1:3000/dashboard?game=4012810");
  await expect(page.getByText("500", { exact: false }).first()).toBeVisible();
  await expect(page.getByText("live_provider", { exact: false })).toBeVisible();
  await expect(page.getByText("deepseek-v4-flash", { exact: false })).toBeVisible();
  await expect(page.getByText("82.6%", { exact: false })).toBeVisible();
  await expect(page.getByText("Current Snapshot", { exact: false })).toBeVisible();
  await expect(page.getByText("Unavailable", { exact: false })).not.toHaveCount(0);
});

test("quantitative-only exact run renders without semantic zeros or browser errors", async ({ page }) => {
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
  page.on("pageerror", (error) => pageErrors.push(error.message));

  const runId = "fixture-quantitative-only";
  const presentation = {
    schema_version: "dashboard-presentation-v1",
    run: { run_id: runId, app_id: 4012810, status: "completed", stale: false },
    readiness: { research_ready: true, semantic_ready: false, status: "ready" },
    research_snapshot: {
      population_n: 500,
      valid_n: 500,
      recommended_n: 460,
      not_recommended_n: 40,
      recommendation_rate: 0.92,
      collection_scope: { languages: ["all"], collection_order: "recent" },
      language_distribution: {},
      stage2e_activity: {},
    },
    semantic: { available: false, status: "unavailable", reason: "no_provider", limitations: [] },
    player_voice: {
      actionable_topics: { items: [], total_count: 0 },
      issues: { items: [], total_count: 0 },
      requests: { items: [], total_count: 0 },
      context_topics: { items: [], total_count: 0 },
      primary_topics: [],
    },
    discovery: { available: false, status: "unavailable", regions: [], interpretation: {} },
    evidence: { run_id: runId, endpoint: "/analysis/4012810/evidence", source_reviews_are_frozen: true },
    provenance: { run_id: runId },
    limitations: [],
    legacy: { available: false },
  };

  await page.route("**/runtime-info", async (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      runtime_profile: "integration",
      backend_port: 8000,
      capabilities: ["analysis-runs-active", "version-review-start", "exact-run-dashboard", "unified-global-queue"],
    }),
  }));
  await page.route("**/starred", async (route) => route.fulfill({ status: 200, contentType: "application/json", body: "[]" }));
  await page.route("**/analysis-runs/recent*", async (route) => route.fulfill({ status: 200, contentType: "application/json", body: "[]" }));
  await page.route("**/presentation/recent-analysis-summary*", async (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ projection: "recent_analysis_summary", projection_version: "fixture", items: [] }) }));
  await page.route("**/analysis/4012810/dashboard*", async (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      app_id: 4012810,
      readiness: {
        state: "ANALYSIS_READY",
        review_count: 500,
        classified_count: 0,
        classification_coverage: 0,
        run_id: runId,
        run_status: "completed",
        result_available: true,
        research_ready: true,
        semantic_ready: false,
        research_result_available: true,
        semantic_result_available: false,
        analysis_window: {},
        analysis_design_available: true,
        five_questions_available: false,
        evidence_available: false,
        research_engine: { available: true, status: "ready" },
        semantic_engine: { available: false, status: "unavailable", reason: "no_provider" },
      },
      metadata: { app_id: 4012810, retrieved: 500, analysis_population_count: 500, header_image: null },
      research_report: { schema_version: "research-report-v1" },
      insights: null,
      semantic_status: { status: "unavailable", reason: "no_provider" },
      reviews: [],
      run: { run_id: runId, app_id: 4012810, status: "completed", stale: false },
      presentation,
    }),
  }));

  await page.goto(`http://127.0.0.1:3000/dashboard?game=4012810&run=${runId}`);
  await expect(page.getByTestId("canonical-dashboard")).toBeVisible();
  await expect(page.getByText("500", { exact: false })).toBeVisible();
  await expect(page.getByText("92%", { exact: false })).toBeVisible();
  await expect(page.getByText("语义分析", { exact: false })).toBeVisible();
  await expect(page.getByText("未配置 LLM Provider", { exact: false })).toBeVisible();
  await expect(page.getByText("暂无语义分析结果", { exact: false })).toHaveCount(3);
  expect(consoleErrors).toEqual([]);
  expect(pageErrors).toEqual([]);
});
