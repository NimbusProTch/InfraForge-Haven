/**
 * Full enterprise-grade UI sweep — visit every relevant page after login,
 * snap screenshot, capture console errors + network failures, write a
 * per-page report.
 *
 * Run: `npx playwright test --config=playwright.demo.config.ts tests/demo-ui-sweep.spec.ts`
 *
 * Output: `playwright-report-demo/screens/sweep-<page>.png` + `sweep-report.json`
 */
import { test, expect, type Page, type Response, type Request } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";
import { login, snap, UI } from "./demo-helpers";

interface PageReport {
  url: string;
  httpStatus: number;
  loadTimeMs: number;
  consoleErrors: string[];
  networkFailures: { method: string; url: string; status: number; reason: string }[];
  screenshot: string;
  notes: string[];
}

const TARGET_URLS: { path: string; description: string; waitFor?: string }[] = [
  { path: "/", description: "root → redirects to dashboard" },
  { path: "/dashboard", description: "main dashboard" },
  { path: "/tenants", description: "tenants list (Projects)" },
  { path: "/tenants/new", description: "new tenant wizard" },
  { path: "/tenants/demo", description: "demo tenant overview" },
  { path: "/tenants/demo?tab=apps", description: "demo tenant Apps tab" },
  { path: "/tenants/demo?tab=services", description: "demo tenant Services tab" },
  { path: "/tenants/demo?tab=settings", description: "demo tenant Settings tab" },
  { path: "/tenants/demo/apps/new", description: "new app wizard step 1" },
  { path: "/tenants/demo/apps/demo-api", description: "demo-api detail Overview" },
  { path: "/tenants/demo/apps/demo-api?tab=deployments", description: "demo-api Deployments" },
  { path: "/tenants/demo/apps/demo-api?tab=variables", description: "demo-api Variables" },
  { path: "/tenants/demo/apps/demo-api?tab=logs", description: "demo-api Logs (SSE)" },
  { path: "/tenants/demo/apps/demo-api?tab=metrics", description: "demo-api Metrics" },
  { path: "/tenants/demo/apps/demo-api?tab=settings", description: "demo-api Settings" },
  { path: "/tenants/demo/apps/demo-ui", description: "demo-ui detail Overview" },
  { path: "/tenants/demo/apps/demo-ui?tab=deployments", description: "demo-ui Deployments" },
  { path: "/organizations", description: "organizations list" },
  { path: "/platform/queue", description: "platform queue page" },
];

const IGNORED_CONSOLE_PATTERNS = [
  /favicon/i,
  /ERR_BLOCKED_BY_CLIENT/i, // ad-block
  /Failed to load resource.*404.*\.png/i, // missing icons
  /404.*\/_next\/data\//i, // Next.js prefetch noise
  /Download the React DevTools/i,
  /\[next-auth\]\[debug\]/i,
];

test.describe.serial("UI sweep — every page, every modal, console + network capture", () => {
  test.setTimeout(300_000); // 5 min total budget

  test("sweep all pages", async ({ page }) => {
    await login(page);
    const reports: PageReport[] = [];
    const reportsDir = path.resolve("playwright-report-demo/screens");
    fs.mkdirSync(reportsDir, { recursive: true });

    for (const target of TARGET_URLS) {
      const consoleErrors: string[] = [];
      const networkFailures: PageReport["networkFailures"] = [];

      const consoleHandler = (msg: any) => {
        if (msg.type() === "error") {
          const txt = msg.text();
          if (!IGNORED_CONSOLE_PATTERNS.some((p) => p.test(txt))) {
            consoleErrors.push(txt.substring(0, 300));
          }
        }
      };
      const respHandler = (res: Response) => {
        const url = res.url();
        const status = res.status();
        const isOurApi =
          url.includes("api.iyziops.com") ||
          url.includes("iyziops.com/api/") ||
          url.includes(UI);
        if (status >= 400 && isOurApi && !url.includes("/api/auth/")) {
          networkFailures.push({
            method: res.request().method(),
            url: url.length > 120 ? url.substring(0, 120) + "..." : url,
            status,
            reason: res.statusText() || "",
          });
        }
      };
      const reqFailedHandler = (req: Request) => {
        networkFailures.push({
          method: req.method(),
          url: req.url(),
          status: 0,
          reason: req.failure()?.errorText || "request failed",
        });
      };
      page.on("console", consoleHandler);
      page.on("response", respHandler);
      page.on("requestfailed", reqFailedHandler);

      const fullUrl = `${UI}${target.path}`;
      const t0 = Date.now();
      let httpStatus = 0;
      const notes: string[] = [];
      try {
        const resp = await page.goto(fullUrl, { waitUntil: "networkidle", timeout: 25_000 });
        httpStatus = resp?.status() || 0;
        // Settle — wait for any async loaders to finish
        await page.waitForTimeout(1500);
      } catch (e: any) {
        notes.push(`goto failed: ${e.message.substring(0, 200)}`);
      }
      const loadTimeMs = Date.now() - t0;

      const slug = target.path.replace(/[/?=&]/g, "_").replace(/^_/, "") || "root";
      const screenshotName = `sweep-${slug}.png`;
      try {
        await page.screenshot({
          path: path.join(reportsDir, screenshotName),
          fullPage: true,
          timeout: 10_000,
        });
      } catch (e: any) {
        notes.push(`screenshot failed: ${e.message.substring(0, 100)}`);
      }

      reports.push({
        url: target.path,
        httpStatus,
        loadTimeMs,
        consoleErrors,
        networkFailures,
        screenshot: screenshotName,
        notes,
      });

      page.off("console", consoleHandler);
      page.off("response", respHandler);
      page.off("requestfailed", reqFailedHandler);

      console.log(
        `[${target.path}] HTTP ${httpStatus} ${loadTimeMs}ms — console errors: ${consoleErrors.length}, network failures: ${networkFailures.length}`
      );
    }

    // Write JSON report
    fs.writeFileSync(
      path.join(reportsDir, "sweep-report.json"),
      JSON.stringify(reports, null, 2)
    );

    // Summary table to stdout
    console.log("\n========== UI SWEEP SUMMARY ==========");
    console.log("PATH                                                HTTP   ms    console  network");
    for (const r of reports) {
      const url = r.url.padEnd(50);
      const status = String(r.httpStatus).padEnd(4);
      const ms = String(r.loadTimeMs).padEnd(5);
      const ce = String(r.consoleErrors.length).padEnd(8);
      const nf = String(r.networkFailures.length);
      console.log(`${url} ${status}  ${ms}  ${ce}  ${nf}`);
    }
    console.log("=======================================");

    // Highlight problems
    const broken = reports.filter(
      (r) => r.httpStatus >= 400 || r.consoleErrors.length > 0 || r.networkFailures.length > 0 || r.notes.length > 0
    );
    if (broken.length > 0) {
      console.log("\n⚠️  Pages with issues:");
      for (const r of broken) {
        console.log(`\n  ${r.url}`);
        if (r.httpStatus >= 400) console.log(`    HTTP: ${r.httpStatus}`);
        for (const ce of r.consoleErrors.slice(0, 3)) console.log(`    console: ${ce}`);
        for (const nf of r.networkFailures.slice(0, 3))
          console.log(`    network: ${nf.method} ${nf.url} → ${nf.status} ${nf.reason}`);
        for (const n of r.notes) console.log(`    note: ${n}`);
      }
    } else {
      console.log("\n✅ All pages clean!");
    }

    // The test itself never fails — sweep is observational. Run shows results in stdout
    // and a JSON file. Decision on what to fix is made by reading the report.
    expect(reports.length).toBe(TARGET_URLS.length);
  });
});
