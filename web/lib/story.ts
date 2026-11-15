import catalog from "./presets/story.json";

export type GenreId = keyof typeof catalog.genres;
export const GENRES = catalog.genres as Record<
  string,
  { label: string; example: string; visual_style: string; music: string; captions: string; speaking_style: string; voice: string }
>;
export const SPEAKING_STYLES = catalog.speaking_styles as Record<string, { label: string }>;
export const VOICES = catalog.voices as { name: string; desc: string }[];
export const LANGUAGES = catalog.languages as Record<string, { label: string }>;
export const LENGTHS = catalog.lengths as number[];
export const CAMERA_MOTIONS = catalog.camera_motions as string[];
export const MUSIC_MOODS = catalog.music_moods as string[];
export const WORDS_PER_SECOND = catalog.words_per_second as number;

export function estimateSeconds(text: string): number {
  const words = text.trim() ? text.trim().split(/\s+/).length : 0;
  return words / WORDS_PER_SECOND;
}
