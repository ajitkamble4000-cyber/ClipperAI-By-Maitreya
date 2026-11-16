"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { supabaseBrowser } from "@/lib/supabase/client";
import { siteUrl } from "@/lib/routes";
import { env } from "@/lib/env";

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    const { error } = await supabaseBrowser().auth.signInWithPassword({ email, password });
    setBusy(false);
    if (error) return toast.error(error.message);
    const next = params.get("next");
    router.replace(next && next.startsWith("/") && !next.startsWith("//") ? next : "/");
    router.refresh();
  };

  const forgot = async () => {
    if (!email) return toast.error("Enter your email first");
    const { error } = await supabaseBrowser().auth.resetPasswordForEmail(email, {
      redirectTo: siteUrl("/auth/accept?mode=reset"),
    });
    if (error) toast.error(error.message);
    else toast.success("If that email has an account, a reset link is on its way.");
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Sign in</CardTitle>
        <CardDescription>
          New here?{" "}
          <Link href="/signup" className="text-primary underline-offset-4 hover:underline">
            Create a free account
          </Link>{" "}
          and get 1,000 tokens every day.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="grid gap-4">
          <Field label="Email" htmlFor="email">
            <Input id="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
          <Field label="Password" htmlFor="password">
            <Input id="password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
          </Field>
          <Button type="submit" disabled={busy || !env.configured}>
            {busy ? "Signing in…" : "Sign in"}
          </Button>
          <button type="button" onClick={forgot} className="text-sm text-muted-foreground hover:text-foreground">
            Forgot password?
          </button>
        </form>
      </CardContent>
    </Card>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
