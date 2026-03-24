import { getServerSession } from "next-auth";
import { redirect, notFound } from "next/navigation";
import Link from "next/link";
import { authOptions } from "@/lib/auth";
import { api, type Application } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ArrowLeft, GitBranch, GitCommit, Server } from "lucide-react";

interface AppDetailPageProps {
  params: { slug: string; appSlug: string };
}

const DEPLOY_STATUS_VARIANT: Record<string, "default" | "success" | "warning" | "destructive" | "secondary"> = {
  running: "success",
  building: "warning",
  deploying: "warning",
  pending: "secondary",
  failed: "destructive",
};

export default async function AppDetailPage({ params }: AppDetailPageProps) {
  const session = await getServerSession(authOptions);
  if (!session) redirect("/auth/signin");

  const accessToken = (session as typeof session & { accessToken?: string }).accessToken;

  let app: Application;
  try {
    app = await api.apps.get(params.slug, params.appSlug, accessToken);
  } catch {
    notFound();
  }

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b">
        <div className="container flex h-16 items-center gap-4">
          <Button variant="ghost" size="sm" asChild>
            <Link href={`/tenants/${params.slug}`}>
              <ArrowLeft className="h-4 w-4 mr-1" />
              Back
            </Link>
          </Button>
          <div className="flex items-center gap-2">
            <Server className="h-5 w-5 text-primary" />
            <span className="font-semibold">{app.name}</span>
            <span className="text-muted-foreground text-sm">/{params.slug}</span>
          </div>
        </div>
      </header>

      <main className="container py-8 space-y-8">
        {/* App info */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base font-medium text-muted-foreground">
              Application Details
            </CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="grid grid-cols-2 md:grid-cols-3 gap-4 text-sm">
              <div>
                <dt className="text-muted-foreground">Repository</dt>
                <dd className="font-mono font-medium truncate">{app.repo_url}</dd>
              </div>
              <div>
                <dt className="flex items-center gap-1 text-muted-foreground">
                  <GitBranch className="h-3 w-3" />
                  Branch
                </dt>
                <dd className="font-medium">{app.branch}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Replicas</dt>
                <dd className="font-medium">{app.replicas}</dd>
              </div>
              {app.image_tag && (
                <div className="col-span-2 md:col-span-3">
                  <dt className="text-muted-foreground">Image</dt>
                  <dd className="font-mono text-xs">{app.image_tag}</dd>
                </div>
              )}
            </dl>
          </CardContent>
        </Card>

        {/* Deployment history placeholder */}
        <section>
          <h2 className="text-xl font-semibold flex items-center gap-2 mb-4">
            <GitCommit className="h-5 w-5" />
            Deployment History
          </h2>
          <Card>
            <CardContent className="py-8 text-center text-muted-foreground">
              <GitCommit className="h-10 w-10 mx-auto mb-3 opacity-30" />
              <p>No deployments yet.</p>
              <p className="text-sm mt-1">Push to the repository to trigger a build.</p>
            </CardContent>
          </Card>
        </section>

        {/* Log viewer placeholder */}
        <section>
          <h2 className="text-xl font-semibold mb-4">Live Logs</h2>
          <Card>
            <CardContent className="py-0">
              <pre className="bg-black text-green-400 rounded-md p-4 text-xs font-mono overflow-auto min-h-[120px] max-h-64">
                {"# Logs will stream here when a deployment is running...\n"}
              </pre>
            </CardContent>
          </Card>
        </section>
      </main>
    </div>
  );
}
