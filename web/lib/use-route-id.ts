"use client";

import { useSearchParams } from "next/navigation";
import { PLACEHOLDER } from "./routes";

/** The real id for a page built with a placeholder id. Call inside a <Suspense> boundary. */
export function useRouteId(fromParams: string | undefined): string | null {
  const search = useSearchParams();
  if (fromParams && fromParams !== PLACEHOLDER) return decodeURIComponent(fromParams);
  return search.get("id");
}
