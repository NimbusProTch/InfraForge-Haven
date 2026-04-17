/**
 * Journey: ALL 6 Managed Service Types — Create → Wait Ready → Delete
 *
 * Added 2026-04-18 overnight sprint. Supplements journey-services.spec.ts
 * (which only covers Redis + PG) to give one test per provisioner:
 *
 *   - PostgreSQL  (Everest → CNPG)
 *   - MySQL       (Everest → Percona XtraDB)
 *   - MongoDB     (Everest → Percona PSMDB)
 *   - Redis       (OpsTree operator, direct CRD)
 *   - RabbitMQ    (RabbitMQ cluster operator, direct CRD)
 *   - Kafka       (Strimzi operator, direct CRD, with PSA-compliant pod template)
 *
 * Uses a unique tenant slug (suffix timestamp) so runs don't collide.
 *
 * Real cluster, real Keycloak, NO mocks.
 */
import { test, expect } from "@playwright/test";
import { UI, apiCall, waitFor } from "./journey-helpers";

// Unique per-run tenant to avoid collision with journey-services.spec.ts.
const TENANT_SLUG = `svc-all-${Math.floor(Date.now() / 1000) % 100000}`;

const SERVICES: Array<{ name: string; type: string; readyTimeoutMs: number }> = [
  { name: "pg1", type: "postgres", readyTimeoutMs: 240_000 },
  { name: "mysql1", type: "mysql", readyTimeoutMs: 300_000 },
  { name: "mongo1", type: "mongodb", readyTimeoutMs: 240_000 },
  { name: "redis1", type: "redis", readyTimeoutMs: 60_000 },
  { name: "rabbit1", type: "rabbitmq", readyTimeoutMs: 180_000 },
  { name: "kafka1", type: "kafka", readyTimeoutMs: 300_000 },
];

test.describe.serial(`Journey: All Managed Service Types (${TENANT_SLUG})`, () => {
  test.setTimeout(360_000);

  test.beforeAll(async () => {
    const { status } = await apiCall("POST", "/tenants", {
      name: `All Services ${TENANT_SLUG}`,
      slug: TENANT_SLUG,
    });
    expect([201, 409]).toContain(status);
  });

  // One create/wait test per service, serial so cluster isn't slammed.
  for (const svc of SERVICES) {
    test(`${svc.type} — create`, async () => {
      const { status } = await apiCall("POST", `/tenants/${TENANT_SLUG}/services`, {
        name: svc.name,
        service_type: svc.type,
        tier: "dev",
      });
      expect([201, 409]).toContain(status);
    });

    test(`${svc.type} — reaches ready`, async () => {
      test.setTimeout(svc.readyTimeoutMs + 30_000);
      await waitFor(
        async () => {
          const { data } = await apiCall("GET", `/tenants/${TENANT_SLUG}/services/${svc.name}`);
          return data?.status === "ready";
        },
        { timeout: svc.readyTimeoutMs, interval: 15_000 },
      );
    });

    test(`${svc.type} — credentials endpoint returns 200`, async () => {
      const { status, data } = await apiCall("GET", `/tenants/${TENANT_SLUG}/services/${svc.name}/credentials`);
      expect(status).toBe(200);
      // At minimum one non-empty credential value
      const creds = data.credentials ?? data;
      expect(Object.keys(creds).length).toBeGreaterThan(0);
    });
  }

  // Cleanup all services (best-effort, don't fail the whole suite if one 404s)
  test("cleanup — delete all services", async () => {
    for (const svc of SERVICES) {
      await apiCall("DELETE", `/tenants/${TENANT_SLUG}/services/${svc.name}`);
    }
  });
});
