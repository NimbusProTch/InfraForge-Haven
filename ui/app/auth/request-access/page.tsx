"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ArrowLeft, Loader2, AlertCircle } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/**
 * Public enterprise-access request form.
 *
 * Submits to POST /api/v1/access-requests (ET1 backend). Rate limited
 * server-side (5/hour/IP) + honeypot on the 'website' field. On 201,
 * redirect to /auth/access-requested (thank-you page). No authentication
 * required — this is the prospective-customer funnel.
 */
export default function RequestAccessPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [orgName, setOrgName] = useState("");
  const [message, setMessage] = useState("");
  const [website, setWebsite] = useState(""); // honeypot
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const resp = await fetch(`${API_BASE}/api/v1/access-requests`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim(),
          email: email.trim(),
          org_name: orgName.trim(),
          message: message.trim() || null,
          website,  // honeypot — must stay empty
        }),
      });
      if (!resp.ok) {
        const detail = await resp.text();
        let pretty = detail;
        try {
          const body = JSON.parse(detail);
          if (Array.isArray(body?.detail)) {
            // Pydantic validation error array
            pretty = body.detail
              .map((e: { msg?: string; loc?: unknown[] }) => {
                const field = Array.isArray(e.loc) ? e.loc.slice(-1)[0] : "";
                return field ? `${field}: ${e.msg}` : e.msg;
              })
              .join("; ");
          } else if (body?.detail) {
            pretty = body.detail;
          }
        } catch {
          /* keep raw */
        }
        if (resp.status === 429) {
          pretty =
            "Too many requests from this address — please wait a few minutes and try again.";
        }
        throw new Error(pretty);
      }
      router.push("/auth/access-requested");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Submission failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-50 via-white to-indigo-50 dark:from-zinc-950 dark:via-zinc-900 dark:to-indigo-950/30 px-4 py-12">
      <div className="w-full max-w-md">
        <Link
          href="/"
          className="inline-flex items-center gap-1.5 text-sm text-gray-500 dark:text-zinc-500 hover:text-gray-900 dark:hover:text-zinc-200 mb-6 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to home
        </Link>

        <div className="bg-white dark:bg-zinc-900/80 backdrop-blur-xl border border-gray-200 dark:border-zinc-800 rounded-2xl p-8 shadow-2xl shadow-indigo-500/5">
          <div className="flex flex-col items-center mb-6">
            <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-blue-500 via-indigo-500 to-violet-600 flex items-center justify-center mb-4 shadow-lg shadow-indigo-500/30">
              <span className="font-extrabold text-2xl text-white leading-none tracking-tighter">
                iy
              </span>
            </div>
            <h1 className="text-xl font-bold text-gray-900 dark:text-white tracking-tight">
              Request access
            </h1>
            <p className="text-sm text-gray-500 dark:text-zinc-500 mt-1 text-center max-w-xs">
              Tell us a bit about your organization and we&apos;ll reach out to get you set up.
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4" data-testid="request-access-form">
            <Field
              id="name"
              label="Full name"
              value={name}
              onChange={setName}
              required
              autoComplete="name"
              placeholder="Jan de Vries"
              minLength={2}
            />
            <Field
              id="email"
              label="Work email"
              type="email"
              value={email}
              onChange={setEmail}
              required
              autoComplete="email"
              placeholder="jan@example.nl"
            />
            <Field
              id="org_name"
              label="Organization"
              value={orgName}
              onChange={setOrgName}
              required
              autoComplete="organization"
              placeholder="Acme Corp"
              minLength={2}
            />

            <div>
              <label
                htmlFor="message"
                className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-1.5"
              >
                Anything else? <span className="text-gray-400">(optional)</span>
              </label>
              <textarea
                id="message"
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                rows={3}
                maxLength={2000}
                placeholder="Which use case are you evaluating? How many users?"
                className="w-full px-3 py-2 text-sm rounded-lg border border-gray-300 dark:border-zinc-700 bg-white dark:bg-zinc-900 text-gray-900 dark:text-white placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
              />
            </div>

            {/* Honeypot — hidden from humans, bots fill it. Server
                silently 201s when populated so we never leak a
                4xx signal. Positioned absolute+invisible rather than
                display:none because some bots ignore the latter. */}
            <div aria-hidden="true" className="absolute opacity-0 pointer-events-none -left-[9999px]">
              <label htmlFor="website">Website (leave blank)</label>
              <input
                id="website"
                name="website"
                type="text"
                tabIndex={-1}
                autoComplete="off"
                value={website}
                onChange={(e) => setWebsite(e.target.value)}
              />
            </div>

            {error && (
              <div
                role="alert"
                data-testid="request-access-error"
                className="flex items-start gap-2 rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-900 dark:border-red-800/50 dark:bg-red-950/40 dark:text-red-300"
              >
                <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full inline-flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 text-white text-sm font-semibold transition-all shadow-lg shadow-indigo-500/20 hover:shadow-indigo-500/30 disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {loading && <Loader2 className="w-4 h-4 animate-spin" />}
              {loading ? "Sending..." : "Request access"}
            </button>
          </form>

          <p className="text-center text-xs text-gray-400 dark:text-zinc-600 mt-6">
            Already have an account?{" "}
            <Link
              href="/auth/signin"
              className="text-indigo-600 dark:text-indigo-400 hover:text-indigo-500 transition-colors"
            >
              Sign in →
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}

function Field({
  id,
  label,
  value,
  onChange,
  required,
  placeholder,
  type = "text",
  autoComplete,
  minLength,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  required?: boolean;
  placeholder?: string;
  type?: string;
  autoComplete?: string;
  minLength?: number;
}) {
  return (
    <div>
      <label
        htmlFor={id}
        className="block text-sm font-medium text-gray-700 dark:text-zinc-300 mb-1.5"
      >
        {label} {required && <span className="text-red-500">*</span>}
      </label>
      <input
        id={id}
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required={required}
        autoComplete={autoComplete}
        placeholder={placeholder}
        minLength={minLength}
        maxLength={255}
        className="w-full px-3 py-2 text-sm rounded-lg border border-gray-300 dark:border-zinc-700 bg-white dark:bg-zinc-900 text-gray-900 dark:text-white placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
      />
    </div>
  );
}
