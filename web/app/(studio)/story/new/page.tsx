import { PageHeader } from "@/components/shell/page-header";
import { NewStoryForm } from "@/components/story/new-story-form";

export default function NewStoryPage() {
  return (
    <>
      <PageHeader title="New story" description="AI script → storyboard → images → voice → finished Short." />
      <NewStoryForm />
    </>
  );
}
