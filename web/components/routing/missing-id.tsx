import Link from "next/link";

/** Shown when a page that needs an id (?id=…) was opened without one. */
export function MissingId({ back = "/" }: { back?: string }) {
  return (
    <div className="mx-auto mt-16 max-w-sm text-center">
      <h1 className="text-lg font-semibold">This page needs a link</h1>
      <p className="mt-1 text-sm text-muted-foreground">Open it from your Library or a notification.</p>
      <Link href={back} className="mt-4 inline-block text-sm text-primary hover:underline">
        Go back
      </Link>
    </div>
  );
}
