import { ClipProjectView } from "@/components/clipper/clip-project-view";

export default async function ClipProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ClipProjectView projectId={id} />;
}
