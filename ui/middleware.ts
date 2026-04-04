/**
 * Next.js Edge Middleware — protects ALL authenticated routes.
 *
 * Unauthenticated users are redirected to /auth/signin server-side.
 */
export { default } from "next-auth/middleware";

export const config = {
  matcher: [
    "/dashboard/:path*",
    "/tenants/:path*",
    "/organizations/:path*",
    "/platform/:path*",
    "/apps/:path*",
    "/services/:path*",
    "/settings/:path*",
  ],
};
