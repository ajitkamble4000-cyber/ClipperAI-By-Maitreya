"use client";

import { MissingId } from "@/components/routing/missing-id";
import { useRouteId } from "@/lib/use-route-id";
import { StoryEditor } from "@/components/story/story-editor";

export function StoryRoute({ id }: { id: string }) {
  const real = useRouteId(id);
  if (!real) return <MissingId back="/story" />;
  return <StoryEditor key={real} projectId={real} />;
}
