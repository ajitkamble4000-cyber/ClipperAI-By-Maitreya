"use client";
import * as React from "react";
import * as T from "@radix-ui/react-tabs";
import { cn } from "@/lib/utils";

export const Tabs = T.Root;
export function TabsList({ className, ...p }: React.ComponentPropsWithoutRef<typeof T.List>) {
  return (
    <T.List
      className={cn("inline-flex h-10 max-w-full items-center gap-1 overflow-x-auto rounded-lg bg-muted p-1", className)}
      {...p}
    />
  );
}
export function TabsTrigger({ className, ...p }: React.ComponentPropsWithoutRef<typeof T.Trigger>) {
  return (
    <T.Trigger
      className={cn(
        "inline-flex h-8 items-center whitespace-nowrap rounded-md px-3 text-sm font-medium text-muted-foreground transition data-[state=active]:bg-background data-[state=active]:text-foreground",
        className,
      )}
      {...p}
    />
  );
}
export const TabsContent = T.Content;
