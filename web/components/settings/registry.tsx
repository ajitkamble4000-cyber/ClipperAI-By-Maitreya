"use client";

import type { ComponentType } from "react";
import { AiTab } from "./ai-tab";
import { DownloadsTab } from "./downloads-tab";
import { LibraryTab } from "./library-tab";
import { PricingTab } from "./pricing-tab";
import { ProvidersTab } from "./providers-tab";

export interface SettingsTab {
  id: string;
  label: string;
  adminOnly?: boolean;
  ownerOnly?: boolean;
  Component: ComponentType;
}

/** Admin tabs shown before Members and Diagnostics. Publishing (YouTube/Instagram) will be added here later. */
export const extraSettingsTabs: SettingsTab[] = [
  { id: "providers", label: "AI providers", adminOnly: true, Component: ProvidersTab },
  { id: "ai", label: "Budget", adminOnly: true, Component: AiTab },
  { id: "downloads", label: "Downloads & storage", adminOnly: true, Component: DownloadsTab },
  { id: "library", label: "Library", adminOnly: true, Component: LibraryTab },
  { id: "pricing", label: "AI model costs", adminOnly: true, Component: PricingTab },
];
