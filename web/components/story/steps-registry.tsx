"use client";

import type { ComponentType } from "react";
import type { Job } from "@/hooks/use-job";
import { CharactersStep } from "./characters-step";
import { ImagesStep } from "./images-step";
import { RenderStep } from "./render-step";
import type { Scene } from "./scene-card";
import type { Story } from "./story-meta";
import { VoiceStep } from "./voice-step";

export interface StepProps {
  story: Story;
  scenes: Scene[];
  setScenes: (fn: (s: Scene[] | null) => Scene[] | null) => void;
  jobs: Job[];
}

export const storyStepTabs: { id: string; label: string; Component: ComponentType<StepProps> }[] = [
  { id: "characters", label: "2. Characters", Component: CharactersStep },
  { id: "images", label: "3. Images", Component: ImagesStep },
  { id: "voice", label: "4. Voice", Component: VoiceStep },
  { id: "render", label: "5. Render", Component: RenderStep },
];
