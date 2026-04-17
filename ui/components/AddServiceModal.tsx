"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api, type ManagedService } from "@/lib/api";
import { Plus, Server, Zap, Shield, Clock, ChevronLeft, HardDrive, RotateCcw, Database } from "lucide-react";
import { ServiceIcon } from "@/components/icons/ServiceIcons";

interface AddServiceModalProps {
  tenantSlug: string;
  appSlug?: string;
  accessToken?: string;
  onCreated?: (service: ManagedService) => void;
}

const SERVICE_TYPES = [
  {
    value: "postgres",
    label: "PostgreSQL",
    description: "Reliable relational database with PITR backup",
    supportsBackup: true,
    supportsPitr: true,
    hasDbName: true,
  },
  {
    value: "mysql",
    label: "MySQL",
    description: "Popular relational database with XtraDB Cluster",
    supportsBackup: true,
    supportsPitr: false,
    hasDbName: true,
  },
  {
    value: "mongodb",
    label: "MongoDB",
    description: "Flexible document database for modern apps",
    supportsBackup: true,
    supportsPitr: false,
    hasDbName: true,
  },
  {
    value: "redis",
    label: "Redis",
    description: "In-memory data store for caching and sessions",
    supportsBackup: false,
    supportsPitr: false,
    hasDbName: false,
  },
  {
    value: "rabbitmq",
    label: "RabbitMQ",
    description: "Distributed message broker for async workflows",
    supportsBackup: false,
    supportsPitr: false,
    hasDbName: false,
  },
  {
    value: "kafka",
    label: "Apache Kafka",
    description: "Distributed event streaming platform for real-time data pipelines",
    supportsBackup: false,
    supportsPitr: false,
    hasDbName: false,
  },
] as const;

const SCHEDULE_PRESETS = [
  { value: "0 2 * * *", label: "Daily at 2am" },
  { value: "0 */12 * * *", label: "Every 12 hours" },
  { value: "0 */6 * * *", label: "Every 6 hours" },
] as const;

const RETENTION_OPTIONS = [
  { value: "7", label: "7 days" },
  { value: "14", label: "14 days" },
  { value: "30", label: "30 days" },
  { value: "90", label: "90 days" },
] as const;

export function AddServiceModal({ tenantSlug, appSlug, accessToken, onCreated }: AddServiceModalProps) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState<"type" | "config">("type");
  const [name, setName] = useState("");
  const [serviceType, setServiceType] = useState<string>("");
  const [tier, setTier] = useState<string>("dev");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Database config
  const [dbName, setDbName] = useState("");
  const [dbUser, setDbUser] = useState("");

  // Backup config state
  const [backupEnabled, setBackupEnabled] = useState(false);
  const [backupSchedule, setBackupSchedule] = useState("0 2 * * *");
  const [backupRetention, setBackupRetention] = useState("7");
  const [pitrEnabled, setPitrEnabled] = useState(false);

  // Auto-connect
  const [autoConnect, setAutoConnect] = useState(true);

  const selectedType = SERVICE_TYPES.find((t) => t.value === serviceType);

  // Auto-generate name when type is selected
  useEffect(() => {
    if (serviceType && step === "config") {
      const prefix = appSlug ?? "app";
      const typeShort = serviceType === "postgres" ? "pg" : serviceType;
      setName(`${prefix}-${typeShort}`);
    }
  }, [serviceType, step, appSlug]);

  // Auto-enable backup for prod tier on backup-supported types
  useEffect(() => {
    if (selectedType?.supportsBackup) {
      setBackupEnabled(tier === "prod");
    } else {
      setBackupEnabled(false);
    }
  }, [tier, selectedType]);

  function resetForm() {
    setStep("type");
    setName("");
    setServiceType("");
    setTier("dev");
    setDbName("");
    setDbUser("");
    setBackupEnabled(false);
    setBackupSchedule("0 2 * * *");
    setBackupRetention("7");
    setPitrEnabled(false);
    setAutoConnect(true);
    setError(null);
  }

  function handleSelectType(type: string) {
    setServiceType(type);
    setStep("config");
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const payload: Record<string, unknown> = { name, service_type: serviceType, tier };
      if (dbName.trim()) payload.db_name = dbName.trim();
      if (dbUser.trim()) payload.db_user = dbUser.trim();

      const svc = await api.services.create(
        tenantSlug,
        payload as { name: string; service_type: string; tier: string },
        accessToken
      );

      // Auto-connect to current app if requested
      if (autoConnect && appSlug) {
        try {
          await api.services.connectToApp(tenantSlug, appSlug, svc.name, accessToken);
        } catch {
          // Connection may fail if service is still provisioning — that's OK
        }
      }

      onCreated?.(svc);
      setOpen(false);
      resetForm();
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create service");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        setOpen(v);
        if (!v) resetForm();
      }}
    >
      <DialogTrigger asChild>
        <Button size="sm">
          <Plus className="h-4 w-4 mr-1" />
          Add Service
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {step === "type" ? "Choose Service Type" : "Configure Service"}
          </DialogTitle>
          <DialogDescription>
            {step === "type"
              ? "Select the type of managed service to provision."
              : `Set up your ${selectedType?.label ?? ""} instance.`}
          </DialogDescription>
        </DialogHeader>

        {step === "type" ? (
          /* Step 1: Service Type Selection */
          <div className="grid grid-cols-2 gap-3 mt-2">
            {SERVICE_TYPES.map((svc) => (
              <button
                key={svc.value}
                type="button"
                onClick={() => handleSelectType(svc.value)}
                className="flex flex-col items-center gap-2 p-4 rounded-xl border border-gray-200 dark:border-zinc-800 bg-white dark:bg-zinc-900/50 hover:border-blue-400 dark:hover:border-blue-500 hover:bg-blue-50/50 dark:hover:bg-blue-950/20 transition-all text-center group"
              >
                <ServiceIcon type={svc.value} size={40} />
                <div>
                  <p className="text-sm font-semibold text-gray-800 dark:text-zinc-200 group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors">
                    {svc.label}
                  </p>
                  <p className="text-xs text-gray-400 dark:text-zinc-500 mt-0.5 leading-relaxed">
                    {svc.description}
                  </p>
                </div>
              </button>
            ))}
          </div>
        ) : (
          /* Step 2: Configuration */
          <form onSubmit={handleSubmit} className="space-y-5 mt-2">
            <button
              type="button"
              onClick={() => setStep("type")}
              className="flex items-center gap-1 text-xs text-gray-400 dark:text-zinc-500 hover:text-gray-700 dark:hover:text-zinc-300 transition-colors -mt-1"
            >
              <ChevronLeft className="w-3 h-3" />
              Change type
            </button>

            {/* Selected type indicator */}
            <div className="flex items-center gap-3 p-3 rounded-lg bg-gray-50 dark:bg-zinc-800/50 border border-gray-200 dark:border-zinc-700">
              <ServiceIcon type={serviceType} size={28} />
              <div>
                <p className="text-sm font-medium text-gray-800 dark:text-zinc-200">{selectedType?.label}</p>
                <p className="text-xs text-gray-400 dark:text-zinc-500">{selectedType?.description}</p>
              </div>
            </div>

            {/* Service name */}
            <div className="space-y-1.5">
              <Label htmlFor="svc-name">Service name</Label>
              <Input
                id="svc-name"
                placeholder="my-database"
                value={name}
                onChange={(e) => setName(e.target.value)}
                pattern="^[a-z0-9][a-z0-9-]*[a-z0-9]$"
                minLength={2}
                required
              />
              <p className="text-xs text-muted-foreground">
                Lowercase letters, numbers, hyphens only.
              </p>
            </div>

            {/* Database name & user — only for DB types */}
            {selectedType?.hasDbName && (
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label htmlFor="db-name" className="flex items-center gap-1.5">
                    <Database className="w-3 h-3" />
                    Database name
                  </Label>
                  <Input
                    id="db-name"
                    placeholder={`${(appSlug ?? "app").replace(/-/g, "_")}_db`}
                    value={dbName}
                    onChange={(e) => setDbName(e.target.value)}
                    pattern="^[a-z][a-z0-9_]*$"
                  />
                  <p className="text-xs text-muted-foreground">Optional. Auto-generated if empty.</p>
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="db-user">Database user</Label>
                  <Input
                    id="db-user"
                    placeholder="app_user"
                    value={dbUser}
                    onChange={(e) => setDbUser(e.target.value)}
                    pattern="^[a-z][a-z0-9_]*$"
                  />
                  <p className="text-xs text-muted-foreground">Optional. Auto-generated if empty.</p>
                </div>
              </div>
            )}

            {/* Tier selection */}
            <div className="space-y-1.5">
              <Label>Environment tier</Label>
              <div className="grid grid-cols-2 gap-3">
                <button
                  type="button"
                  onClick={() => setTier("dev")}
                  aria-pressed={tier === "dev"}
                  className={`flex flex-col items-start p-3 rounded-xl border-2 transition-all text-left ${
                    tier === "dev"
                      ? "border-blue-500 bg-blue-50/50 dark:bg-blue-950/20"
                      : "border-gray-200 dark:border-zinc-800 hover:border-gray-300 dark:hover:border-zinc-700"
                  }`}
                >
                  <div className="flex items-center gap-2 mb-2">
                    <Zap className="w-4 h-4 text-amber-500" />
                    <span className="text-sm font-semibold text-gray-800 dark:text-zinc-200">Dev</span>
                  </div>
                  <ul className="space-y-1 text-xs text-gray-500 dark:text-zinc-400">
                    <li className="flex items-center gap-1.5"><Server className="w-3 h-3 shrink-0" /> 1 replica</li>
                    <li className="flex items-center gap-1.5"><HardDrive className="w-3 h-3 shrink-0" /> Ephemeral</li>
                    <li className="flex items-center gap-1.5"><Shield className="w-3 h-3 shrink-0 opacity-40" /> No backup</li>
                  </ul>
                </button>

                <button
                  type="button"
                  onClick={() => setTier("prod")}
                  aria-pressed={tier === "prod"}
                  className={`flex flex-col items-start p-3 rounded-xl border-2 transition-all text-left ${
                    tier === "prod"
                      ? "border-blue-500 bg-blue-50/50 dark:bg-blue-950/20"
                      : "border-gray-200 dark:border-zinc-800 hover:border-gray-300 dark:hover:border-zinc-700"
                  }`}
                >
                  <div className="flex items-center gap-2 mb-2">
                    <Shield className="w-4 h-4 text-emerald-500" />
                    <span className="text-sm font-semibold text-gray-800 dark:text-zinc-200">Prod</span>
                  </div>
                  <ul className="space-y-1 text-xs text-gray-500 dark:text-zinc-400">
                    <li className="flex items-center gap-1.5"><Server className="w-3 h-3 shrink-0" /> 3 replicas, HA</li>
                    <li className="flex items-center gap-1.5"><HardDrive className="w-3 h-3 shrink-0" /> Persistent</li>
                    <li className="flex items-center gap-1.5"><Shield className="w-3 h-3 shrink-0" /> Daily backup</li>
                  </ul>
                </button>
              </div>
            </div>

            {/* Backup configuration */}
            {selectedType?.supportsBackup && (
              <div className="space-y-3 rounded-xl border border-gray-200 dark:border-zinc-800 p-4 bg-gray-50/50 dark:bg-zinc-800/30">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <RotateCcw className="w-4 h-4 text-gray-500 dark:text-zinc-400" />
                    <Label className="cursor-pointer">Enable automated backups</Label>
                  </div>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={backupEnabled}
                    onClick={() => setBackupEnabled(!backupEnabled)}
                    className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent transition-colors ${
                      backupEnabled ? "bg-blue-500" : "bg-gray-300 dark:bg-zinc-700"
                    }`}
                  >
                    <span className={`pointer-events-none block h-3.5 w-3.5 rounded-full bg-white shadow-sm transition-transform ${
                      backupEnabled ? "translate-x-4" : "translate-x-0.5"
                    }`} />
                  </button>
                </div>

                {backupEnabled && (
                  <div className="space-y-3 pt-1">
                    <div className="space-y-1">
                      <Label htmlFor="backup-schedule" className="text-xs">
                        <Clock className="w-3 h-3 inline mr-1" />
                        Schedule
                      </Label>
                      <Select value={backupSchedule} onValueChange={setBackupSchedule}>
                        <SelectTrigger id="backup-schedule" className="h-8 text-xs">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {SCHEDULE_PRESETS.map((p) => (
                            <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>

                    <div className="space-y-1">
                      <Label htmlFor="backup-retention" className="text-xs">
                        <HardDrive className="w-3 h-3 inline mr-1" />
                        Retention
                      </Label>
                      <Select value={backupRetention} onValueChange={setBackupRetention}>
                        <SelectTrigger id="backup-retention" className="h-8 text-xs">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {RETENTION_OPTIONS.map((r) => (
                            <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>

                    {selectedType?.supportsPitr && (
                      <div className="flex items-center justify-between pt-1">
                        <Label className="text-xs cursor-pointer">Enable point-in-time recovery (PITR)</Label>
                        <button
                          type="button"
                          role="switch"
                          aria-checked={pitrEnabled}
                          onClick={() => setPitrEnabled(!pitrEnabled)}
                          className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent transition-colors ${
                            pitrEnabled ? "bg-blue-500" : "bg-gray-300 dark:bg-zinc-700"
                          }`}
                        >
                          <span className={`pointer-events-none block h-3.5 w-3.5 rounded-full bg-white shadow-sm transition-transform ${
                            pitrEnabled ? "translate-x-4" : "translate-x-0.5"
                          }`} />
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Auto-connect toggle */}
            {appSlug && (
              <div className="flex items-center justify-between py-2">
                <div>
                  <Label className="cursor-pointer">Auto-connect to this application</Label>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Automatically inject connection credentials after provisioning.
                  </p>
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-checked={autoConnect}
                  onClick={() => setAutoConnect(!autoConnect)}
                  className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent transition-colors ${
                    autoConnect ? "bg-blue-500" : "bg-gray-300 dark:bg-zinc-700"
                  }`}
                >
                  <span className={`pointer-events-none block h-3.5 w-3.5 rounded-full bg-white shadow-sm transition-transform ${
                    autoConnect ? "translate-x-4" : "translate-x-0.5"
                  }`} />
                </button>
              </div>
            )}

            {error && <p className="text-sm text-destructive">{error}</p>}

            <div className="flex justify-end gap-2 pt-1">
              <Button type="button" variant="outline" onClick={() => setOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={loading}>
                {loading ? "Provisioning..." : "Create"}
              </Button>
            </div>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
