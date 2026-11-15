"use client";

import type { ComponentType } from "react";

export interface SettingsTab {
  id: string;
  label: string;
  adminOnly?: boolean;
  Component: ComponentType;
}

/** Tabs added by later features (AI, YouTube, styles, music, pricing). */
export const extraSettingsTabs: SettingsTab[] = [];
