"""Build deterministic test videos for the clipper (needs ffmpeg + espeak-ng).

podcast.mp4  1920x1080 30fps ~2.5 min: a face that drifts left/right (face tracking must
             follow it) with spoken narration on several topics and one loud laugh/applause peak.
sports.mp4   1280x720 30fps ~60 s: moving people (OpenCV vtest) with a crowd roar at ~38 s.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent / "media"

SCRIPT = [
    "Welcome back to the show. Today we are talking about the strangest facts in the universe.",
    "Here is the first one. A day on Venus is longer than a year on Venus. It spins so slowly that the sun rises in the west.",
    "That sounds impossible, right? But it is true, and scientists confirmed it with radar in the nineteen sixties.",
    "Now let me tell you the craziest story I have ever heard. A man once tried to sell the Eiffel Tower. Twice.",
    "He convinced scrap metal dealers that the city wanted to get rid of it. And the first buyer was too embarrassed to report him.",
    "So he came back a few months later and tried the exact same trick again. That is unbelievable.",
    "Okay, switching topics. Why do cats knock things off tables? Researchers think it is about attention and play.",
    "If your cat does this at three in the morning, it is probably bored. Give it a toy before bed.",
    "Last thing before we go. Honey never spoils. Archaeologists found honey in Egyptian tombs that was still edible.",
    "Three thousand years old and still good on toast. Thanks for listening, and see you next week.",
]


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd[:6]), "...")
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def speech(out: Path) -> None:
    parts = []
    for i, line in enumerate(SCRIPT):
        p = HERE / f"_line{i}.wav"
        run(["espeak-ng", "-v", "en-us", "-s", "150", "-w", str(p), line])
        parts.append(p)
    lst = HERE / "_lines.txt"
    lst.write_text("".join(f"file '{p.name}'\nfile '_gap.wav'\n" for p in parts))
    run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=22050:cl=mono", "-t", "0.6", str(HERE / "_gap.wav")]
    )
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-ar", "48000", "-ac", "2", str(out)])


def podcast() -> None:
    voice = HERE / "_voice.wav"
    speech(voice)
    dur = float(
        subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(voice)]
        ).decode()
    )
    # Face drifts horizontally across a wide canvas: x oscillates over ~20 s periods.
    vf = (
        "[0:v]scale=1920:1080,boxblur=20,eq=brightness=-0.25[bg];"
        "[1:v]scale=520:520[face];"
        "[bg][face]overlay=x='700+600*sin(2*PI*t/20)':y=260[v]"
    )
    # Applause-like burst (filtered noise) at 40% of the way through, mixed under the voice.
    peak = dur * 0.4
    af = (
        f"[3:a]volume='if(between(t,{peak:.2f},{peak + 2.5:.2f}),0.9,0)':eval=frame,highpass=f=300[noise];"
        "[2:a][noise]amix=inputs=2:duration=first:normalize=0[a]"
    )
    run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x203040:s=1920x1080:r=30:d={dur:.2f}",
            "-loop",
            "1",
            "-i",
            str(HERE / "lena.jpg"),
            "-i",
            str(voice),
            "-f",
            "lavfi",
            "-i",
            f"anoisesrc=color=pink:a=0.6:d={dur:.2f}:r=48000",
            "-filter_complex",
            vf + ";" + af,
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-t",
            f"{dur:.2f}",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            str(HERE / "podcast.mp4"),
        ]
    )


def sports() -> None:
    run(
        [
            "ffmpeg",
            "-y",
            "-stream_loop",
            "8",
            "-i",
            str(HERE / "vtest.avi"),
            "-f",
            "lavfi",
            "-i",
            "anoisesrc=color=brown:a=0.08:d=60:r=48000",
            "-f",
            "lavfi",
            "-i",
            "anoisesrc=color=pink:a=0.9:d=60:r=48000",
            "-filter_complex",
            "[0:v]scale=1280:720,fps=30[v];"
            "[2:a]volume='if(between(t,38,42),1,0)':eval=frame[roar];[1:a][roar]amix=inputs=2:normalize=0[a]",
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-t",
            "60",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(HERE / "sports.mp4"),
        ]
    )


if __name__ == "__main__":
    which = sys.argv[1:] or ["podcast", "sports"]
    if "podcast" in which:
        podcast()
    if "sports" in which:
        sports()
    for p in HERE.glob("_*"):
        p.unlink()
    print("done")
