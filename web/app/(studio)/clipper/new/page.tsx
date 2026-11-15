import { NewClipForm } from "@/components/clipper/new-clip-form";
import { PageHeader } from "@/components/shell/page-header";

type Mode = "auto" | "clips" | "captions";

export default async function NewClipsPage({ searchParams }: { searchParams: Promise<{ url?: string; mode?: string }> }) {
  const sp = await searchParams;
  const mode: Mode = sp.mode === "clips" || sp.mode === "captions" ? sp.mode : "auto";
  return (
    <>
      <PageHeader title="Make Shorts" description="Paste any link or upload a video: get captioned clips, or the whole video captioned." />
      <NewClipForm initialUrl={sp.url ?? ""} initialMode={mode} />
    </>
  );
}
