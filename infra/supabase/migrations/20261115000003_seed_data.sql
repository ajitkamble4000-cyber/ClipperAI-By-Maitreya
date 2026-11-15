-- Default data: price estimates (edit in Settings → Pricing) and built-in visual styles.
-- Prices are USD and are matched by longest model-name prefix. They are estimates
-- taken from Google's public price list at build time; check them against
-- https://ai.google.dev/gemini-api/docs/pricing and adjust.

insert into public.model_pricing (model, input_per_mtok, output_per_mtok, audio_out_per_mtok, per_image, per_video_second) values
  ('gemini-2.5-pro',              1.25, 10.00,  0,     0,     0),
  ('gemini-2.5-flash-lite',       0.10,  0.40,  0,     0,     0),
  ('gemini-2.5-flash',            0.30,  2.50,  0,     0,     0),
  ('gemini-2.5-flash-image',      0.30,  0,     0,     0.039, 0),
  ('gemini-2.5-flash-preview-tts',0.50,  0,    10.00,  0,     0),
  ('gemini-2.5-pro-preview-tts',  1.00,  0,    20.00,  0,     0),
  ('gemini-3-pro',                2.00, 12.00,  0,     0,     0),
  ('gemini-3-pro-image',          2.00,  0,     0,     0.134, 0),
  ('gemini-3-flash',              0.50,  3.00,  0,     0,     0),
  ('imagen-4',                    0,     0,     0,     0.04,  0),
  ('veo-2',                       0,     0,     0,     0,     0.35),
  ('veo-3.0-fast',                0,     0,     0,     0,     0.15),
  ('veo-3.0',                     0,     0,     0,     0,     0.40),
  ('veo-3.1-fast',                0,     0,     0,     0,     0.15),
  ('veo-3.1',                     0,     0,     0,     0,     0.40)
on conflict (model) do nothing;

insert into public.visual_styles (id, name, prompt, builtin) values
  ('realistic_3d', 'Realistic 3D render',
   'Hyper-realistic 3D render, cinematic lighting, volumetric light, dramatic rim light, shallow depth of field, Unreal Engine 5 quality, highly detailed textures, photoreal materials, epic scale, vertical 9:16 composition with the subject centered', true),
  ('pixar_3d', 'Pixar-style 3D',
   'Stylized 3D animation in the style of a modern animated feature film, soft global illumination, appealing rounded character design, expressive faces, vibrant saturated colors, subsurface scattering, vertical 9:16 composition', true),
  ('dark_horror', 'Dark horror illustration',
   'Dark horror digital illustration, desaturated palette with deep shadows, sickly green and blood red accents, heavy film grain, fog, unsettling atmosphere, chiaroscuro lighting, vertical 9:16 composition', true),
  ('anime', 'Anime',
   'High quality anime key visual, clean line art, cel shading, vivid colors, dramatic sky, detailed background art, cinematic anime lighting, vertical 9:16 composition', true),
  ('comic', 'Comic',
   'Bold comic book art, thick ink outlines, halftone dot shading, dynamic angles, high-contrast flat colors, graphic novel panel style, vertical 9:16 composition', true)
on conflict (id) do nothing;
