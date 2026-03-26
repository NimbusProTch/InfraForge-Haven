"use client";

import { Globe, HeartPulse, Webhook, ExternalLink } from "lucide-react";

export interface DomainValues {
  custom_domain: string;
  health_check_path: string;
  health_check_type: "http" | "tcp";
  auto_deploy: boolean;
}

interface DomainConfigProps {
  value: DomainValues;
  onChange: (values: DomainValues) => void;
  currentHostname?: string;
  disabled?: boolean;
}

export default function DomainConfig({
  value,
  onChange,
  currentHostname,
  disabled,
}: DomainConfigProps) {
  function update(partial: Partial<DomainValues>) {
    onChange({ ...value, ...partial });
  }

  return (
    <div className="space-y-6">
      {/* Custom Domain */}
      <div className="bg-white dark:bg-[#141414] border border-gray-200 dark:border-[#222] rounded-lg p-5">
        <div className="flex items-center gap-2 mb-4">
          <div className="w-7 h-7 rounded-md bg-blue-500/10 flex items-center justify-center">
            <Globe className="w-3.5 h-3.5 text-blue-500" />
          </div>
          <h4 className="text-sm font-semibold text-gray-900 dark:text-white">Domain</h4>
        </div>

        {/* Current hostname */}
        {currentHostname && (
          <div className="mb-4 bg-gray-50 dark:bg-[#0a0a0a] border border-gray-200 dark:border-[#1e1e1e] rounded-md px-3 py-2.5">
            <p className="text-xs text-gray-500 dark:text-[#666] mb-1">Current hostname</p>
            <div className="flex items-center gap-2">
              <code className="text-sm font-mono text-gray-900 dark:text-white">
                {currentHostname}
              </code>
              <a
                href={`https://${currentHostname}`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-500 hover:text-blue-600 transition-colors"
              >
                <ExternalLink className="w-3 h-3" />
              </a>
            </div>
          </div>
        )}

        <div>
          <label className="block text-xs text-gray-500 dark:text-[#666] mb-1">
            Custom domain (optional)
          </label>
          <input
            type="text"
            value={value.custom_domain}
            onChange={(e) => update({ custom_domain: e.target.value })}
            placeholder="app.yourdomain.nl"
            disabled={disabled}
            className="w-full px-3 py-1.5 rounded-md border border-gray-200 dark:border-[#2e2e2e] bg-white dark:bg-[#0a0a0a] text-sm text-gray-900 dark:text-white font-mono focus:outline-none focus:ring-1 focus:ring-blue-500 transition-colors"
          />
          <p className="text-xs text-gray-400 dark:text-[#555] mt-1.5">
            Point a CNAME record to your sslip.io hostname. TLS will be auto-provisioned via Let&apos;s Encrypt.
          </p>
        </div>
      </div>

      {/* Health Check */}
      <div className="bg-white dark:bg-[#141414] border border-gray-200 dark:border-[#222] rounded-lg p-5">
        <div className="flex items-center gap-2 mb-4">
          <div className="w-7 h-7 rounded-md bg-emerald-500/10 flex items-center justify-center">
            <HeartPulse className="w-3.5 h-3.5 text-emerald-500" />
          </div>
          <h4 className="text-sm font-semibold text-gray-900 dark:text-white">Health Check</h4>
        </div>

        <div className="space-y-3">
          <div>
            <label className="block text-xs text-gray-500 dark:text-[#666] mb-1">Type</label>
            <div className="flex gap-2">
              {(["http", "tcp"] as const).map((type) => (
                <button
                  key={type}
                  type="button"
                  disabled={disabled}
                  onClick={() => update({ health_check_type: type })}
                  className={`px-4 py-1.5 rounded-md text-xs font-medium border transition-colors disabled:opacity-50 ${
                    value.health_check_type === type
                      ? "border-blue-500 bg-blue-500/10 text-blue-500 dark:text-blue-400"
                      : "border-gray-200 dark:border-[#2e2e2e] text-gray-500 dark:text-[#666] hover:border-gray-400 dark:hover:border-[#444]"
                  }`}
                >
                  {type.toUpperCase()}
                </button>
              ))}
            </div>
          </div>

          {value.health_check_type === "http" && (
            <div>
              <label className="block text-xs text-gray-500 dark:text-[#666] mb-1">
                Health check path
              </label>
              <input
                type="text"
                value={value.health_check_path}
                onChange={(e) => update({ health_check_path: e.target.value })}
                placeholder="/health"
                disabled={disabled}
                className="w-full px-3 py-1.5 rounded-md border border-gray-200 dark:border-[#2e2e2e] bg-white dark:bg-[#0a0a0a] text-sm text-gray-900 dark:text-white font-mono focus:outline-none focus:ring-1 focus:ring-blue-500 transition-colors"
              />
              <p className="text-xs text-gray-400 dark:text-[#555] mt-1.5">
                HTTP GET endpoint that returns 200 OK when the app is healthy.
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Auto-deploy */}
      <div className="bg-white dark:bg-[#141414] border border-gray-200 dark:border-[#222] rounded-lg p-5">
        <div className="flex items-center gap-2 mb-4">
          <div className="w-7 h-7 rounded-md bg-amber-500/10 flex items-center justify-center">
            <Webhook className="w-3.5 h-3.5 text-amber-500" />
          </div>
          <h4 className="text-sm font-semibold text-gray-900 dark:text-white">Auto-Deploy</h4>
        </div>

        <label className="flex items-center gap-3 cursor-pointer group">
          <div className="relative">
            <input
              type="checkbox"
              checked={value.auto_deploy}
              onChange={(e) => update({ auto_deploy: e.target.checked })}
              disabled={disabled}
              className="sr-only peer"
            />
            <div className="w-9 h-5 rounded-full bg-gray-200 dark:bg-[#2a2a2a] peer-checked:bg-blue-600 transition-colors" />
            <div className="absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform peer-checked:translate-x-4" />
          </div>
          <span className="text-xs text-gray-700 dark:text-[#ccc] group-hover:text-gray-900 dark:group-hover:text-white transition-colors">
            Auto-deploy on push
          </span>
        </label>
        <p className="text-xs text-gray-400 dark:text-[#555] mt-2 ml-12">
          When enabled, a push to the configured branch will automatically trigger a build and deployment via webhook.
        </p>
      </div>
    </div>
  );
}
