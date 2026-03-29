"use client";

import { useEffect, useState, useCallback } from "react";
import { api, type VolumeItem, type VolumeList } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { Badge } from "@/components/ui/badge";
import {
  Plus,
  Loader2,
  HardDrive,
  Trash2,
  X,
  Database,
} from "lucide-react";

const ACCESS_MODE_LABELS: Record<string, string> = {
  ReadWriteOnce: "RWO — Single node read/write",
  ReadWriteMany: "RWX — Multi-node read/write",
  ReadOnlyMany: "ROX — Multi-node read-only",
};

interface VolumesTabProps {
  tenantSlug: string;
  appSlug: string;
  accessToken?: string;
}

export default function VolumesTab({ tenantSlug, appSlug, accessToken }: VolumesTabProps) {
  const { error: toastError, success: toastSuccess } = useToast();
  const [volumes, setVolumes] = useState<VolumeItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);

  // Create form
  const [newName, setNewName] = useState("");
  const [newSize, setNewSize] = useState(5);
  const [newAccessMode, setNewAccessMode] = useState("ReadWriteOnce");
  const [newMountPath, setNewMountPath] = useState("/data");

  const loadVolumes = useCallback(async () => {
    try {
      const result = await api.pvcs.list(tenantSlug, appSlug, accessToken);
      setVolumes(result.volumes ?? []);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [tenantSlug, appSlug, accessToken]);

  useEffect(() => {
    loadVolumes();
  }, [loadVolumes]);

  async function createVolume() {
    if (!newName.trim()) return;
    setCreating(true);
    try {
      const vol = await api.pvcs.create(tenantSlug, appSlug, {
        name: newName.toLowerCase().replace(/[^a-z0-9-]/g, "-"),
        size_gi: newSize,
        access_mode: newAccessMode,
        mount_path: newMountPath,
      }, accessToken);
      setVolumes((prev) => [...prev, vol]);
      toastSuccess(`Volume "${vol.name}" created (${newSize} GiB)`);
      setShowCreate(false);
      setNewName("");
      setNewSize(5);
      setNewMountPath("/data");
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Failed to create volume");
    } finally {
      setCreating(false);
    }
  }

  async function deleteVolume(name: string) {
    if (!confirm(`Delete volume "${name}"? All data will be lost.`)) return;
    setDeleting(name);
    try {
      await api.pvcs.delete(tenantSlug, appSlug, name, accessToken);
      setVolumes((prev) => prev.filter((v) => v.name !== name));
      toastSuccess(`Volume "${name}" deleted`);
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Failed to delete volume");
    } finally {
      setDeleting(null);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="w-5 h-5 animate-spin text-zinc-600" />
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-5">
        <p className="text-sm text-zinc-500">Persistent storage volumes backed by Longhorn</p>
        <button
          onClick={() => setShowCreate(true)}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-medium transition-colors"
        >
          <Plus className="w-3 h-3" />
          New Volume
        </button>
      </div>

      {/* Create modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl w-full max-w-md mx-4 shadow-2xl overflow-hidden">
            <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-800">
              <div className="flex items-center gap-2">
                <HardDrive className="w-4 h-4 text-cyan-500" />
                <h2 className="text-sm font-semibold text-zinc-100">Create Volume</h2>
              </div>
              <button onClick={() => setShowCreate(false)} className="text-zinc-600 hover:text-zinc-300 transition-colors">
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-5 space-y-4">
              <div>
                <label className="block text-xs font-medium text-zinc-400 mb-1.5">Name</label>
                <input
                  type="text"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="app-data"
                  className="w-full px-3 py-2 rounded-lg border border-zinc-700 bg-zinc-800 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:border-cyan-600 focus:ring-1 focus:ring-cyan-600/30 font-mono"
                  autoFocus
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-zinc-400 mb-1.5">
                  Size: <span className="text-zinc-200 font-mono">{newSize} GiB</span>
                </label>
                <input
                  type="range"
                  min={1}
                  max={100}
                  value={newSize}
                  onChange={(e) => setNewSize(Number(e.target.value))}
                  className="w-full h-1.5 bg-zinc-700 rounded-lg appearance-none cursor-pointer accent-cyan-500"
                />
                <div className="flex justify-between text-xs text-zinc-600 mt-1">
                  <span>1 GiB</span>
                  <span>100 GiB</span>
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-zinc-400 mb-1.5">Access Mode</label>
                <div className="space-y-2">
                  {Object.entries(ACCESS_MODE_LABELS).map(([mode, label]) => (
                    <button
                      key={mode}
                      onClick={() => setNewAccessMode(mode)}
                      className={`w-full text-left px-3 py-2.5 rounded-lg border text-xs transition-colors ${
                        newAccessMode === mode
                          ? "border-cyan-600 bg-cyan-600/10 text-cyan-400"
                          : "border-zinc-800 bg-zinc-800/50 text-zinc-500 hover:border-zinc-700"
                      }`}
                    >
                      <span className="font-medium">{label}</span>
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-zinc-400 mb-1.5">Mount Path</label>
                <input
                  type="text"
                  value={newMountPath}
                  onChange={(e) => setNewMountPath(e.target.value)}
                  placeholder="/data"
                  className="w-full px-3 py-2 rounded-lg border border-zinc-700 bg-zinc-800 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:border-cyan-600 focus:ring-1 focus:ring-cyan-600/30 font-mono"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  onClick={() => setShowCreate(false)}
                  className="px-3 py-1.5 rounded-lg text-xs font-medium text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800 transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={createVolume}
                  disabled={!newName.trim() || creating}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-700 text-white text-xs font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {creating && <Loader2 className="w-3 h-3 animate-spin" />}
                  Create
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Volume list */}
      {volumes.length === 0 ? (
        <div className="text-center py-16 border border-dashed border-zinc-800 rounded-xl">
          <HardDrive className="w-8 h-8 mx-auto mb-2 text-zinc-700" />
          <p className="text-sm text-zinc-500">No persistent volumes.</p>
          <p className="text-xs text-zinc-600 mt-1">Attach a volume for data that survives pod restarts.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {volumes.map((vol) => (
            <div
              key={vol.name}
              className="bg-zinc-900/50 border border-zinc-800 rounded-xl p-4 hover:border-zinc-700 transition-colors"
            >
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-lg bg-cyan-500/10 flex items-center justify-center">
                    <Database className="w-4 h-4 text-cyan-500" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-zinc-200 font-mono">{vol.name}</span>
                      <Badge variant="secondary">{vol.status ?? "Bound"}</Badge>
                    </div>
                    <div className="flex items-center gap-3 mt-1 text-xs text-zinc-600">
                      <span className="font-mono">{vol.size_gi} GiB</span>
                      <span>{vol.access_mode}</span>
                    </div>
                  </div>
                </div>

                <button
                  onClick={() => deleteVolume(vol.name)}
                  disabled={deleting === vol.name}
                  className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium text-zinc-600 hover:text-red-400 hover:bg-red-950/30 transition-colors disabled:opacity-50"
                >
                  {deleting === vol.name ? (
                    <Loader2 className="w-3 h-3 animate-spin" />
                  ) : (
                    <Trash2 className="w-3 h-3" />
                  )}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
