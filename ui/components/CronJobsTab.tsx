"use client";

import { useEffect, useState, useCallback } from "react";
import { api, type CronJob } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { Badge } from "@/components/ui/badge";
import {
  Plus,
  Loader2,
  Timer,
  Trash2,
  X,
  Play,
  Clock,
  CheckCircle2,
  XCircle,
} from "lucide-react";

const CRON_PRESETS = [
  { label: "Every minute", value: "* * * * *" },
  { label: "Every 5 minutes", value: "*/5 * * * *" },
  { label: "Every hour", value: "0 * * * *" },
  { label: "Every day at midnight", value: "0 0 * * *" },
  { label: "Every Monday 9 AM", value: "0 9 * * 1" },
  { label: "Custom", value: "" },
];

interface CronJobsTabProps {
  tenantSlug: string;
  appSlug: string;
  accessToken?: string;
}

export default function CronJobsTab({ tenantSlug, appSlug, accessToken }: CronJobsTabProps) {
  const { error: toastError, success: toastSuccess } = useToast();
  const [jobs, setJobs] = useState<CronJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [running, setRunning] = useState<string | null>(null);

  // Create form
  const [newName, setNewName] = useState("");
  const [newSchedule, setNewSchedule] = useState("0 * * * *");
  const [newCommand, setNewCommand] = useState("");
  const [selectedPreset, setSelectedPreset] = useState("0 * * * *");

  const loadJobs = useCallback(async () => {
    try {
      const j = await api.cronjobs.list(tenantSlug, appSlug, accessToken);
      setJobs(j);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [tenantSlug, appSlug, accessToken]);

  useEffect(() => {
    loadJobs();
  }, [loadJobs]);

  async function createJob() {
    if (!newName.trim() || !newSchedule.trim()) return;
    setCreating(true);
    try {
      const job = await api.cronjobs.create(tenantSlug, appSlug, {
        name: newName.toLowerCase().replace(/[^a-z0-9-]/g, "-"),
        schedule: newSchedule,
        command: newCommand ? newCommand.split(" ") : undefined,
      }, accessToken);
      setJobs((prev) => [...prev, job]);
      toastSuccess(`CronJob "${job.name}" created`);
      setShowCreate(false);
      setNewName("");
      setNewCommand("");
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Failed to create cron job");
    } finally {
      setCreating(false);
    }
  }

  async function runNow(jobId: string, jobName: string) {
    setRunning(jobId);
    try {
      await api.cronjobs.runNow(tenantSlug, appSlug, jobId, accessToken);
      toastSuccess(`Manual run triggered for "${jobName}"`);
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Failed to trigger run");
    } finally {
      setRunning(null);
    }
  }

  async function deleteJob(jobId: string, jobName: string) {
    if (!confirm(`Delete cron job "${jobName}"?`)) return;
    setDeleting(jobId);
    try {
      await api.cronjobs.delete(tenantSlug, appSlug, jobId, accessToken);
      setJobs((prev) => prev.filter((j) => j.id !== jobId));
      toastSuccess(`CronJob "${jobName}" deleted`);
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Failed to delete cron job");
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
        <p className="text-sm text-zinc-500">Scheduled tasks running on a cron schedule</p>
        <button
          onClick={() => setShowCreate(true)}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-medium transition-colors"
        >
          <Plus className="w-3 h-3" />
          New CronJob
        </button>
      </div>

      {/* Create modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl w-full max-w-md mx-4 shadow-2xl overflow-hidden">
            <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-800">
              <div className="flex items-center gap-2">
                <Timer className="w-4 h-4 text-violet-500" />
                <h2 className="text-sm font-semibold text-zinc-100">Create CronJob</h2>
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
                  placeholder="db-cleanup"
                  className="w-full px-3 py-2 rounded-lg border border-zinc-700 bg-zinc-800 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:border-violet-600 focus:ring-1 focus:ring-violet-600/30 font-mono"
                  autoFocus
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-zinc-400 mb-1.5">Schedule</label>
                <div className="flex flex-wrap gap-1.5 mb-2">
                  {CRON_PRESETS.map((preset) => (
                    <button
                      key={preset.label}
                      onClick={() => {
                        setSelectedPreset(preset.value);
                        if (preset.value) setNewSchedule(preset.value);
                      }}
                      className={`px-2 py-1 rounded text-xs transition-colors ${
                        selectedPreset === preset.value
                          ? "bg-violet-600/20 text-violet-400 border border-violet-600/40"
                          : "bg-zinc-800 text-zinc-500 border border-zinc-700 hover:border-zinc-600"
                      }`}
                    >
                      {preset.label}
                    </button>
                  ))}
                </div>
                <input
                  type="text"
                  value={newSchedule}
                  onChange={(e) => {
                    setNewSchedule(e.target.value);
                    setSelectedPreset("");
                  }}
                  placeholder="*/5 * * * *"
                  className="w-full px-3 py-2 rounded-lg border border-zinc-700 bg-zinc-800 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:border-violet-600 focus:ring-1 focus:ring-violet-600/30 font-mono"
                />
                <p className="text-xs text-zinc-600 mt-1">Standard cron syntax: minute hour day month weekday</p>
              </div>

              <div>
                <label className="block text-xs font-medium text-zinc-400 mb-1.5">Command (optional)</label>
                <input
                  type="text"
                  value={newCommand}
                  onChange={(e) => setNewCommand(e.target.value)}
                  placeholder="python manage.py cleanup"
                  className="w-full px-3 py-2 rounded-lg border border-zinc-700 bg-zinc-800 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:border-violet-600 focus:ring-1 focus:ring-violet-600/30 font-mono"
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
                  onClick={createJob}
                  disabled={!newName.trim() || !newSchedule.trim() || creating}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-violet-600 hover:bg-violet-700 text-white text-xs font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {creating && <Loader2 className="w-3 h-3 animate-spin" />}
                  Create
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Job list */}
      {jobs.length === 0 ? (
        <div className="text-center py-16 border border-dashed border-zinc-800 rounded-xl">
          <Timer className="w-8 h-8 mx-auto mb-2 text-zinc-700" />
          <p className="text-sm text-zinc-500">No scheduled jobs.</p>
          <p className="text-xs text-zinc-600 mt-1">Create a cron job to run tasks on a schedule.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {jobs.map((job) => (
            <div
              key={job.id}
              className="bg-zinc-900/50 border border-zinc-800 rounded-xl p-4 hover:border-zinc-700 transition-colors"
            >
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-zinc-200">{job.name}</span>
                    <Badge variant={!job.suspended ? "success" : "secondary"}>
                      {!job.suspended ? "active" : "suspended"}
                    </Badge>
                  </div>
                  <div className="flex items-center gap-3 mt-1.5 text-xs text-zinc-600">
                    <span className="flex items-center gap-1 font-mono">
                      <Clock className="w-3 h-3" />
                      {job.schedule}
                    </span>
                    {job.command && (
                      <span className="font-mono truncate max-w-[200px]">{job.command.join(" ")}</span>
                    )}
                  </div>
                  {(job.last_schedule || job.last_status) && (
                    <div className="flex items-center gap-3 mt-1 text-xs">
                      {job.last_schedule && (
                        <span className="flex items-center gap-1 text-zinc-500">
                          <CheckCircle2 className="w-3 h-3" />
                          Last: {new Date(job.last_schedule).toLocaleString()}
                        </span>
                      )}
                      {job.last_status && (
                        <Badge variant={job.last_status === "Complete" ? "success" : "destructive"}>
                          {job.last_status}
                        </Badge>
                      )}
                    </div>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => runNow(job.id, job.name)}
                    disabled={running === job.id}
                    className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-xs font-medium text-zinc-300 hover:text-zinc-100 transition-colors disabled:opacity-50"
                  >
                    {running === job.id ? (
                      <Loader2 className="w-3 h-3 animate-spin" />
                    ) : (
                      <Play className="w-3 h-3" />
                    )}
                    Run Now
                  </button>
                  <button
                    onClick={() => deleteJob(job.id, job.name)}
                    disabled={deleting === job.id}
                    className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium text-zinc-600 hover:text-red-400 hover:bg-red-950/30 transition-colors disabled:opacity-50"
                  >
                    {deleting === job.id ? (
                      <Loader2 className="w-3 h-3 animate-spin" />
                    ) : (
                      <Trash2 className="w-3 h-3" />
                    )}
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
