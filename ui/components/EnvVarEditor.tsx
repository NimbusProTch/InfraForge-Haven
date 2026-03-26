"use client";

import { useState, useCallback } from "react";
import { Plus, Trash2, AlertCircle } from "lucide-react";

interface EnvVarEditorProps {
  value: Record<string, string>;
  onChange: (vars: Record<string, string>) => void;
  disabled?: boolean;
}

interface EnvEntry {
  id: string;
  key: string;
  value: string;
}

let nextId = 0;
function genId(): string {
  return `env-${++nextId}-${Date.now()}`;
}

function toEntries(vars: Record<string, string>): EnvEntry[] {
  const entries = Object.entries(vars).map(([key, value]) => ({
    id: genId(),
    key,
    value,
  }));
  return entries.length > 0 ? entries : [{ id: genId(), key: "", value: "" }];
}

function toRecord(entries: EnvEntry[]): Record<string, string> {
  const record: Record<string, string> = {};
  for (const entry of entries) {
    const trimmedKey = entry.key.trim();
    if (trimmedKey) {
      record[trimmedKey] = entry.value;
    }
  }
  return record;
}

export default function EnvVarEditor({ value, onChange, disabled }: EnvVarEditorProps) {
  const [entries, setEntries] = useState<EnvEntry[]>(() => toEntries(value));

  const commit = useCallback(
    (next: EnvEntry[]) => {
      setEntries(next);
      onChange(toRecord(next));
    },
    [onChange]
  );

  function handleKeyChange(id: string, newKey: string) {
    const next = entries.map((e) => (e.id === id ? { ...e, key: newKey } : e));
    commit(next);
  }

  function handleValueChange(id: string, newValue: string) {
    const next = entries.map((e) => (e.id === id ? { ...e, value: newValue } : e));
    commit(next);
  }

  function handleAdd() {
    commit([...entries, { id: genId(), key: "", value: "" }]);
  }

  function handleRemove(id: string) {
    const next = entries.filter((e) => e.id !== id);
    commit(next.length > 0 ? next : [{ id: genId(), key: "", value: "" }]);
  }

  // Validation: find duplicate keys
  const keyCounts: Record<string, number> = {};
  for (const e of entries) {
    const k = e.key.trim();
    if (k) {
      keyCounts[k] = (keyCounts[k] || 0) + 1;
    }
  }
  const duplicateKeys = new Set(
    Object.entries(keyCounts)
      .filter(([, count]) => count > 1)
      .map(([key]) => key)
  );

  const hasEmptyKeys = entries.some((e) => e.key.trim() === "" && e.value.trim() !== "");

  return (
    <div className="space-y-3">
      <div className="space-y-2">
        {/* Header row */}
        <div className="grid grid-cols-[1fr_1fr_36px] gap-2">
          <span className="text-xs font-medium text-gray-500 dark:text-[#666] uppercase tracking-wider">
            Key
          </span>
          <span className="text-xs font-medium text-gray-500 dark:text-[#666] uppercase tracking-wider">
            Value
          </span>
          <span />
        </div>

        {/* Entries */}
        {entries.map((entry) => {
          const isDuplicate = duplicateKeys.has(entry.key.trim());
          const isEmpty = entry.key.trim() === "" && entry.value.trim() !== "";

          return (
            <div key={entry.id} className="grid grid-cols-[1fr_1fr_36px] gap-2 items-start">
              <div>
                <input
                  type="text"
                  value={entry.key}
                  onChange={(e) => handleKeyChange(entry.id, e.target.value)}
                  placeholder="KEY_NAME"
                  disabled={disabled}
                  className={`w-full px-3 py-1.5 rounded-md border bg-white dark:bg-[#0a0a0a] text-sm text-gray-900 dark:text-white font-mono focus:outline-none focus:ring-1 transition-colors ${
                    isDuplicate || isEmpty
                      ? "border-red-400 dark:border-red-500/50 focus:ring-red-500"
                      : "border-gray-200 dark:border-[#2e2e2e] focus:ring-blue-500"
                  }`}
                />
                {isDuplicate && (
                  <p className="text-[10px] text-red-400 mt-0.5 flex items-center gap-1">
                    <AlertCircle className="w-2.5 h-2.5" />
                    Duplicate key
                  </p>
                )}
              </div>
              <input
                type="text"
                value={entry.value}
                onChange={(e) => handleValueChange(entry.id, e.target.value)}
                placeholder="value"
                disabled={disabled}
                className="w-full px-3 py-1.5 rounded-md border border-gray-200 dark:border-[#2e2e2e] bg-white dark:bg-[#0a0a0a] text-sm text-gray-900 dark:text-white font-mono focus:outline-none focus:ring-1 focus:ring-blue-500 transition-colors"
              />
              <button
                type="button"
                onClick={() => handleRemove(entry.id)}
                disabled={disabled}
                className="p-1.5 rounded-md text-gray-400 dark:text-[#555] hover:text-red-500 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors disabled:opacity-50 mt-0.5"
                title="Remove variable"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          );
        })}
      </div>

      {/* Validation warnings */}
      {hasEmptyKeys && (
        <p className="text-xs text-amber-500 flex items-center gap-1.5">
          <AlertCircle className="w-3 h-3" />
          Variables with empty keys will be ignored
        </p>
      )}

      {/* Add button */}
      <button
        type="button"
        onClick={handleAdd}
        disabled={disabled}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-dashed border-gray-300 dark:border-[#333] text-gray-500 dark:text-[#666] hover:text-gray-700 dark:hover:text-[#999] hover:border-gray-400 dark:hover:border-[#444] text-xs font-medium transition-colors disabled:opacity-50"
      >
        <Plus className="w-3 h-3" />
        Add Variable
      </button>

      {/* Summary */}
      <p className="text-xs text-gray-400 dark:text-[#555]">
        {Object.keys(toRecord(entries)).length} variable{Object.keys(toRecord(entries)).length !== 1 ? "s" : ""} defined
      </p>
    </div>
  );
}
