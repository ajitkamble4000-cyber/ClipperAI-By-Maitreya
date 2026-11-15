"use client";

import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { CAPTION_FONTS, CAPTION_PRESETS, PRESET_IDS, diffStyle, resolveStyle, type CaptionStyle, type PresetId } from "@/lib/presets";
import { cn } from "@/lib/utils";
import { CaptionPreview } from "./caption-preview";

export function CaptionStylePicker({
  value,
  onChange,
  hook,
  compact,
}: {
  value: CaptionStyle;
  onChange: (s: CaptionStyle) => void;
  hook?: string | null;
  compact?: boolean;
}) {
  const s = resolveStyle(value);
  const set = (patch: Partial<typeof s>) => onChange(diffStyle({ ...s, ...patch }));
  return (
    <div className={cn("grid gap-6", !compact && "md:grid-cols-[1fr_220px]")}>
      <div className="grid gap-5">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {[...PRESET_IDS, "none" as const].map((id) => (
            <button
              type="button"
              key={id}
              onClick={() => onChange({ preset: id })}
              className={cn(
                "rounded-lg border p-3 text-left transition",
                value.preset === id ? "border-primary bg-primary/10" : "hover:border-primary/50",
              )}
              data-testid={`preset-${id}`}
            >
              <p className="text-sm font-medium">{id === "none" ? "No captions" : CAPTION_PRESETS[id as PresetId].label}</p>
              <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">
                {id === "none" ? "Video only" : CAPTION_PRESETS[id as PresetId].description}
              </p>
            </button>
          ))}
        </div>
        {value.preset !== "none" && (
          <details className="rounded-lg border p-4" open={!compact}>
            <summary className="cursor-pointer text-sm font-medium">Customize</summary>
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              <Field label="Font">
                <Select value={s.font} onValueChange={(font) => set({ font })} options={Object.keys(CAPTION_FONTS).map((f) => ({ value: f, label: f }))} />
              </Field>
              <Field label="Position" hint="Always inside the Shorts safe zone">
                <Select
                  value={s.position}
                  onValueChange={(p) => set({ position: p as typeof s.position })}
                  options={[
                    { value: "top", label: "Top" },
                    { value: "middle", label: "Middle" },
                    { value: "lower", label: "Lower third" },
                  ]}
                />
              </Field>
              <Field label={`Size (${s.size})`}>
                <Slider min={40} max={140} step={2} value={[s.size]} onValueChange={([v]) => set({ size: v })} />
              </Field>
              <Field label={`Words per line (${s.words_per_line})`}>
                <Slider min={1} max={6} step={1} value={[s.words_per_line]} onValueChange={([v]) => set({ words_per_line: v })} />
              </Field>
              <Field label="Text color">
                <Input type="color" value={s.color} onChange={(e) => set({ color: e.target.value.toUpperCase() })} className="h-10 p-1" />
              </Field>
              <Field label="Highlight color">
                <Input type="color" value={s.highlight} onChange={(e) => set({ highlight: e.target.value.toUpperCase() })} className="h-10 p-1" />
              </Field>
              <Field label={`Outline (${s.outline})`}>
                <Slider min={0} max={14} step={1} value={[s.outline]} onValueChange={([v]) => set({ outline: v })} />
              </Field>
              <Field label={`Shadow (${s.shadow})`}>
                <Slider min={0} max={12} step={1} value={[s.shadow]} onValueChange={([v]) => set({ shadow: v })} />
              </Field>
              <label className="flex items-center justify-between gap-3 text-sm">
                ALL CAPS <Switch checked={s.uppercase} onCheckedChange={(uppercase) => set({ uppercase })} />
              </label>
              <label className="flex items-center justify-between gap-3 text-sm">
                Auto-emoji <Switch checked={s.emoji} onCheckedChange={(emoji) => set({ emoji })} />
              </label>
            </div>
          </details>
        )}
      </div>
      <div className={cn("mx-auto w-full max-w-[220px]", compact && "hidden sm:block")}>
        <CaptionPreview style={value} hook={hook} />
        <p className="mt-2 text-center text-xs text-muted-foreground">Live preview</p>
      </div>
    </div>
  );
}
