import { PlugZap } from "lucide-react";
import { env } from "@/lib/env";

/** On a static build without server addresses: explains why signing in isn't possible yet. */
export function NotConnected() {
  if (env.configured) return null;
  return (
    <div className="flex items-center justify-center gap-2 border-b border-warning/40 bg-warning/10 px-4 py-2 text-center text-sm" data-testid="not-connected" role="status">
      <PlugZap className="size-4 shrink-0 text-warning" aria-hidden />
      <span>Opening soon: sign-up and sign-in will be available here shortly.</span>
    </div>
  );
}
