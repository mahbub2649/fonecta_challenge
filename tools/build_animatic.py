#!/usr/bin/env python3
"""Assemble the prototype film (an animatic) from the generated stills, screens, narration and sound effects.

    python3 tools/build_animatic.py            # writes demo/out/film-draft.mp4 (--fresh re-renders every shot)

Demo-only tool: needs the imageio-ffmpeg package for an ffmpeg binary (not a dependency of the app). Each shot is a
still with a slow camera move; split shots put a character on the left and a phone on the right. A scene lasts as long
as its narration plus a short breath, so retiming the voice retimes the film.
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


def still(path: Path, seconds: float, size: tuple, out: Path, zoom: float = 0.06) -> None:
    """A still with a slow push-in, cropped to fill `size`."""
    w, h = size
    frames = max(1, round(seconds * FPS))
    vf = (f"scale={w * 2}:{h * 2}:force_original_aspect_ratio=increase,crop={w * 2}:{h * 2},"
          f"zoompan=z='1+{zoom}*on/{frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={w}x{h}:fps={FPS},setsar=1")
    run(["-loop", "1", "-t", f"{seconds:.3f}", "-i", str(path), "-vf", vf, "-frames:v", str(frames),
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS), str(out)])


def moving(path: Path, seconds: float, size: tuple, out: Path) -> None:
    """A video clip cropped to fill `size`, held on its last frame if the scene runs longer. Its own sound is dropped."""
    w, h = size
    vf = (f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={FPS},"
          f"tpad=stop_mode=clone:stop_duration=30,trim=duration={seconds:.3f},setpts=PTS-STARTPTS,setsar=1")
    run(["-i", str(path), "-vf", vf, "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS), str(out)])


def picture(name: str, seconds: float, size: tuple, out: Path, zoom: float) -> None:
    clip = video_for(name)
    if clip:
        moving(clip, seconds, size, out)
    else:
        still(asset(name), seconds, size, out, zoom)


def shot(item: dict, seconds: float, out: Path) -> None:
    sources = [video_for(item[k]) or asset(item[k]) for k in ("full", "left", "right") if k in item]
    if REUSE and out.exists() and abs(duration(out) - seconds) < 0.1 and all(out.stat().st_mtime > s.stat().st_mtime for s in sources):
        return  # Same shot, same length: already rendered.
    if "full" in item:
        picture(item["full"], seconds, (1920, 1080), out, item.get("zoom", 0.06))
        return
    left, right = WORK / (out.stem + "-l.mp4"), WORK / (out.stem + "-r.mp4")
    picture(item["left"], seconds, (960, 1080), left, 0.06)
    picture(item["right"], seconds, (960, 1080), right, 0.015)
    run(["-i", str(left), "-i", str(right), "-filter_complex", "[0:v][1:v]hstack=inputs=2[v]", "-map", "[v]",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS), str(out)])


# Each scene: shots (a share of the scene, the last takes the rest), the narration, and sounds (clip, start, volume).
SPLIT = lambda left, right: {"left": left, "right": right}  # noqa: E731
SCENES = [
    # Part 1: the film
    {"shots": [{"full": "s11-emma-walk"}], "min": 5.0, "sfx": [("sfx01-snow-door", 0, 0.8)]},
    {"voice": "n01-hook", "shots": [{"full": "hook-phone", "share": 0.5}, {"full": "s13-emma-door"}], "sfx": [("sfx01-snow-door", 2.5, 0.45)]},
    {"voice": "f21-aleksi", "shots": [{"full": "s21-aleksi-counter"}], "sfx": [("sfx02-cafe-busy", 0, 0.35), ("sfx03-message", -2.8, 0.7)]},
    {"voice": "f22-tap", "shots": [{**SPLIT("s22-aleksi-nod", "ui22-message"), "share": 0.55}, SPLIT("s22-aleksi-nod", "ui22-message-yes")],
     "sfx": [("sfx02-cafe-busy", 0, 0.2), ("sfx08-tap", "switch", 0.8)]},
    {"voice": "f23-updated", "shots": [SPLIT("s23-aleksi-serve", "ui23-updated")], "sfx": [("sfx02-cafe-busy", 0, 0.3)]},
    {"voice": "f31-summer", "shots": [{"full": "s31-summer-park"}], "sfx": [("sfx06-summer-park", 0, 0.55)]},
    {"voice": "f32-sanna", "shots": [{"full": "s32-sanna-phone"}], "sfx": [("sfx07-terrace", 0, 0.35), ("sfx03-message", 0.6, 0.7)]},
    {"voice": "f33-yes", "shots": [{**SPLIT("s33-sanna-nod", "ui33-message"), "share": 0.5}, SPLIT("s33-sanna-nod", "ui33-message-yes")],
     "min": 4.5, "sfx": [("sfx07-terrace", 0, 0.25), ("sfx08-tap", "switch", 0.8)]},
    {"voice": "f41-doors", "shots": [SPLIT("s41-emma-door-open", "s41-terrace-crowd")], "sfx": [("sfx04-cafe-open", 0, 0.55)]},
    {"voice": "f42-open", "shots": [SPLIT("s42-emma-coffee", "s42-sanna-pour")], "min": 5.0, "sfx": [("sfx04-cafe-open", 0, 0.35)]},
    {"voice": "n11-title", "shots": [{"full": "title", "zoom": 0.02}], "min": 4.0, "sfx": [("sfx05-tone", 0, 0.6)]},
    # Part 2: the platform
    {"voice": "p51-idea", "shots": [{"full": "s50-office"}], "music": True},
    {"voice": "p52-detect", "shots": [{"full": "ui51-overview", "share": 0.35, "zoom": 0.02}, {"full": "ui52-detect", "zoom": 0.02}], "music": True},
    {"voice": "p53-suggest", "shots": [{"full": "ui53-suggest", "zoom": 0.02}], "music": True},
    {"voice": "p54-message", "shots": [{"full": "ui54-languages", "zoom": 0.02}], "music": True},
    {"voice": "p55-apply", "shots": [{"full": "ui55-apply", "zoom": 0.02}], "music": True},
    {"voice": "p56-learn", "shots": [{"full": "s56-office-smile", "share": 0.3}, {"full": "ui56-learn", "zoom": 0.02}], "music": True},
    {"voice": "p57-value", "shots": [{"full": "ui57-value", "zoom": 0.02}], "music": True},
    {"shots": [{"full": "title", "zoom": 0.02}], "min": 3.0, "sfx": [("sfx05-tone", 0, 0.5)], "music": True},
]
LEAD, BREATH = 0.35, 0.75
REUSE = "--fresh" not in sys.argv  # Rendered shots are reused when their length hasn't changed.  # Seconds before the voice starts, and after it ends.


def main() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    t, clips, sounds, music_spans = 0.0, [], [], []
    for n, scene in enumerate(SCENES):
        voice = audio(scene["voice"]) if scene.get("voice") else None
        length = max(scene.get("min", 0.0), (duration(voice) + LEAD + BREATH) if voice else 0.0)
        if len(scene["shots"]) == 1:
            item = scene["shots"][0]
            own = [video_for(item[k]) for k in ("full", "left", "right") if k in item]
            length = max([length] + [duration(c) - 0.2 for c in own if c])
        if voice:
            sounds.append((voice, t + LEAD, 1.0))
        offset, switch = 0.0, None
        for k, item in enumerate(scene["shots"]):
            last = k == len(scene["shots"]) - 1
            seconds = length - offset if last else length * item.get("share", 1 / len(scene["shots"]))
            out = WORK / f"scene{n:02d}-{k}.mp4"
            shot(item, seconds, out)
            clips.append(out)
            offset += seconds
            if k == 0 and not last:
                switch = offset
        for name, start, volume in scene.get("sfx", []):
            start = switch if start == "switch" else (length + start if start < 0 else start)
            sounds.append((audio(name), t + start, volume))
        if scene.get("music"):
            music_spans.append((t, t + length))
        print(f"scene {n:2d}: {t:6.1f}s  +{length:4.1f}s  {scene.get('voice', '-')}", flush=True)
        t += length
    total = t

    concat = WORK / "concat.txt"
    concat.write_text("".join(f"file '{c}'\n" for c in clips))
    video = WORK / "video.mp4"
    run(["-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(video)])

    # Audio: every sound at its time, plus the music bed looped under part 2 with fades.
    inputs, filters = [], []
    for i, (path, start, volume) in enumerate(sounds):
        inputs += ["-i", str(path)]
        ms = int(start * 1000)
        filters.append(f"[{i}:a]volume={volume},adelay={ms}|{ms}[a{i}]")
    labels = [f"[a{i}]" for i in range(len(sounds))]
    if music_spans:
        start, end = music_spans[0][0], music_spans[-1][1]
        i = len(sounds)
        bed = audio("sfx09-music-bed")
        loops = int((end - start) // duration(bed)) + 1  # A finite loop: an endless one never lets ffmpeg finish.
        inputs += ["-stream_loop", str(loops), "-i", str(bed)]
        ms = int(start * 1000)
        filters.append(f"[{i}:a]atrim=0:{end - start:.2f},afade=t=in:d=1.5,afade=t=out:st={end - start - 2:.2f}:d=2,"
                       f"volume=0.16,adelay={ms}|{ms}[m]")
        labels.append("[m]")
    filters.append("".join(labels) + f"amix=inputs={len(labels)}:normalize=0:dropout_transition=0,"
                   f"alimiter=limit=0.95,apad,atrim=0:{total:.2f}[mix]")
    mix = WORK / "audio.m4a"
    run([*inputs, "-filter_complex", ";".join(filters), "-map", "[mix]", "-c:a", "aac", "-b:a", "192k", str(mix)])

    final = OUT / "film-draft.mp4"
    run(["-i", str(video), "-i", str(mix), "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "copy", "-shortest",
         "-movflags", "+faststart", str(final)])
    print(f"wrote {final}  ({total:.0f}s, {final.stat().st_size // (1024 * 1024)} MB)")


if __name__ == "__main__":
    main()
