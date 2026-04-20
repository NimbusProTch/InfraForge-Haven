/**
 * NextAuth configuration — Keycloak OIDC + optional GitHub OAuth.
 *
 * Features:
 * - Automatic token refresh via Keycloak refresh_token
 * - Sliding session window (refreshes 1 min before expiry)
 * - Access token forwarded to API via session.accessToken
 * - Error state on refresh failure → forces re-login
 */
import type { NextAuthOptions } from "next-auth";
import KeycloakProvider from "next-auth/providers/keycloak";
import GitHubProvider from "next-auth/providers/github";

const KC_URL = process.env.KEYCLOAK_URL!;
const KC_REALM = process.env.KEYCLOAK_REALM ?? "haven";
const KC_CLIENT_ID = process.env.KEYCLOAK_CLIENT_ID!;
const KC_CLIENT_SECRET = process.env.KEYCLOAK_CLIENT_SECRET!;

// Must match api/app/deps.py:PLATFORM_ADMIN_ROLE. Keycloak JWTs carry
// realm-level roles under `realm_access.roles`.
const PLATFORM_ADMIN_ROLE = "platform-admin";

/**
 * Decode a JWT payload without verification. We only use this to surface
 * the `realm_access.roles` claim to the React tree — the backend is the
 * source of truth for authorization and verifies the signature on every
 * request. This is read-only UI affordance, never a security gate.
 */
function decodeJwtPayload(jwt: string | undefined): Record<string, unknown> | null {
  if (!jwt) return null;
  const parts = jwt.split(".");
  if (parts.length !== 3) return null;
  try {
    const payload = Buffer.from(
      parts[1].replace(/-/g, "+").replace(/_/g, "/"),
      "base64"
    ).toString("utf-8");
    return JSON.parse(payload) as Record<string, unknown>;
  } catch {
    return null;
  }
}

function isPlatformAdmin(accessToken: string | undefined): boolean {
  const payload = decodeJwtPayload(accessToken);
  if (!payload) return false;
  const realmAccess = payload["realm_access"];
  if (!realmAccess || typeof realmAccess !== "object") return false;
  const roles = (realmAccess as { roles?: unknown }).roles;
  return Array.isArray(roles) && roles.includes(PLATFORM_ADMIN_ROLE);
}

const providers: NextAuthOptions["providers"] = [
  KeycloakProvider({
    clientId: KC_CLIENT_ID,
    clientSecret: KC_CLIENT_SECRET,
    issuer: `${KC_URL}/realms/${KC_REALM}`,
  }),
];

// GitHub OAuth is optional — only enabled when credentials are configured
if (process.env.GITHUB_ID && process.env.GITHUB_SECRET) {
  providers.push(
    GitHubProvider({
      clientId: process.env.GITHUB_ID,
      clientSecret: process.env.GITHUB_SECRET,
      authorization: { params: { scope: "read:user user:email repo" } },
    })
  );
}

/**
 * Refresh the Keycloak access token using the refresh token.
 * Returns the refreshed token data or an error marker.
 */
async function refreshAccessToken(token: Record<string, unknown>): Promise<Record<string, unknown>> {
  try {
    const url = `${KC_URL}/realms/${KC_REALM}/protocol/openid-connect/token`;
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        client_id: KC_CLIENT_ID,
        client_secret: KC_CLIENT_SECRET,
        grant_type: "refresh_token",
        refresh_token: token.refreshToken as string,
      }),
    });

    const data = await response.json();

    if (!response.ok) {
      console.error("[auth] Token refresh failed:", data);
      return { ...token, error: "RefreshTokenExpired" };
    }

    return {
      ...token,
      accessToken: data.access_token,
      refreshToken: data.refresh_token ?? token.refreshToken,
      expiresAt: Math.floor(Date.now() / 1000) + (data.expires_in as number),
      error: undefined,
    };
  } catch (error) {
    console.error("[auth] Token refresh error:", error);
    return { ...token, error: "RefreshTokenError" };
  }
}

export const authOptions: NextAuthOptions = {
  providers,
  callbacks: {
    async jwt({ token, account }) {
      // First login — store all token data
      if (account) {
        return {
          ...token,
          accessToken: account.access_token,
          refreshToken: account.refresh_token,
          expiresAt: account.expires_at,
          provider: account.provider,
        };
      }

      // Token still valid (with 5 min safety margin — refresh well before expiry)
      const expiresAt = (token.expiresAt as number) ?? 0;
      if (Date.now() < expiresAt * 1000 - 300_000) {
        return token;
      }

      // Token expired or about to expire — refresh it
      if (token.provider === "keycloak" && token.refreshToken) {
        return refreshAccessToken(token);
      }

      // GitHub tokens don't refresh — just pass through
      return token;
    },

    async session({ session, token }) {
      const s = session as typeof session & {
        accessToken: string;
        provider: string;
        error?: string;
        platformAdmin: boolean;
      };
      s.accessToken = token.accessToken as string;
      s.provider = token.provider as string;
      s.platformAdmin = isPlatformAdmin(token.accessToken as string | undefined);
      if (token.error) {
        s.error = token.error as string;
      }
      return session;
    },
  },
  session: {
    strategy: "jwt",
    maxAge: 8 * 60 * 60, // 8 hours — Keycloak SSO Session Max must match
  },
  pages: {
    signIn: "/auth/signin",
  },
};
