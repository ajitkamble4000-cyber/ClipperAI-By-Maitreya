"use client";

import { useEffect, useState } from "react";
import { signedUrl } from "@/lib/api";
import { cn } from "@/lib/utils";

const GRADIENTS: Record<string, string> = {
  realistic_3d: "from-sky-900 via-indigo-900 to-black",
  pixar_3d: "from-amber-300 via-pink-400 to-sky-400",
  dark_horror: "from-zinc-900 via-red-950 to-black",
  anime: "from-fuchsia-500 via-sky-400 to-indigo-600",
  comic: "from-yellow-300 via-red-500 to-blue-600",
};

export function StyleThumb({ style, active }: { style: { id: string; name: string; example_key: string | null }; active?: boolean }) {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (style.example_key) signedUrl(style.example_key).then(setUrl).catch(() => {});
  }, [style.example_key]);
  return (
    <div
      className={cn(
        "relative aspect-[9/16] overflow-hidden rounded-lg border-2 bg-gradient-to-br",
        GRADIENTS[style.id] ?? "from-slate-700 to-slate-900",
        active ? "border-primary" : "border-transparent",
      )}
    >
      {url && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={url} alt={style.name} className="size-full object-cover" />
      )}
    </div>
  );
}
