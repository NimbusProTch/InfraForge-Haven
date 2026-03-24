import { getServerSession } from "next-auth";
import { redirect, notFound } from "next/navigation";
import Link from "next/link";
import { authOptions } from "@/lib/auth";
import { api, type Application, type ManagedService, type Tenant } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { AddServiceModal } from "@/components/AddServiceModal";
import { ArrowLeft, Box, Database, Layers } from "lucide-react";

const SERVICE_TYPE_ICONS: Record<string, string> = {
  postgres: "🐘",
  redis: "🔴",
  rabbitmq: "🐰",
};

const STATUS_VARIANT: Record<string, "default" | "success" | "warning" | "destructive" | "secondary"> = {
  ready: "success",
  provisioning: "warning",
  failed: "destructive",
  deleting: "secondary",
};

interface TenantDetailPageProps {
  params: { slug: string };
}

export default async function TenantDetailPage({ params }: TenantDetailPageProps) {
  const session = await getServerSession(authOptions);
  if (!session) redirect("/auth/signin");

  const accessToken = (session as typeof session & { accessToken?: string }).accessToken;

  let tenant: Tenant;
  let apps: Application[];
  let services: ManagedService[];

  try {
    [tenant, apps, services] = await Promise.all([
      api.tenants.get(params.slug, accessToken),
      api.apps.list(params.slug, accessToken),
      api.services.list(params.slug, accessToken),
    ]);
  } catch {
    notFound();
  }

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b">
        <div className="container flex h-16 items-center gap-4">
          <Button variant="ghost" size="sm" asChild>
            <Link href="/dashboard">
              <ArrowLeft className="h-4 w-4 mr-1" />
              Back
            </Link>
          </Button>
          <div className="flex items-center gap-2">
            <Layers className="h-5 w-5 text-primary" />
            <span className="font-semibold">{tenant.name}</span>
            <Badge variant={tenant.active ? "success" : "secondary"} className="ml-1">
              {tenant.active ? "Active" : "Inactive"}
            </Badge>
          </div>
        </div>
      </header>

      <main className="container py-8 space-y-8">
        {/* Tenant info */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base font-medium text-muted-foreground">
              Tenant Details
            </CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
              <div>
                <dt className="text-muted-foreground">Slug</dt>
                <dd className="font-mono font-medium">{tenant.slug}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Namespace</dt>
                <dd className="font-mono font-medium">{tenant.namespace}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">CPU Limit</dt>
                <dd className="font-medium">{tenant.cpu_limit}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Memory Limit</dt>
                <dd className="font-medium">{tenant.memory_limit}</dd>
              </div>
            </dl>
          </CardContent>
        </Card>

        {/* Applications */}
        <section>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-semibold flex items-center gap-2">
              <Box className="h-5 w-5" />
              Applications
              <span className="text-sm font-normal text-muted-foreground">({apps.length})</span>
            </h2>
          </div>

          {apps.length === 0 ? (
            <p className="text-muted-foreground text-sm py-4">No applications deployed yet.</p>
          ) : (
            <div className="grid gap-3 md:grid-cols-2">
              {apps.map((app) => (
                <Link key={app.id} href={`/tenants/${params.slug}/apps/${app.slug}`}>
                  <Card className="hover:shadow-md transition-shadow cursor-pointer">
                    <CardHeader className="pb-2">
                      <div className="flex items-center justify-between">
                        <CardTitle className="text-base">{app.name}</CardTitle>
                      </div>
                      <CardDescription className="font-mono text-xs">{app.repo_url}</CardDescription>
                    </CardHeader>
                    <CardContent className="pt-0">
                      <p className="text-sm text-muted-foreground">
                        Branch: <span className="font-medium text-foreground">{app.branch}</span>
                        {" · "}
                        Replicas: <span className="font-medium text-foreground">{app.replicas}</span>
                      </p>
                    </CardContent>
                  </Card>
                </Link>
              ))}
            </div>
          )}
        </section>

        {/* Managed Services */}
        <section>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-semibold flex items-center gap-2">
              <Database className="h-5 w-5" />
              Managed Services
              <span className="text-sm font-normal text-muted-foreground">({services.length})</span>
            </h2>
            <AddServiceModal
              tenantSlug={params.slug}
              accessToken={accessToken}
              onCreated={() => {}}
            />
          </div>

          {services.length === 0 ? (
            <p className="text-muted-foreground text-sm py-4">
              No managed services. Add PostgreSQL, Redis, or RabbitMQ.
            </p>
          ) : (
            <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
              {services.map((svc) => (
                <Card key={svc.id}>
                  <CardHeader className="pb-2">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-base flex items-center gap-1.5">
                        <span>{SERVICE_TYPE_ICONS[svc.service_type]}</span>
                        {svc.name}
                      </CardTitle>
                      <Badge variant={STATUS_VARIANT[svc.status] ?? "secondary"}>
                        {svc.status}
                      </Badge>
                    </div>
                    <CardDescription>
                      {svc.service_type} · {svc.tier}
                    </CardDescription>
                  </CardHeader>
                  {svc.connection_hint && (
                    <CardContent className="pt-0">
                      <p className="text-xs font-mono text-muted-foreground truncate">
                        {svc.connection_hint}
                      </p>
                    </CardContent>
                  )}
                </Card>
              ))}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
