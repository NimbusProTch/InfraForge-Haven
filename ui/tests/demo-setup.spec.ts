/**
 * Demo setup — via API (fast path):
 *  1. Create "demo" tenant
 *  2. Create demo-pg / demo-cache / demo-queue services
 *  3. Wait all 3 READY
 *
 * Via API because services take 3-5 min to ready; waiting in a browser test
 * is fragile. Browser flow is in demo-full-journey.spec.ts (apps wizard).
 */
import { test, expect } from "@playwright/test";
import { apiCall, waitFor, TENANT_SLUG } from "./demo-helpers";

test.describe.serial("Demo — tenant + services setup", () => {
  test.setTimeout(600_000);

  test("1. ensure demo tenant exists", async () => {
    const { status } = await apiCall("POST", "/api/v1/tenants", {
      slug: TENANT_SLUG,
      name: "iyziops Demo",
    });
    expect([201, 409]).toContain(status);
  });

  const SERVICES = [
    { name: "demo-pg", type: "postgres" },
    { name: "demo-cache", type: "redis" },
    { name: "demo-queue", type: "rabbitmq" },
  ];

  for (const svc of SERVICES) {
    test(`2. create ${svc.name}`, async () => {
      const { status } = await apiCall("POST", `/api/v1/tenants/${TENANT_SLUG}/services`, {
        name: svc.name,
        service_type: svc.type,
        tier: "dev",
      });
      expect([201, 409]).toContain(status);
    });
  }

  test("3. all services reach ready", async () => {
    await waitFor(
      async () => {
        const { data } = await apiCall<any[]>("GET", `/api/v1/tenants/${TENANT_SLUG}/services`);
        if (!Array.isArray(data)) return false;
        const demoSvcs = data.filter((s) => SERVICES.some((x) => x.name === s.name));
        const readyCount = demoSvcs.filter((s) => s.status === "ready").length;
        console.log(`[services] ${readyCount}/${SERVICES.length} ready`);
        return readyCount === SERVICES.length;
      },
      { timeout: 540_000, interval: 15_000, label: "all 3 demo services ready" },
    );
  });
});
