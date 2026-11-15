"use client";

import type { ComponentType } from "react";
import type { Job } from "@/hooks/use-job";
import type { Scene } from "./scene-card";
import type { Story } from "./story-meta";

export interface StepProps {
  story: Story;
  scenes: Scene[];
  setScenes: (fn: (s: Scene[] | null) => Scene[] | null) => void;
  jobs: Job[];
}

/** Later steps (characters, images, voice, render) register here. */
export const storyStepTabs: { id: string; label: string; Component: ComponentType<StepProps> }[] = [];
