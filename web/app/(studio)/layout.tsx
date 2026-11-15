import { redirect } from "next/navigation";
import { AppShell } from "@/components/shell/app-shell";
import type { Me } from "@/components/shell/member-context";
import { supabaseServer } from "@/lib/supabase/server";

export default async function StudioLayout({ children }: { children: React.ReactNode }) {
  const sb = await supabaseServer();
  const {
    data: { user },
  } = await sb.auth.getUser();
  if (!user) redirect("/login");
  // RLS only returns member rows to members, so a non-member gets nothing here.
  const { data: me } = await sb.from("members").select("user_id, email, role, display_name").eq("user_id", user.id).maybeSingle();
  if (!me) {
    return (
      <div className="flex min-h-dvh items-center justify-center px-4 text-center">
        <div>
          <h1 className="text-xl font-semibold">You're not a member of this workspace</h1>
          <p className="mt-2 text-sm text-muted-foreground">Signed in as {user.email}. Ask an admin to invite this email.</p>
        </div>
      </div>
    );
  }
  return <AppShell me={me as Me}>{children}</AppShell>;
}
