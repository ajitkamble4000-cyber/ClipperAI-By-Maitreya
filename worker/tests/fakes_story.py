"""Fake Gemini answers for Story Studio tests."""

from __future__ import annotations

from worker.story.schema import CharacterOut, HookRewrite, SceneOut, SceneRewrite, StoryScript


class FakeStoryGemini:
    def __init__(self) -> None:
        self.prompts: list = []

    def generate_json(self, contents, schema, **kw):
        self.prompts.append(contents)
        from worker.clipper.moments.schema import ClipIdeas

        if schema is ClipIdeas:  # so one fake can serve both tools in browser tests
            from fakes import FakeGemini

            return FakeGemini().generate_json(contents, schema)
        from worker.captions.translate import CueTranslations
        from worker.clipper.whole import WholeMeta
        from worker.extras import TitleIdeas

        if schema is TitleIdeas:
            return TitleIdeas(
                titles=[
                    "I tried this for 30 days",
                    "Nobody talks about this",
                    "Is this the best trick?",
                    "5 things I wish I knew",
                    "This changed everything",
                ],
                hashtags=["#shorts", "viral", "#tips", "#howto", "#lifehack", "#fyp", "#learn", "#daily"],
                description="A quick video worth watching.",
            )
        if schema is WholeMeta:
            return WholeMeta(
                title="A quick captioned video",
                hook_text="WATCH THIS",
                description="Captioned automatically.",
                hashtags=["#shorts", "captions"],
            )
        if schema is CueTranslations:  # "translate" by tagging each line, keeping the count
            body = str(contents).split("\n\n", 1)[-1]
            lines = [ln.split(". ", 1)[-1] for ln in body.splitlines() if ln.strip()]
            return CueTranslations(lines=[f"[es] {ln}" for ln in lines])
        if schema is StoryScript:
            lines = [
                "You fall toward a black hole.",
                "Time slows down around you.",
                "Your feet stretch first.",
                "Light bends into a ring.",
                "The universe ages in seconds.",
                "Then everything goes dark.",
            ]
            return StoryScript(
                title="What if you fell into a black hole?",
                hook_text="YOU FALL IN",
                description="A trip you can't undo.",
                hashtags=["space", "#blackhole", "#science", "#whatif", "#shorts"],
                characters=[
                    CharacterOut(name="Astronaut", description="woman, 30s, white spacesuit, gold visor")
                ],
                scenes=[
                    SceneOut(
                        narration=t,
                        image_prompt=f"cinematic shot {i}",
                        camera_motion="zoom-in",
                        duration_estimate=3.0,
                        sfx_suggestion="whoosh",
                        characters=["Astronaut"],
                    )
                    for i, t in enumerate(lines)
                ],
            )
        if schema is SceneRewrite:
            return SceneRewrite(
                narration="A rewritten, more gripping line.",
                image_prompt="new prompt",
                camera_motion="shake",
                sfx_suggestion="boom",
            )
        if schema is HookRewrite:
            return HookRewrite(
                title="Better title",
                hook_text="DON'T LOOK DOWN",
                first_scene_narration="Stronger hook.",
                first_scene_image_prompt="striking frame",
            )
        raise NotImplementedError(schema)


class FakeMediaGemini(FakeStoryGemini):
    """Adds images (Pillow) and TTS (espeak-ng, 24 kHz PCM) so the whole render pipeline runs offline."""

    def __init__(self) -> None:
        super().__init__()
        self.image_calls: list[tuple[str, int]] = []
        self.tts_calls = 0

    def generate_image(self, prompt, *, refs=None, aspect="9:16", model=None):
        import io
        import zlib

        from PIL import Image, ImageDraw

        self.image_calls.append((prompt, len(refs or [])))
        seed = zlib.crc32(prompt.encode())
        im = Image.new("RGB", (576, 1024), ((seed >> 16) & 255, (seed >> 8) & 255, seed & 255))
        d = ImageDraw.Draw(im)
        for i in range(0, 1024, 64):  # texture so motion is visible
            d.line([(0, i), (576, i + 300)], fill=(255 - (seed & 255), 200, (seed >> 8) & 255), width=6)
        d.ellipse((188, 380, 388, 580), fill=(255, 255, 255))
        out = io.BytesIO()
        im.save(out, "PNG")
        return out.getvalue()

    def edit_image(self, image, mime, instruction, aspect="9:16"):
        return self.generate_image("edited " + instruction)

    def tts(self, text, *, voice, style=None, model=None):
        import subprocess
        import tempfile

        self.tts_calls += 1
        with tempfile.NamedTemporaryFile(suffix=".wav") as f:
            subprocess.run(
                ["espeak-ng", "-v", "en-us", "-s", "155", "-w", f.name, text.replace("\n\n", ". ")],
                check=True,
            )
            pcm = subprocess.run(
                [
                    "ffmpeg",
                    "-loglevel",
                    "error",
                    "-i",
                    f.name,
                    "-f",
                    "s16le",
                    "-ar",
                    "24000",
                    "-ac",
                    "1",
                    "-",
                ],
                check=True,
                capture_output=True,
            ).stdout
        return pcm


class _Op:
    def __init__(self, name, polls_left, fail=False):
        self.name, self.polls_left, self.fail = name, polls_left, fail
        self.done, self.error, self.response = False, None, None


class FakeVeoGemini(FakeMediaGemini):
    """Veo: operations finish after a couple of polls; prompts containing FAILME fail."""

    def __init__(self) -> None:
        super().__init__()
        self.ops: dict[str, _Op] = {}
        self.started = 0

    def start_video(self, *, prompt, image, mime, seconds, model=None, aspect="9:16"):
        self.started += 1
        op = _Op(f"operations/fake-{self.started}", 2, fail="FAILME" in prompt)
        op.seconds = seconds
        self.ops[op.name] = op
        return op

    def operation_from_name(self, name):
        return self.ops[name]

    def get_operation(self, op):
        op = self.ops[op.name]
        op.polls_left -= 1
        if op.polls_left <= 0:
            op.done = True
            if op.fail:
                op.error = {"message": "content filtered"}
        return op

    def download_video(self, op, *, model, seconds):
        import subprocess
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".mp4") as f:
            subprocess.run(
                [
                    "ffmpeg",
                    "-loglevel",
                    "error",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    f"testsrc2=s=720x1280:r=24:d={seconds}",
                    "-pix_fmt",
                    "yuv420p",
                    f.name,
                ],
                check=True,
            )
            return open(f.name, "rb").read()
