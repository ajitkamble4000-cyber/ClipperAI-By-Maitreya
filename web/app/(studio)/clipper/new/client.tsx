"use client";

import { useSearchParams } from "next/navigation";
import { NewClipForm } from "@/components/clipper/new-clip-form";

type Mode = "auto" | "clips" | "captions";

/** Reads ?url= and ?mode= (from the Home quick paste) in the browser, so the page can be static. */
export function NewClipFromQuery() {
  const sp = useSearchParams();
  const m = sp.get("mode");
  const mode: Mode = m === "clips" || m === "captions" ? m : "auto";
  return <NewClipForm initialUrl={sp.get("url") ?? ""} initialMode={mode} />;
}
