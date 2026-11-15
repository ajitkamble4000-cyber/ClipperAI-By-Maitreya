from __future__ import annotations

from pydantic import BaseModel, Field


class ClipIdea(BaseModel):
    start: float = Field(description="Clip start in seconds from the beginning of the video")
    end: float = Field(description="Clip end in seconds")
    title: str = Field(description="Catchy YouTube Shorts title, under 60 characters")
    hook_text: str = Field(description="3-6 word on-screen hook for the first 3 seconds")
    description: str = Field(description="1-2 sentence YouTube description")
    hashtags: list[str] = Field(description="5-8 hashtags, each starting with #")
    virality_score: int = Field(description="1-100 estimate of how well this performs as a Short")
    reason: str = Field(description="Why this moment works: the hook and the payoff")


class ClipIdeas(BaseModel):
    clips: list[ClipIdea]


class Candidate(BaseModel):
    start: float
    end: float
    title: str = ""
    hook_text: str = ""
    description: str = ""
    hashtags: list[str] = []
    virality_score: int = 50
    reason: str = ""
    mode: str = "ai"
