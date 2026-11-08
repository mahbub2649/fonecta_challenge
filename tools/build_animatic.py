#!/usr/bin/env python3
"""Shared helpers for the demo film tools: where things are, finding generated clips and audio, and running ffmpeg.

Used by tools/build_film.py (the story), tools/build_platform.py (the narrated screen recording) and
tools/build_next.py (what's next, and the full film). Demo-only (needs imageio-ffmpeg); not part of the app.
The name is historical: this file first held a still-frame prototype of the film.
"""
from __future__ import annotations

import glob
import json
import re
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg

ROOT = Path(__file__).resolve().parent.parent
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
ASSETS, SCREENS, AUDIO = ROOT / "demo" / "assets", ROOT / "demo" / "screens", ROOT / "demo" / "audio"
OUT = ROOT / "demo" / "out"
WORK = OUT / "work"
FPS = 30


def asset(name: str) -> Path:
    if (SCREENS / f"{name}.png").exists():
        return SCREENS / f"{name}.png"
    found = sorted(glob.glob(str(ASSETS / f"{name}-*.jpg")))
    if not found:
        sys.exit(f"No image for {name}")
    return Path(found[-1])


def audio(name: str) -> Path:
    index = json.loads((AUDIO / "index.json").read_text())
    clips = {c["name"]: c for c in json.loads((ROOT / "demo" / "audio.json").read_text())["clips"]}
    # The file that matches the clip's current request (the cache key), whatever name it was first saved under.
    sys.path.insert(0, str(ROOT / "tools"))
    from elevenlabs_audio import cache_key  # noqa: E402
    entry = index.get(cache_key(clips[name]))
    if not entry:
        sys.exit(f"Audio clip {name} isn't generated yet")
    return AUDIO / entry["file"]


# The video clip made from each still (tools/pruna_assets.py). A shot uses its clip when it exists.
VIDEO_FOR = {"s11-emma-walk": "v11-emma-walk", "hook-phone": "v12-phone", "s13-emma-door": "v13-emma-door",
             "s21-aleksi-counter": "v21-aleksi-counter", "s22-aleksi-nod": "v22-aleksi-nod", "s23-aleksi-serve": "v23-aleksi-serve",
             "s31-summer-park": "v31-summer-park", "s32-sanna-phone": "v32-sanna-phone", "s33-sanna-nod": "v33-sanna-nod",
             "s41-emma-door-open": "v41-emma-door-open", "s41-terrace-crowd": "v41-terrace-crowd",
             "s42-emma-coffee": "v42-emma-coffee", "s42-sanna-pour": "v42-sanna-pour",
             "s50-office": "v50-office", "s56-office-smile": "v56-office-smile"}


def video_for(name: str) -> Path | None:
    found = sorted(glob.glob(str(ASSETS / f"{VIDEO_FOR.get(name, '-')}-*.mp4")))
    return Path(found[-1]) if found else None


def duration(path: Path) -> float:
    err = subprocess.run([FFMPEG, "-i", str(path)], capture_output=True, text=True).stderr
    h, m, s = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err).groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


def run(args: list) -> None:
    # -nostdin: never wait for keyboard input, which hangs a render that runs in the background.
    result = subprocess.run([FFMPEG, "-nostdin", "-y", "-loglevel", "error", *args], capture_output=True, text=True,
                            stdin=subprocess.DEVNULL)
    if result.returncode:
        sys.exit(result.stderr[-1500:])
