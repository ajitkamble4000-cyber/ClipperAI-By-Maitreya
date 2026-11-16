"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { BrandMark } from "@/components/shell/brand-mark";
import { STATIC, staticFallback } from "@/lib/routes";

/**
 * 404. On static hosting, GitHub Pages serves this for any path that has no file, including links with an id in
 * the path (/clipper/<id>, /s/<token>…): those are forwarded to the page that reads the id from ?id=.
 */
export default function NotFound() {
  const [forwarding, setForwarding] = useState(STATIC);
  useEffect(() => {
    if (!STATIC) return;
    const to = staticFallback(window.location.pathname, window.location.search, window.location.hash);
    if (to) window.location.replace(to);
    else setForwarding(false);
  }, []);
  if (forwarding) return null;
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-4 px-4 text-center">
      <BrandMark size="lg" />
      <h1 className="text-xl font-semibold">Page not found</h1>
      <p className="text-sm text-muted-foreground">The link may be wrong, or the page was moved.</p>
      <Link href="/" className="text-sm text-primary hover:underline">
        Go to the home page
      </Link>
    </div>
  );
}
