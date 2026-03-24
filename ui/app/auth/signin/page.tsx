"use client";

import { signIn } from "next-auth/react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function SignInPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <Card className="w-full max-w-sm">
        <CardHeader className="text-center">
          <CardTitle className="text-2xl">Haven Platform</CardTitle>
          <CardDescription>Sign in with your organization account</CardDescription>
        </CardHeader>
        <CardContent>
          <Button
            className="w-full"
            onClick={() => signIn("keycloak", { callbackUrl: "/dashboard" })}
          >
            Sign in with Keycloak
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
