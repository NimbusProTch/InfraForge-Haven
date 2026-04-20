import Link from "next/link";
import { CheckCircle2, ArrowLeft } from "lucide-react";

/**
 * Thank-you page shown after /auth/request-access form submit succeeds.
 *
 * Intentionally sparse — no id, no ETA. The public endpoint returns
 * only {"status": "received"} to prevent enumeration, so we can't
 * surface a ticket number here.
 */
export default function AccessRequestedPage() {
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

        <div className="bg-white dark:bg-zinc-900/80 backdrop-blur-xl border border-gray-200 dark:border-zinc-800 rounded-2xl p-8 shadow-2xl shadow-emerald-500/5 text-center">
          <div className="w-14 h-14 mx-auto rounded-full bg-emerald-100 dark:bg-emerald-950/40 flex items-center justify-center mb-5">
            <CheckCircle2 className="w-7 h-7 text-emerald-600 dark:text-emerald-400" />
          </div>

          <h1 className="text-xl font-bold text-gray-900 dark:text-white tracking-tight">
            We&apos;ve got your request.
          </h1>
          <p className="text-sm text-gray-500 dark:text-zinc-500 mt-2 leading-relaxed">
            One of our founders will review it and reach out by email within a
            business day. If you don&apos;t hear back, check your spam folder — or
            email{" "}
            <a
              href="mailto:hello@iyziops.com"
              className="text-indigo-600 dark:text-indigo-400 hover:text-indigo-500"
            >
              hello@iyziops.com
            </a>
            .
          </p>

          <div className="mt-6 pt-5 border-t border-gray-100 dark:border-zinc-800/60">
            <p className="text-xs text-gray-500 dark:text-zinc-500">
              Already have an account?{" "}
              <Link
                href="/auth/signin"
                className="font-medium text-indigo-600 dark:text-indigo-400 hover:text-indigo-500 transition-colors"
              >
                Sign in →
              </Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
