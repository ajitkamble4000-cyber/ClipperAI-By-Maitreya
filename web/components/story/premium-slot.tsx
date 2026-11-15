"use client";

import type { ComponentType } from "react";
import type { StepProps } from "./steps-registry";

/** Premium (Veo) panel, provided by the premium feature module. */
export const premiumPanel: { Component: ComponentType<StepProps> | null } = { Component: null };
