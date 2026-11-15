import { StoryEditor } from "@/components/story/story-editor";

export default async function StoryProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <StoryEditor projectId={id} />;
}
