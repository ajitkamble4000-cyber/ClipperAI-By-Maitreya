import { Suspense } from "react";
import { PageHeader } from "@/components/shell/page-header";
import { NewClipFromQuery } from "./client";

export default function NewClipsPage() {
  return (
    <>
      <PageHeader title="Make Shorts" description="Paste any link or upload a video: get captioned clips, or the whole video captioned." />
      <Suspense>
        <NewClipFromQuery />
      </Suspense>
    </>
  );
}
