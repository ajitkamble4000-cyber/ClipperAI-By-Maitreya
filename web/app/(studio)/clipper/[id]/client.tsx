"use client";

import { MissingId } from "@/components/routing/missing-id";
import { useRouteId } from "@/lib/use-route-id";
import { ClipProjectView } from "@/components/clipper/clip-project-view";

export function ClipRoute({ id }: { id: string }) {
  const real = useRouteId(id);
  if (!real) return <MissingId back="/clipper" />;
  return <ClipProjectView key={real} projectId={real} />;
}
