import { NewClipForm } from "@/components/clipper/new-clip-form";
import { PageHeader } from "@/components/shell/page-header";

export default function NewClipsPage() {
  return (
    <>
      <PageHeader title="New clips" description="Turn a long video into ready-to-post vertical Shorts." />
      <NewClipForm />
    </>
  );
}
