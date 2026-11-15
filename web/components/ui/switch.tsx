"use client";
import * as React from "react";
import * as S from "@radix-ui/react-switch";
import { cn } from "@/lib/utils";

export function Switch({ className, ...p }: React.ComponentPropsWithoutRef<typeof S.Root>) {
  return (
    <S.Root
      className={cn(
        "inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent bg-input transition data-[state=checked]:bg-primary disabled:opacity-50",
        className,
      )}
      {...p}
    >
      <S.Thumb className="block size-5 rounded-full bg-white shadow transition data-[state=checked]:translate-x-5" />
    </S.Root>
  );
}
