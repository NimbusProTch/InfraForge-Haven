import { type APIRequestContext } from "@playwright/test";

const API_URL = process.env.API_URL || "http://localhost:8000";
const KC_URL = process.env.KC_URL || "https://keycloak.iyziops.com";

/**
 * Get a Keycloak access token for API calls.
 */
export async function getApiToken(request: APIRequestContext): Promise<string> {
  const resp = await request.post(
    `${KC_URL}/realms/haven/protocol/openid-connect/token`,
    {
      form: {
        grant_type: "password",
        client_id: "haven-api",
        username: process.env.KC_USER || "testuser",
        password: process.env.KC_PASS || "test123456",
      },
    }
  );
  const data = await resp.json();
  if (!data.access_token) throw new Error(`Auth failed: ${data.error_description || "unknown"}`);
  return data.access_token;
}

/**
 * Make an authenticated API call.
 */
export async function apiCall(
  request: APIRequestContext,
  method: string,
  path: string,
  token: string,
  body?: unknown
) {
  const url = `${API_URL}/api/v1${path}`;
  const headers = { Authorization: `Bearer ${token}` };

  if (method === "GET") return request.get(url, { headers });
  if (method === "POST") return request.post(url, { headers, data: body });
  if (method === "PATCH") return request.patch(url, { headers, data: body });
  if (method === "DELETE") return request.delete(url, { headers });
  throw new Error(`Unknown method: ${method}`);
}

/**
 * Cleanup: delete a tenant (ignores 404).
 */
export async function cleanupTenant(request: APIRequestContext, token: string, slug: string) {
  await apiCall(request, "DELETE", `/tenants/${slug}`, token);
}
