"""Names shared by the API (producer) and workers (consumers)."""

QUEUE_MEDIA = "media"  # CPU heavy: ffmpeg, whisper, reframe
QUEUE_AI = "ai"  # I/O bound: Gemini text / image / TTS
QUEUE_POLL = "poll"  # Veo long-running operations

# job kind -> (celery task name, queue)
JOB_ROUTES: dict[str, tuple[str, str]] = {
    "dummy": ("worker.run_job", QUEUE_MEDIA),
    "clip": ("worker.run_job", QUEUE_MEDIA),
    "clip_rerender": ("worker.run_job", QUEUE_MEDIA),
    "clip_zip": ("worker.run_job", QUEUE_MEDIA),
    "story_script": ("worker.run_job", QUEUE_AI),
    "story_scene_ai": ("worker.run_job", QUEUE_AI),
    "story_characters": ("worker.run_job", QUEUE_AI),
    "story_images": ("worker.run_job", QUEUE_AI),
    "story_image_one": ("worker.run_job", QUEUE_AI),
    "story_voice": ("worker.run_job", QUEUE_MEDIA),
    "story_veo": ("worker.run_job", QUEUE_POLL),
    "story_render": ("worker.run_job", QUEUE_MEDIA),
}
