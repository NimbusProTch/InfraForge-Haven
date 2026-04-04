"use client";

import { useState } from "react";
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
import { Plus } from "lucide-react";
import { ServiceIcon } from "@/components/icons/ServiceIcons";

interface AddServiceModalProps {
  tenantSlug: string;
  accessToken?: string;
  onCreated?: (service: ManagedService) => void;
}

export function AddServiceModal({ tenantSlug, accessToken, onCreated }: AddServiceModalProps) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [serviceType, setServiceType] = useState<string>("postgres");
  const [tier, setTier] = useState<string>("dev");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const svc = await api.services.create(
        tenantSlug,
        { name, service_type: serviceType, tier },
        accessToken
      );
      onCreated?.(svc);
      setOpen(false);
      setName("");
      setServiceType("postgres");
      setTier("dev");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create service");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">
          <Plus className="h-4 w-4 mr-1" />
          Add Service
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Add Managed Service</DialogTitle>
          <DialogDescription>
            Provision a managed database, cache, or message queue for this tenant.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4 mt-2">
          <div className="space-y-1">
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
            <p className="text-xs text-muted-foreground">Lowercase letters, numbers, hyphens only.</p>
          </div>

          <div className="space-y-1">
            <Label htmlFor="svc-type">Type</Label>
            <Select value={serviceType} onValueChange={setServiceType}>
              <SelectTrigger id="svc-type">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="postgres">
                  <span className="flex items-center gap-2"><ServiceIcon type="postgres" size={16} /> PostgreSQL</span>
                </SelectItem>
                <SelectItem value="mysql">
                  <span className="flex items-center gap-2"><ServiceIcon type="mysql" size={16} /> MySQL</span>
                </SelectItem>
                <SelectItem value="mongodb">
                  <span className="flex items-center gap-2"><ServiceIcon type="mongodb" size={16} /> MongoDB</span>
                </SelectItem>
                <SelectItem value="redis">
                  <span className="flex items-center gap-2"><ServiceIcon type="redis" size={16} /> Redis</span>
                </SelectItem>
                <SelectItem value="rabbitmq">
                  <span className="flex items-center gap-2"><ServiceIcon type="rabbitmq" size={16} /> RabbitMQ</span>
                </SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1">
            <Label htmlFor="svc-tier">Tier</Label>
            <Select value={tier} onValueChange={setTier}>
              <SelectTrigger id="svc-tier">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="dev">Dev (single replica, small storage)</SelectItem>
                <SelectItem value="prod">Prod (HA, larger storage)</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}

          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={loading}>
              {loading ? "Provisioning..." : "Create"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
