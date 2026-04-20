/**
 * Next.js Edge Middleware — protects ALL authenticated routes.
 *
 * Sprint H2 P10: also enforces session.error after token-refresh failure.
 *
 * BEFORE this fix:
 *   - Unauthenticated request → /auth/signin (good, NextAuth default)
 *   - Authenticated request with stale session.error="RefreshTokenExpired"
 *     → middleware lets it through (BUG — user sees stale UI, next API
 *     call gets 401, confusing experience). The Keycloak refresh token
 *     in `lib/auth.ts` sets `session.error = "RefreshTokenExpired"` when
 *     the refresh round-trip fails, but this signal was never read by
 *     the middleware.
 *
 * AFTER this fix:
 *   - Unauthenticated → /auth/signin (unchanged)
 *   - Authenticated with `session.error` → /auth/signin?reason=session_expired
 *     so the user sees a "your session expired, please log in again"
 *     toast and signs in fresh. The `signOut()` is performed implicitly
 *     by NextAuth on the next protected page render once it detects the
 *     middleware redirected.
 *
 * Why a custom function instead of `export { default } from "next-auth/middleware"`:
 *   - The default export only checks "is the session present at all?"
 *   - It does NOT inspect `session.error` — that's a Haven-specific
 *     convention added in `lib/auth.ts:114-116` from the H0 deep-dive.
 *
 * Reference:
 *   - lib/auth.ts:60 sets `error = "RefreshTokenExpired"` on Keycloak
 *     refresh failure
 *   - lib/auth.ts:114-116 propagates it onto the session
 *   - This middleware is the consumer that finally acts on it.
 */
import { withAuth } from "next-auth/middleware";
import { NextResponse } from "next/server";

export default withAuth(
  function middleware(req) {
    const token = req.nextauth.token;

    // P10: token refresh failed → kick to signin with a friendly reason.
    // The reason is read by /auth/signin/page.tsx (existing handling) to
    // surface a toast.
    if (token && token.error === "RefreshTokenExpired") {
      const signInUrl = new URL("/auth/signin", req.url);
      signInUrl.searchParams.set("reason", "session_expired");
      signInUrl.searchParams.set("callbackUrl", req.nextUrl.pathname);
      return NextResponse.redirect(signInUrl);
    }

    // Other catastrophic refresh errors (e.g. RefreshTokenError from a
    // network timeout) — also kick out, but without the "expired" reason
    // so the toast wording is generic.
    if (token && token.error === "RefreshTokenError") {
      const signInUrl = new URL("/auth/signin", req.url);
      signInUrl.searchParams.set("reason", "session_error");
      signInUrl.searchParams.set("callbackUrl", req.nextUrl.pathname);
      return NextResponse.redirect(signInUrl);
    }

    return NextResponse.next();
  },
  {
    callbacks: {
      // The default authorization callback returns true if a token is
      // present at all. We keep that behavior — the actual error handling
      // happens in the middleware function above. Returning false here
      // would short-circuit straight to /auth/signin without our reason
      // query string.
      authorized: ({ token }) => !!token,
    },
  }
);

export const config = {
  matcher: [
    "/dashboard/:path*",
    "/tenants/:path*",
    "/organizations/:path*",
    "/platform/:path*",
    "/apps/:path*",
    "/services/:path*",
    "/settings/:path*",
    "/admin/:path*",
  ],
};
