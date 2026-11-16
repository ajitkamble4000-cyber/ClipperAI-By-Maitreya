import { SiteBanner } from "@/components/shell/site-banner";
import { BrandMark } from "@/components/shell/brand-mark";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col">
      <SiteBanner />
      <div className="flex flex-1 flex-col items-center justify-center px-4 py-10">
        <div className="mb-8 flex items-center gap-2 text-xl font-semibold">
          <BrandMark size="lg" />
        </div>
        <div className="w-full max-w-sm">{children}</div>
      </div>
    </div>
  );
}
