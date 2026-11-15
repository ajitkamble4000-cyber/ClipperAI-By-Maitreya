import { PublicFooter, PublicNav } from "@/components/marketing/public-nav";

export default function PublicLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-dvh">
      <PublicNav />
      <main>{children}</main>
      <PublicFooter />
    </div>
  );
}
