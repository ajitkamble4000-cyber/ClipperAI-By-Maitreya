import { Suspense } from "react";
import { PLACEHOLDER } from "@/lib/routes";
import { AdminUserRoute } from "./client";

/**
 * On static hosting this page is built once (placeholder id) and reads the real id from ?id=. On the server build
 * the placeholder render reads cookies (studio layout), so Next keeps the route dynamic.
 */
export function generateStaticParams() {
  return [{ id: PLACEHOLDER }];
}

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <Suspense>
      <AdminUserRoute id={id} />
    </Suspense>
  );
}
