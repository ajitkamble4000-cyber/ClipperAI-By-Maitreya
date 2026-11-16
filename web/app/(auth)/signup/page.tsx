"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { MailCheck } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { useSiteStatus } from "@/components/shell/site-banner";
import { supabaseBrowser } from "@/lib/supabase/client";

export default function SignupPage() {
  return (
    <Suspense>
      <Signup />
    </Suspense>
  );
}

function Signup() {
  const router = useRouter();
  const params = useSearchParams();
  const raw = params.get("next");
  const next = raw && raw.startsWith("/") && !raw.startsWith("//") ? raw : "/";
  const ref = (params.get("ref") ?? "").toLowerCase().replace(/[^a-z0-9]/g, "").slice(0, 16);
  const site = useSiteStatus();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password.length < 10) return toast.error("Use at least 10 characters for your password");
    setBusy(true);
    const { data, error } = await supabaseBrowser().auth.signUp({
      email: email.trim().toLowerCase(),
      password,
      options: { data: { display_name: name.trim(), ...(ref ? { ref } : {}) }, emailRedirectTo: `${window.location.origin}/auth/accept?mode=signup&next=${encodeURIComponent(next)}` },
    });
    setBusy(false);
    if (error) return toast.error(/closed/i.test(error.message) || /Database error/i.test(error.message) ? "Sign-ups are closed right now." : error.message);
    if (data.session) {
      router.replace(next);
      router.refresh();
    } else {
      setSent(true); // email confirmation is on: the account opens from the link
    }
  };

  if (sent) {
    return (
      <Card>
        <CardHeader>
          <MailCheck className="mb-2 size-8 text-primary" />
          <CardTitle>Check your email</CardTitle>
          <CardDescription>
            We sent a link to <b>{email}</b>. Open it to confirm your address and start creating.
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  if (site && !site.signups_open) {
    return (
      <Card data-testid="signups-closed">
        <CardHeader>
          <CardTitle>Sign-ups are closed right now</CardTitle>
          <CardDescription>
            We&apos;re not taking new accounts at the moment. Have an account?{" "}
            <Link href="/login" className="text-primary hover:underline">
              Sign in
            </Link>
            .
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        {ref && site && site.referral_reward > 0 && (
          <p className="mb-2 rounded-lg bg-primary/10 px-3 py-2 text-sm text-primary" data-testid="referral-note">
            A friend invited you: you&apos;ll both get {site.referral_reward.toLocaleString()} bonus tokens after your first video.
          </p>
        )}
        <CardTitle>Create your free account</CardTitle>
        <CardDescription>1,000 tokens every day: enough for several captioned videos. No card needed.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="grid gap-4">
          <Field label="Your name" htmlFor="name">
            <Input id="name" autoComplete="name" required maxLength={80} value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field label="Email" htmlFor="email">
            <Input id="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
          <Field label="Password" htmlFor="password" hint="At least 10 characters">
            <Input id="password" type="password" autoComplete="new-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
          </Field>
          <Button type="submit" disabled={busy}>
            {busy ? "Creating…" : "Create account"}
          </Button>
          <p className="text-center text-sm text-muted-foreground">
            Have an account?{" "}
            <Link href="/login" className="text-primary hover:underline">
              Sign in
            </Link>
          </p>
          <p className="text-center text-xs text-muted-foreground">
            By creating an account you agree to use the service only for videos you have the rights to.
          </p>
        </form>
      </CardContent>
    </Card>
  );
}
