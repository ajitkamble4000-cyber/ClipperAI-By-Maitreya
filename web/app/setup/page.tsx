"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Clapperboard } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { supabaseBrowser } from "@/lib/supabase/client";

export default function SetupPage() {
  const router = useRouter();
  const [needed, setNeeded] = useState<boolean | null>(null);
  const [form, setForm] = useState({ token: "", email: "", password: "", display_name: "" });
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<{ needs_setup: boolean }>("/setup/status").then((r) => setNeeded(r.needs_setup)).catch(() => setNeeded(false));
  }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api("/setup", { method: "POST", json: form });
      await supabaseBrowser().auth.signInWithPassword({ email: form.email, password: form.password });
      toast.success("Workspace created. You're the admin.");
      router.replace("/");
      router.refresh();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });

  return (
    <div className="flex min-h-dvh flex-col items-center justify-center px-4">
      <div className="mb-8 flex items-center gap-2 text-xl font-semibold">
        <Clapperboard className="size-7 text-primary" /> Shorts Studio
      </div>
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>First-time setup</CardTitle>
          <CardDescription>Create the admin account. This page only works once.</CardDescription>
        </CardHeader>
        <CardContent>
          {needed === null ? (
            <p className="text-sm text-muted-foreground">Checking…</p>
          ) : !needed ? (
            <p className="text-sm text-muted-foreground">Setup is already done. <a className="text-primary" href="/login">Sign in</a>.</p>
          ) : (
            <form onSubmit={submit} className="grid gap-4">
              <Field label="Setup token" htmlFor="token" hint="The SETUP_TOKEN value from the server's environment.">
                <Input id="token" type="password" required value={form.token} onChange={set("token")} />
              </Field>
              <Field label="Your name" htmlFor="name">
                <Input id="name" value={form.display_name} onChange={set("display_name")} />
              </Field>
              <Field label="Email" htmlFor="email">
                <Input id="email" type="email" required value={form.email} onChange={set("email")} />
              </Field>
              <Field label="Password" htmlFor="password" hint="At least 10 characters">
                <Input id="password" type="password" minLength={10} required value={form.password} onChange={set("password")} />
              </Field>
              <Button disabled={busy}>{busy ? "Creating…" : "Create workspace"}</Button>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
