import type { Metadata } from "next";
import { Suspense } from "react";
import { BRAND } from "@/lib/brand";
import { PLACEHOLDER } from "@/lib/routes";
import { SharedVideo } from "./client";

export const metadata: Metadata = { title: `Shared video · ${BRAND}`, robots: { index: false, follow: false } };

/** On static hosting this page is built once (placeholder token) and reads the real token from ?id=. */
export function generateStaticParams() {
  return [{ token: PLACEHOLDER }];
}

export default async function SharedPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  return (
    <Suspense>
      <SharedVideo token={token} />
    </Suspense>
  );
}
