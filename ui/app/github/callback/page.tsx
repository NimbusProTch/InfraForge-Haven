"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Loader2, CheckCircle, XCircle } from "lucide-react";

// Force dynamic rendering - this page should never be statically cached
export const dynamic = "force-dynamic";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/**
 * Inner component that uses useSearchParams().
 * Must be wrapped in <Suspense> per Next.js 14.2.5 requirements.
 */
function GitHubCallbackContent() {
  const searchParams = useSearchParams();
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [message, setMessage] = useState("");
  const called = useRef(false);

  useEffect(() => {
    // Guard against duplicate calls
    if (called.current) return;

    const code = searchParams.get("code");
    const error = searchParams.get("error");

    // Wait for searchParams to actually populate before processing.
    // In some Next.js 14 edge cases, searchParams can be empty on the
    // first effect run; we skip and let the next render retry.
    if (!code && !error) return;

    // Params are available - lock to prevent re-entry
    called.current = true;

    if (error) {
      setStatus("error");
      setMessage(searchParams.get("error_description") ?? "GitHub authorization denied");
      // Notify opener of failure
      if (window.opener) {
        window.opener.postMessage({ type: "github_oauth_error", error }, window.location.origin);
        setTimeout(() => window.close(), 2000);
      }
      return;
    }

    // Exchange code for access token via backend
    fetch(`${API_BASE}/api/v1/github/auth/callback?code=${encodeURIComponent(code!)}`)
      .then((res) => {
        if (!res.ok) return res.text().then((t) => Promise.reject(new Error(t)));
        return res.json() as Promise<{ access_token: string }>;
      })
      .then(({ access_token }) => {
        setStatus("success");
        setMessage("GitHub connected successfully!");
        if (window.opener) {
          window.opener.postMessage(
            { type: "github_oauth_success", access_token },
            window.location.origin
          );
          setTimeout(() => window.close(), 1000);
        }
      })
      .catch((err: Error) => {
        setStatus("error");
        setMessage(err.message || "Token exchange failed");
        if (window.opener) {
          window.opener.postMessage(
            { type: "github_oauth_error", error: err.message },
            window.location.origin
          );
          setTimeout(() => window.close(), 2000);
        }
      });
  }, [searchParams]);

  return (
    <div className="min-h-screen bg-[#0a0a0a] flex items-center justify-center">
      <div className="text-center space-y-4">
        {status === "loading" && (
          <>
            <Loader2 className="w-8 h-8 text-blue-500 animate-spin mx-auto" />
            <p className="text-[#888] text-sm">Connecting to GitHub…</p>
          </>
        )}
        {status === "success" && (
          <>
            <CheckCircle className="w-8 h-8 text-green-500 mx-auto" />
            <p className="text-white text-sm font-medium">{message}</p>
            <p className="text-[#555] text-xs">This window will close automatically</p>
          </>
        )}
        {status === "error" && (
          <>
            <XCircle className="w-8 h-8 text-red-500 mx-auto" />
            <p className="text-red-400 text-sm font-medium">{message}</p>
            <button
              onClick={() => window.close()}
              className="text-xs text-[#555] hover:text-white transition-colors"
            >
              Close window
            </button>
          </>
        )}
      </div>
    </div>
  );
}

/**
 * Wrapper component providing the required Suspense boundary for useSearchParams().
 * Shows a loading spinner while search params are being resolved.
 */
export default function GitHubCallbackPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-[#0a0a0a] flex items-center justify-center">
          <div className="text-center space-y-4">
            <Loader2 className="w-8 h-8 text-blue-500 animate-spin mx-auto" />
            <p className="text-[#888] text-sm">Connecting to GitHub…</p>
          </div>
        </div>
      }
    >
      <GitHubCallbackContent />
    </Suspense>
  );
}
