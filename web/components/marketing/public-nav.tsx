"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { SiteBanner } from "@/components/shell/site-banner";
import { supabaseBrowser } from "@/lib/supabase/client";
import { BrandMark } from "@/components/shell/brand-mark";

/** Top bar for public pages; shows "Open studio" when already signed in. */
export function PublicNav() {
  const [signedIn, setSignedIn] = useState(false);
  useEffect(() => {
    supabaseBrowser()
      .auth.getSession()
      .then(({ data }) => setSignedIn(!!data.session));
  }, []);
  return (
    <header className="sticky top-0 z-30 border-b bg-background/80 backdrop-blur">
      <SiteBanner />
      <div className="mx-auto flex max-w-6xl items-center gap-4 px-4 py-3">
        <Link href="/welcome">
          <BrandMark />
        </Link>
        <nav className="ml-auto flex items-center gap-1 text-sm sm:gap-3">
          <Link href="/pricing" className="rounded-lg px-2 py-1.5 text-muted-foreground hover:text-foreground">
            Pricing
          </Link>
          {signedIn ? (
            <Button asChild size="sm">
              <Link href="/">Open studio</Link>
            </Button>
          ) : (
            <>
              <Link href="/login" className="rounded-lg px-2 py-1.5 text-muted-foreground hover:text-foreground">
                Sign in
              </Link>
              <Button asChild size="sm">
                <Link href="/signup">Start free</Link>
              </Button>
            </>
          )}
        </nav>
      </div>
    </header>
  );
}

export function PublicFooter() {
  return (
    <footer className="mt-20 border-t">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-4 px-4 py-8 text-sm text-muted-foreground">
        <BrandMark size="sm" />
        <Link href="/pricing" className="hover:text-foreground">
          Pricing
        </Link>
        <Link href="/signup" className="hover:text-foreground">
          Create account
        </Link>
        <span className="ml-auto text-xs">Use only videos you have the rights to.</span>
      </div>
    </footer>
  );
}
