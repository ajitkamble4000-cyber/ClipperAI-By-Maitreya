"use client";
import * as React from "react";
import * as S from "@radix-ui/react-slider";
import { cn } from "@/lib/utils";

export function Slider({ className, ...p }: React.ComponentPropsWithoutRef<typeof S.Root>) {
  return (
    <S.Root className={cn("relative flex h-5 w-full touch-none select-none items-center", className)} {...p}>
      <S.Track className="relative h-1.5 w-full grow overflow-hidden rounded-full bg-muted">
        <S.Range className="absolute h-full bg-primary" />
      </S.Track>
      {(p.value ?? p.defaultValue ?? [0]).map((_, i) => (
        <S.Thumb
          key={i}
          className="block size-5 rounded-full border-2 border-primary bg-background shadow focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
      ))}
    </S.Root>
  );
}
