from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

CameraMotion = Literal["zoom-in", "zoom-out", "pan-left", "pan-right", "shake", "static"]


class SceneOut(BaseModel):
    narration: str = Field(description="What the narrator says in this scene (spoken words only)")
    image_prompt: str = Field(
        description="Detailed visual description of ONE vertical 9:16 image for this scene. "
        "Describe subject, setting, action, lighting and camera angle. No text in the image."
    )
    camera_motion: CameraMotion = Field(description="Motion applied to the still image")
    duration_estimate: float = Field(description="Seconds this narration takes to say")
    sfx_suggestion: str = Field(
        description="One short sound effect idea (e.g. whoosh, heartbeat, thunder) or empty"
    )
    on_screen_text: str = Field(default="", description="Optional 1-4 word overlay text, usually empty")
    characters: list[str] = Field(
        default_factory=list, description="Names of recurring characters visible in this scene"
    )


class CharacterOut(BaseModel):
    name: str
    description: str = Field(
        description="Consistent visual description: age, build, face, hair, clothing, colors"
    )


class StoryScript(BaseModel):
    title: str = Field(description="YouTube Shorts title under 60 characters")
    hook_text: str = Field(description="3-6 word on-screen hook for the first 3 seconds")
    description: str = Field(description="1-2 sentence YouTube description")
    hashtags: list[str] = Field(description="5-8 hashtags starting with #")
    characters: list[CharacterOut] = Field(
        default_factory=list,
        description="Recurring characters (people/creatures appearing in 2+ scenes); empty if none",
    )
    scenes: list[SceneOut]


class SceneRewrite(BaseModel):
    narration: str
    image_prompt: str
    camera_motion: CameraMotion
    sfx_suggestion: str = ""
    on_screen_text: str = ""


class HookRewrite(BaseModel):
    title: str
    hook_text: str
    first_scene_narration: str
    first_scene_image_prompt: str
