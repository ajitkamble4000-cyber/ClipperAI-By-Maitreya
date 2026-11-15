"use client";

import { useEffect, useMemo, useState } from "react";
import { CAPTION_FONTS, POSITIONS, resolveStyle, type CaptionStyle } from "@/lib/presets";
import { cn } from "@/lib/utils";

const SAMPLE = "this is how your captions will look on every short".split(" ");

function hexA(hex: string, a: number) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}

/** Live CSS approximation of the burned-in captions (same fonts, colors, sizes, safe-zone positions). */
export function CaptionPreview({
  style,
  hook,
  className,
  words = SAMPLE,
}: {
  style: CaptionStyle;
  hook?: string | null;
  className?: string;
  words?: string[];
}) {
  const s = resolveStyle(style);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 380);
    return () => clearInterval(id);
  }, []);
  const per = Math.max(1, s.words_per_line);
  const chunkCount = Math.ceil(words.length / per);
  const chunk = Math.floor(tick / per) % chunkCount;
  const active = tick % per;
  const shown = useMemo(() => words.slice(chunk * per, chunk * per + per), [words, chunk, per]);
  const font = CAPTION_FONTS[s.font] ?? CAPTION_FONTS["Montserrat Black"];
  const scale = 0.25; // preview is ~270px wide vs 1080px video
  const fontSize = s.size * scale;
  const outline = s.outline * scale;
  const shadow = s.shadow * scale;
  const textShadow = [
    outline > 0 &&
      Array.from({ length: 8 }, (_, i) => {
        const a = (i / 8) * Math.PI * 2;
        return `${(Math.cos(a) * outline).toFixed(1)}px ${(Math.sin(a) * outline).toFixed(1)}px 0 ${s.outline_color}`;
      }).join(","),
    shadow > 0 && `${shadow}px ${shadow}px ${shadow * 1.5}px rgba(0,0,0,0.55)`,
  ]
    .filter(Boolean)
    .join(",");

  return (
    <div
      className={cn(
        "relative aspect-[9/16] w-full overflow-hidden rounded-xl border bg-gradient-to-b from-slate-700 via-slate-800 to-slate-900",
        className,
      )}
      data-testid="caption-preview"
    >
      <div className="absolute inset-x-0 bottom-0 h-[24%] bg-gradient-to-t from-black/50 to-transparent" />
      <div className="absolute bottom-[3%] left-[4%] right-[16%] space-y-1 opacity-50">
        <div className="h-1.5 w-2/3 rounded bg-white/70" />
        <div className="h-1.5 w-1/2 rounded bg-white/40" />
      </div>
      <div className="absolute bottom-[6%] right-[3%] flex flex-col gap-2 opacity-40">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="size-5 rounded-full bg-white/70" />
        ))}
      </div>
      {hook && (
        <div className="absolute left-[6.5%] right-[12%] top-[17%] flex justify-center">
          <span className="rounded-md bg-[#FFE500] px-2 py-1 text-center text-[11px] font-black uppercase leading-tight text-black" style={{ fontFamily: "Montserrat" }}>
            {hook}
          </span>
        </div>
      )}
      {s.preset !== "none" && (
        <div
          className="absolute flex w-[81%] justify-center text-center"
          style={{ left: "6.5%", top: `${POSITIONS[s.position] * 100}%`, transform: "translateY(-50%)" }}
        >
          <span
            className={cn("inline-block leading-[1.15]", s.preset === "horror" && "animate-[shake_0.18s_infinite]")}
            style={{
              fontFamily: font.css,
              fontWeight: font.weight,
              fontSize,
              color: s.color,
              textShadow: s.preset === "boxed" ? undefined : textShadow,
              textTransform: s.uppercase ? "uppercase" : "none",
              background: s.preset === "boxed" ? hexA(s.box_color ?? "#000000", s.box_opacity ?? 0.72) : undefined,
              padding: s.preset === "boxed" ? "4px 10px" : undefined,
              borderRadius: s.preset === "boxed" ? 6 : undefined,
            }}
          >
            {shown.map((w, i) => {
              const on = i === active;
              const karaokeDone = s.preset === "karaoke" && i < active;
              return (
                <span key={`${chunk}-${i}`}>
                  <span
                    className="inline-block transition-transform duration-100"
                    style={{
                      color: on || karaokeDone ? s.highlight : undefined,
                      transform: on && s.preset === "bold_pop" ? "scale(1.14)" : undefined,
                    }}
                  >
                    {w}
                  </span>
                  {i < shown.length - 1 ? " " : ""}
                </span>
              );
            })}
          </span>
        </div>
      )}
    </div>
  );
}
