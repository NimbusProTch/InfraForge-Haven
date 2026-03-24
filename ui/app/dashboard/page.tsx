import { getServerSession } from "next-auth";
import { redirect } from "next/navigation";
import Link from "next/link";
import { authOptions } from "@/lib/auth";
import { api, type Tenant } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Building2, LogOut, Plus } from "lucide-react";

async function getTenants(token?: string): Promise<Tenant[]> {
  try {
    return await api.tenants.list(token);
  } catch {
    return [];
  }
}

export default async function DashboardPage() {
  const session = await getServerSession(authOptions);
  if (!session) redirect("/auth/signin");

  const accessToken = (session as typeof session & { accessToken?: string }).accessToken;
  const tenants = await getTenants(accessToken);

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b">
        <div className="container flex h-16 items-center justify-between">
          <div className="flex items-center gap-2">
            <Building2 className="h-6 w-6 text-primary" />
            <span className="font-semibold text-lg">Haven Platform</span>
          </div>
          <div className="flex items-center gap-4">
            <span className="text-sm text-muted-foreground">{session.user?.email}</span>
            <Button variant="ghost" size="sm" asChild>
              <Link href="/api/auth/signout">
                <LogOut className="h-4 w-4 mr-1" />
                Sign out
              </Link>
            </Button>
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="container py-8">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold">Tenants</h1>
            <p className="text-muted-foreground mt-1">
              {tenants.length} tenant{tenants.length !== 1 ? "s" : ""} registered
            </p>
          </div>
          <Button asChild>
            <Link href="/tenants/new">
              <Plus className="h-4 w-4 mr-1" />
              New Tenant
            </Link>
          </Button>
        </div>

        {tenants.length === 0 ? (
          <div className="text-center py-16 text-muted-foreground">
            <Building2 className="h-12 w-12 mx-auto mb-4 opacity-40" />
            <p className="text-lg">No tenants yet</p>
            <p className="text-sm mt-1">Create your first tenant to get started.</p>
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {tenants.map((tenant) => (
              <Link key={tenant.id} href={`/tenants/${tenant.slug}`}>
                <Card className="hover:shadow-md transition-shadow cursor-pointer">
                  <CardHeader>
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-lg">{tenant.name}</CardTitle>
                      <Badge variant={tenant.active ? "success" : "secondary"}>
                        {tenant.active ? "Active" : "Inactive"}
                      </Badge>
                    </div>
                    <CardDescription className="font-mono text-xs">{tenant.slug}</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <dl className="grid grid-cols-3 gap-2 text-sm">
                      <div>
                        <dt className="text-muted-foreground">CPU</dt>
                        <dd className="font-medium">{tenant.cpu_limit}</dd>
                      </div>
                      <div>
                        <dt className="text-muted-foreground">Memory</dt>
                        <dd className="font-medium">{tenant.memory_limit}</dd>
                      </div>
                      <div>
                        <dt className="text-muted-foreground">Storage</dt>
                        <dd className="font-medium">{tenant.storage_limit}</dd>
                      </div>
                    </dl>
                  </CardContent>
                </Card>
              </Link>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
