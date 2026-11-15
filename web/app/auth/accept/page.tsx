"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Clapperboard } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { supabaseBrowser } from "@/lib/supabase/client";

/** Landing page for invite and password-reset links: establish the session, then set a password. */
function Accept() {
  const router = useRouter();
  const params = useSearchParams();
  const reset = params.get("mode") === "reset";
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const sb = supabaseBrowser();
    const code = params.get("code");
    const tokenHash = params.get("token_hash");
    const type = params.get("type") as "invite" | "recovery" | "signup" | "email" | null;
    (async () => {
      if (code) {
        const { error } = await sb.auth.exchangeCodeForSession(code);
        if (error) return setFailed(error.message);
      } else if (tokenHash && type) {
        const { error } = await sb.auth.verifyOtp({ token_hash: tokenHash, type });
        if (error) return setFailed(error.message);
      } else if (window.location.hash.includes("access_token")) {
        const h = new URLSearchParams(window.location.hash.slice(1));
        const { error } = await sb.auth.setSession({
          access_token: h.get("access_token")!,
          refresh_token: h.get("refresh_token")!,
        });
        if (error) return setFailed(error.message);
        history.replaceState(null, "", window.location.pathname + window.location.search);
      } else if (window.location.hash.includes("error")) {
        const h = new URLSearchParams(window.location.hash.slice(1));
        return setFailed(h.get("error_description") ?? "This link is invalid or has expired.");
      }
      const { data } = await sb.auth.getSession();
      if (!data.session) return setFailed("This link is invalid or has expired. Ask an admin for a new invite.");
      if (params.get("mode") === "signup") {
        toast.success("Email confirmed. Welcome!");
        const next = params.get("next");
        router.replace(next && next.startsWith("/") && !next.startsWith("//") ? next : "/");
        router.refresh();
        return;
      }
      setReady(true);
    })();
  }, [params, router]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password.length < 10) return toast.error("Use at least 10 characters");
    setBusy(true);
    const { error } = await supabaseBrowser().auth.updateUser({ password });
    if (error) {
      setBusy(false);
      return toast.error(error.message);
    }
    if (name.trim()) await api("/me", { method: "PATCH", json: { display_name: name.trim() } }).catch(() => {});
    toast.success("You're all set");
    router.replace("/");
    router.refresh();
  };

  return (
    <div className="flex min-h-dvh flex-col items-center justify-center px-4">
      <div className="mb-8 flex items-center gap-2 text-xl font-semibold">
        <Clapperboard className="size-7 text-primary" /> Shorts Studio
      </div>
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>{reset ? "Choose a new password" : "Welcome to the team"}</CardTitle>
          <CardDescription>{reset ? "Enter a new password for your account." : "Set your name and a password to finish joining."}</CardDescription>
        </CardHeader>
        <CardContent>
          {failed ? (
            <p className="text-sm text-destructive">{failed}</p>
          ) : !ready ? (
            <p className="text-sm text-muted-foreground">Checking your link…</p>
          ) : (
            <form onSubmit={submit} className="grid gap-4">
              {!reset && (
                <Field label="Your name" htmlFor="name">
                  <Input id="name" value={name} onChange={(e) => setName(e.target.value)} maxLength={80} />
                </Field>
              )}
              <Field label="Password" htmlFor="pw" hint="At least 10 characters">
                <Input id="pw" type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
              </Field>
              <Button disabled={busy}>{busy ? "Saving…" : "Continue"}</Button>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default function AcceptPage() {
  return (
    <Suspense>
      <Accept />
    </Suspense>
  );
}
