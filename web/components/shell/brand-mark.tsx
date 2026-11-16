import { Clapperboard } from "lucide-react";
import { BRAND_BY, BRAND_SHORT } from "@/lib/brand";
import { cn } from "@/lib/utils";

/** Logo + name: "ClipperAI" with a quieter "by Maitreya". */
export function BrandMark({ size = "md", stacked, className }: { size?: "sm" | "md" | "lg"; stacked?: boolean; className?: string }) {
  const icon = size === "lg" ? "size-7" : size === "sm" ? "size-4" : "size-6";
  return (
    <span className={cn("flex items-center gap-2 font-semibold", className)} data-testid="brand">
      <Clapperboard className={cn(icon, "shrink-0 text-primary")} aria-hidden />
      <span className={cn("flex whitespace-nowrap", stacked ? "flex-col leading-tight" : "items-baseline gap-1.5")}>
        <span>{BRAND_SHORT}</span>
        <span className={cn("font-normal text-muted-foreground", stacked ? "text-[11px]" : "text-xs")}>{BRAND_BY}</span>
      </span>
    </span>
  );
}
