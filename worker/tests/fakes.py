"""A fake Gemini that answers like the real one (structured objects), for offline tests."""

from __future__ import annotations

from typing import Any

from worker.clipper.moments.schema import ClipIdea, ClipIdeas


class FakeGemini:
    def __init__(self, picks: list[tuple[float, float, int]] | None = None) -> None:
        self.picks = picks or [(23.0, 46.0, 91), (6.0, 22.0, 77), (50.5, 73.0, 64), (24.0, 40.0, 50)]
        self.calls: list[Any] = []

    def generate_json(self, contents, schema, **kw):
        self.calls.append(contents)
        if schema is ClipIdeas:
            return ClipIdeas(
                clips=[
                    ClipIdea(
                        start=s,
                        end=e,
                        title=f"Amazing moment {i}",
                        hook_text="YOU WON'T BELIEVE THIS",
                        description="desc",
                        hashtags=["shorts", "#facts", "#fyp", "#wow", "#viral"],
                        virality_score=v,
                        reason="test",
                    )
                    for i, (s, e, v) in enumerate(self.picks)
                ]
            )
        raise NotImplementedError(schema)

    def video_part(self, **kw):
        return {"video": kw}

    def upload_file(self, path, **kw):
        return {"file": str(path)}

    def delete_file(self, f):
        pass
