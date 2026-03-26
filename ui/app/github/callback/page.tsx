"use client";

import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Loader2, CheckCircle, XCircle } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function GitHubCallbackPage() {
  const searchParams = useSearchParams();
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [message, setMessage] = useState("");
  const called = useRef(false);

  useEffect(() => {
    if (called.current) return;
    called.current = true;

    const code = searchParams.get("code");
    const error = searchParams.get("error");

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

    if (!code) {
      setStatus("error");
      setMessage("No authorization code received from GitHub");
      return;
    }

    // Exchange code for access token via backend
    fetch(`${API_BASE}/api/v1/github/auth/callback?code=${encodeURIComponent(code)}`)
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
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
