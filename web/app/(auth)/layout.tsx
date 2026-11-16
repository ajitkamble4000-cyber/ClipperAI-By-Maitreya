import { Clapperboard } from "lucide-react";
import { SiteBanner } from "@/components/shell/site-banner";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col">
      <SiteBanner />
      <div className="flex flex-1 flex-col items-center justify-center px-4 py-10">
        <div className="mb-8 flex items-center gap-2 text-xl font-semibold">
          <Clapperboard className="size-7 text-primary" /> Shorts Studio
        </div>
        <div className="w-full max-w-sm">{children}</div>
      </div>
    </div>
  );
}
