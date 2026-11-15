"use client";

import { useSearchParams } from "next/navigation";

import { PageHeader } from "@/components/shell/page-header";
import { isAdmin, useMe } from "@/components/shell/member-context";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DiagnosticsTab } from "./diagnostics-tab";
import { MembersTab } from "./members-tab";
import { extraSettingsTabs } from "./registry";

export function SettingsView() {
  const me = useMe();
  const params = useSearchParams();
  const tabs = extraSettingsTabs.filter((t) => (!t.adminOnly || isAdmin(me)) && (!t.ownerOnly || me.role === "owner"));
  return (
    <>
      <PageHeader title="Settings" description={isAdmin(me) ? "Workspace configuration." : "Only admins can change workspace settings."} />
      <Tabs defaultValue={params.get("tab") ?? tabs[0]?.id ?? "members"}>
        <TabsList className="mb-6">
          {tabs.map((t) => (
            <TabsTrigger key={t.id} value={t.id}>
              {t.label}
            </TabsTrigger>
          ))}
          <TabsTrigger value="members">Team</TabsTrigger>
          <TabsTrigger value="diagnostics">Diagnostics</TabsTrigger>
        </TabsList>
        {tabs.map((t) => (
          <TabsContent key={t.id} value={t.id}>
            <t.Component />
          </TabsContent>
        ))}
        <TabsContent value="members">
          <MembersTab />
        </TabsContent>
        <TabsContent value="diagnostics">
          <DiagnosticsTab />
        </TabsContent>
      </Tabs>
    </>
  );
}
