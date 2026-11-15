"use client";

import type { ComponentType } from "react";
import { PremiumPanel } from "./premium-panel";
import type { StepProps } from "./steps-registry";

/** Premium (Veo) panel shown in the Render step when motion mode is Premium. */
export const premiumPanel: { Component: ComponentType<StepProps> | null } = { Component: PremiumPanel };
