"use client";

import { Cpu, MemoryStick, Scaling } from "lucide-react";

const CPU_PRESETS = ["50m", "100m", "250m", "500m", "1000m"];
const MEMORY_PRESETS = ["64Mi", "128Mi", "256Mi", "512Mi", "1Gi", "2Gi"];

export interface ResourceValues {
  cpu_request: string;
  cpu_limit: string;
  memory_request: string;
  memory_limit: string;
  min_replicas: number;
  max_replicas: number;
  cpu_threshold: number;
}

interface ResourceConfigProps {
  value: ResourceValues;
  onChange: (values: ResourceValues) => void;
  disabled?: boolean;
}

function PresetPicker({
  presets,
  current,
  onSelect,
  disabled,
}: {
  presets: string[];
  current: string;
  onSelect: (v: string) => void;
  disabled?: boolean;
}) {
  return (
    <div className="flex flex-wrap gap-1 mt-1.5">
      {presets.map((p) => (
        <button
          key={p}
          type="button"
          disabled={disabled}
          onClick={() => onSelect(p)}
          className={`px-2 py-0.5 rounded text-[11px] font-mono border transition-colors disabled:opacity-50 ${
            current === p
              ? "border-blue-500 bg-blue-500/10 text-blue-500 dark:text-blue-400"
              : "border-gray-200 dark:border-[#2e2e2e] text-gray-500 dark:text-[#666] hover:border-gray-400 dark:hover:border-[#444] hover:text-gray-700 dark:hover:text-[#999]"
          }`}
        >
          {p}
        </button>
      ))}
    </div>
  );
}

export default function ResourceConfig({ value, onChange, disabled }: ResourceConfigProps) {
  function update(partial: Partial<ResourceValues>) {
    onChange({ ...value, ...partial });
  }

  return (
    <div className="space-y-6">
      {/* CPU */}
      <div className="bg-white dark:bg-[#141414] border border-gray-200 dark:border-[#222] rounded-lg p-5">
        <div className="flex items-center gap-2 mb-4">
          <div className="w-7 h-7 rounded-md bg-blue-500/10 flex items-center justify-center">
            <Cpu className="w-3.5 h-3.5 text-blue-500" />
          </div>
          <h4 className="text-sm font-semibold text-gray-900 dark:text-white">CPU</h4>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-xs text-gray-500 dark:text-[#666] mb-1">Request</label>
            <input
              type="text"
              value={value.cpu_request}
              onChange={(e) => update({ cpu_request: e.target.value })}
              disabled={disabled}
              className="w-full px-3 py-1.5 rounded-md border border-gray-200 dark:border-[#2e2e2e] bg-white dark:bg-[#0a0a0a] text-sm text-gray-900 dark:text-white font-mono focus:outline-none focus:ring-1 focus:ring-blue-500 transition-colors"
            />
            <PresetPicker
              presets={CPU_PRESETS}
              current={value.cpu_request}
              onSelect={(v) => update({ cpu_request: v })}
              disabled={disabled}
            />
          </div>
          <div>
            <label className="block text-xs text-gray-500 dark:text-[#666] mb-1">Limit</label>
            <input
              type="text"
              value={value.cpu_limit}
              onChange={(e) => update({ cpu_limit: e.target.value })}
              disabled={disabled}
              className="w-full px-3 py-1.5 rounded-md border border-gray-200 dark:border-[#2e2e2e] bg-white dark:bg-[#0a0a0a] text-sm text-gray-900 dark:text-white font-mono focus:outline-none focus:ring-1 focus:ring-blue-500 transition-colors"
            />
            <PresetPicker
              presets={CPU_PRESETS}
              current={value.cpu_limit}
              onSelect={(v) => update({ cpu_limit: v })}
              disabled={disabled}
            />
          </div>
        </div>
      </div>

      {/* Memory */}
      <div className="bg-white dark:bg-[#141414] border border-gray-200 dark:border-[#222] rounded-lg p-5">
        <div className="flex items-center gap-2 mb-4">
          <div className="w-7 h-7 rounded-md bg-purple-500/10 flex items-center justify-center">
            <MemoryStick className="w-3.5 h-3.5 text-purple-500" />
          </div>
          <h4 className="text-sm font-semibold text-gray-900 dark:text-white">Memory</h4>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-xs text-gray-500 dark:text-[#666] mb-1">Request</label>
            <input
              type="text"
              value={value.memory_request}
              onChange={(e) => update({ memory_request: e.target.value })}
              disabled={disabled}
              className="w-full px-3 py-1.5 rounded-md border border-gray-200 dark:border-[#2e2e2e] bg-white dark:bg-[#0a0a0a] text-sm text-gray-900 dark:text-white font-mono focus:outline-none focus:ring-1 focus:ring-blue-500 transition-colors"
            />
            <PresetPicker
              presets={MEMORY_PRESETS}
              current={value.memory_request}
              onSelect={(v) => update({ memory_request: v })}
              disabled={disabled}
            />
          </div>
          <div>
            <label className="block text-xs text-gray-500 dark:text-[#666] mb-1">Limit</label>
            <input
              type="text"
              value={value.memory_limit}
              onChange={(e) => update({ memory_limit: e.target.value })}
              disabled={disabled}
              className="w-full px-3 py-1.5 rounded-md border border-gray-200 dark:border-[#2e2e2e] bg-white dark:bg-[#0a0a0a] text-sm text-gray-900 dark:text-white font-mono focus:outline-none focus:ring-1 focus:ring-blue-500 transition-colors"
            />
            <PresetPicker
              presets={MEMORY_PRESETS}
              current={value.memory_limit}
              onSelect={(v) => update({ memory_limit: v })}
              disabled={disabled}
            />
          </div>
        </div>
      </div>

      {/* Autoscaling */}
      <div className="bg-white dark:bg-[#141414] border border-gray-200 dark:border-[#222] rounded-lg p-5">
        <div className="flex items-center gap-2 mb-4">
          <div className="w-7 h-7 rounded-md bg-emerald-500/10 flex items-center justify-center">
            <Scaling className="w-3.5 h-3.5 text-emerald-500" />
          </div>
          <h4 className="text-sm font-semibold text-gray-900 dark:text-white">Autoscaling</h4>
        </div>
        <div className="grid grid-cols-2 gap-4 mb-4">
          <div>
            <label className="block text-xs text-gray-500 dark:text-[#666] mb-1">Min Replicas</label>
            <input
              type="number"
              min={1}
              max={100}
              value={value.min_replicas}
              onChange={(e) =>
                update({ min_replicas: Math.max(1, Math.min(100, Number(e.target.value))) })
              }
              disabled={disabled}
              className="w-full px-3 py-1.5 rounded-md border border-gray-200 dark:border-[#2e2e2e] bg-white dark:bg-[#0a0a0a] text-sm text-gray-900 dark:text-white font-mono focus:outline-none focus:ring-1 focus:ring-blue-500 transition-colors"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-500 dark:text-[#666] mb-1">Max Replicas</label>
            <input
              type="number"
              min={1}
              max={100}
              value={value.max_replicas}
              onChange={(e) =>
                update({ max_replicas: Math.max(1, Math.min(100, Number(e.target.value))) })
              }
              disabled={disabled}
              className="w-full px-3 py-1.5 rounded-md border border-gray-200 dark:border-[#2e2e2e] bg-white dark:bg-[#0a0a0a] text-sm text-gray-900 dark:text-white font-mono focus:outline-none focus:ring-1 focus:ring-blue-500 transition-colors"
            />
          </div>
        </div>
        <div>
          <label className="block text-xs text-gray-500 dark:text-[#666] mb-2">
            CPU Autoscale Threshold:{" "}
            <span className="font-mono font-semibold text-gray-700 dark:text-[#ccc]">
              {value.cpu_threshold}%
            </span>
          </label>
          <input
            type="range"
            min={10}
            max={100}
            step={5}
            value={value.cpu_threshold}
            onChange={(e) => update({ cpu_threshold: Number(e.target.value) })}
            disabled={disabled}
            className="w-full h-1.5 rounded-full appearance-none cursor-pointer bg-gray-200 dark:bg-[#2a2a2a] accent-blue-600"
          />
          <div className="flex justify-between mt-1">
            <span className="text-[10px] text-gray-400 dark:text-[#555]">10%</span>
            <span className="text-[10px] text-gray-400 dark:text-[#555]">50%</span>
            <span className="text-[10px] text-gray-400 dark:text-[#555]">100%</span>
          </div>
        </div>
      </div>
    </div>
  );
}
