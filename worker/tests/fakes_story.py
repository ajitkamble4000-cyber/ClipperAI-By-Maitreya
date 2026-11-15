"""Fake Gemini answers for Story Studio tests."""

from __future__ import annotations

from worker.story.schema import CharacterOut, HookRewrite, SceneOut, SceneRewrite, StoryScript


class FakeStoryGemini:
    def __init__(self) -> None:
        self.prompts: list = []

    def generate_json(self, contents, schema, **kw):
        self.prompts.append(contents)
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
