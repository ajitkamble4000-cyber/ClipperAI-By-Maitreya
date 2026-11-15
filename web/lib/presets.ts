import catalog from "./presets/captions.json";

export type PresetId = "bold_pop" | "karaoke" | "minimal" | "boxed" | "horror";
export type Position = "top" | "middle" | "lower";

export interface CaptionStyle {
  preset: PresetId | "none";
  font?: string;
  size?: number;
  color?: string;
  highlight?: string;
  outline_color?: string;
  outline?: number;
  shadow?: number;
  uppercase?: boolean;
  words_per_line?: number;
  position?: Position;
  emoji?: boolean;
}

export type ResolvedStyle = Required<Omit<CaptionStyle, "preset">> & {
  preset: PresetId | "none";
  label: string;
  box_color?: string;
  box_opacity?: number;
};

export const CAPTION_FONTS = catalog.fonts as Record<string, { file: string; css: string; weight: number }>;
export const CAPTION_PRESETS = catalog.presets as unknown as Record<PresetId, ResolvedStyle & { description: string }>;
export const POSITIONS = catalog.positions as Record<Position, number>;
export const PRESET_IDS = Object.keys(CAPTION_PRESETS) as PresetId[];

export function resolveStyle(s: CaptionStyle | null | undefined): ResolvedStyle {
  const preset = (s?.preset && s.preset !== "none" ? s.preset : "bold_pop") as PresetId;
  const base = CAPTION_PRESETS[preset];
  const overrides = Object.fromEntries(Object.entries(s ?? {}).filter(([, v]) => v !== undefined && v !== null));
  return { ...base, ...overrides, preset: s?.preset ?? preset } as ResolvedStyle;
}

/** Only the fields that differ from the preset (keeps saved styles small and preset updates flowing through). */
export function diffStyle(s: ResolvedStyle): CaptionStyle {
  if (s.preset === "none") return { preset: "none" };
  const base = CAPTION_PRESETS[s.preset as PresetId] as unknown as Record<string, unknown>;
  const out: Record<string, unknown> = { preset: s.preset };
  for (const k of ["font", "size", "color", "highlight", "outline_color", "outline", "shadow", "uppercase", "words_per_line", "position", "emoji"]) {
    const v = (s as unknown as Record<string, unknown>)[k];
    if (v !== undefined && v !== base[k]) out[k] = v;
  }
  return out as unknown as CaptionStyle;
}

export function slugify(text: string, max = 50): string {
  const s = text
    .normalize("NFKD")
    .replace(/[^\x00-\x7F]/g, "")
    .replace(/[^a-zA-Z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .toLowerCase()
    .slice(0, max)
    .replace(/-+$/, "");
  return s || "clip";
}

export function clipFilename(idx: number, title: string): string {
  return `${String(idx).padStart(2, "0")}_${slugify(title)}.mp4`;
}
