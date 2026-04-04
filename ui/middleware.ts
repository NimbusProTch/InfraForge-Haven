/**
 * Next.js Edge Middleware — protects all authenticated routes.
 *
 * Unauthenticated users are redirected to /auth/signin server-side
 * (not client-side) for better security and UX.
 */
export { default } from "next-auth/middleware";

export const config = {
  matcher: [
    "/dashboard/:path*",
    "/tenants/:path*",
    "/organizations/:path*",
    "/platform/:path*",
  ],
};
