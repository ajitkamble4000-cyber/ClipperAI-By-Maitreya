/** Plan features shown in the UI (mirrors api/app/plans.py FEATURE_LABELS) and the cheapest plan that has them. */
export const FEATURES: Record<string, { label: string; plan: "Pro" | "Business" }> = {
  visual_analysis: { label: "Visual analysis", plan: "Pro" },
  brand_kit: { label: "Brand kit", plan: "Pro" },
  translation: { label: "Caption translation", plan: "Pro" },
  filler_removal: { label: "Filler & silence removal", plan: "Pro" },
  keyword_emphasis: { label: "Keyword emphasis", plan: "Pro" },
  templates: { label: "Templates", plan: "Pro" },
  premium_voices: { label: "Premium voices", plan: "Pro" },
  thumbnails: { label: "AI thumbnails", plan: "Pro" },
  title_variants: { label: "Title ideas", plan: "Pro" },
  share_links: { label: "Share links", plan: "Pro" },
  output_formats: { label: "Square / 4:5 / 16:9 output", plan: "Pro" },
  no_watermark: { label: "No watermark", plan: "Pro" },
  premium_video: { label: "Premium AI video", plan: "Business" },
  batch: { label: "Batch mode", plan: "Business" },
  priority: { label: "Priority processing", plan: "Business" },
};
