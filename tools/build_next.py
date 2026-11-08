#!/usr/bin/env python3
"""Cut the "What's next" part (slide 7 of the pitch deck) and join the whole film.

    python3 tools/render_next.py     # the animated graphics, first
    python3 tools/build_next.py      # demo/out/film-next.mp4 and demo/out/film-full.mp4

Demo-only tool (needs imageio-ffmpeg). Linnea, a Connect team member at a standing desk, opens it; one continuous graphic in
the deck's style builds the three cards as the narration explains them; she closes it with "Let's connect!". film-full.mp4 is the story
film, then the demo of the real app, then this part.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_animatic import FPS, OUT, WORK, audio, duration, run  # noqa: E402
from build_film import clip_path  # noqa: E402

W, H = 1920, 1080
DISSOLVE, END_FADE = 0.4, 1.2

SHOTS = [
    {"clip": "vn1b-wide", "dur": 4.0, "voice": [("w1-next", 1.6)]},
    {"graphic": "next-cards", "dur": 25.2,
     "voice": [("w2-signals", 0.3), ("w3-churn", 11.0), ("w4-revenue", 17.2)]},
    {"clip": "vn7-end", "dur": 5.2, "title": True, "voice": [("w5-connect", 1.8)]},
]


def render(shot: dict, out: Path) -> None:
    dur = shot["dur"]
    if "graphic" in shot:
        source = WORK / f"{shot['graphic']}.mp4"
        vf = f"fps={FPS},tpad=stop_mode=clone:stop_duration=5,trim=duration={dur:.3f},setpts=PTS-STARTPTS,setsar=1,format=yuv420p"
        run(["-i", str(source), "-vf", vf, "-an", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(FPS), str(out)])
        return
    base = (f"[0:v]fps={FPS},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
            f"tpad=stop_mode=clone:stop_duration=5,trim=duration={dur:.3f},setpts=PTS-STARTPTS,setsar=1[v]")
    inputs, graph, last = ["-i", str(clip_path(shot["clip"]))], [base], "v"
    if shot.get("title"):
        inputs += ["-loop", "1", "-t", f"{dur:.3f}", "-i", str(WORK / "next-title.png")]
        graph.append(f"[1:v]format=rgba,fade=t=in:st=0.8:d=0.8:alpha=1[t]")
        graph.append(f"[v][t]overlay=0:0:shortest=1[o]")
        last = "o"
    run([*inputs, "-filter_complex", ";".join(graph), "-map", f"[{last}]", "-an", "-t", f"{dur:.3f}",
         "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(FPS), str(out)])


def main() -> None:
    files, starts, t = [], [], 0.0
    for k, shot in enumerate(SHOTS):
        out = WORK / f"next-{k:02d}.mp4"
        render(shot, out)
        if k:
            t -= DISSOLVE
        files.append(out)
        starts.append(t)
        t += shot["dur"]
    total = t

    inputs = [x for f in files for x in ("-i", str(f))]
    graph = [f"[{k}:v]settb=AVTB,fps={FPS},setpts=PTS-STARTPTS[i{k}]" for k in range(len(files))]
    last = "i0"
    for k in range(1, len(files)):
        graph.append(f"[{last}][i{k}]xfade=transition=fade:duration={DISSOLVE}:offset={starts[k]:.3f}[x{k}]")
        last = f"x{k}"
    graph.append(f"[{last}]fade=t=in:d=0.6,fade=t=out:st={total - END_FADE:.3f}:d={END_FADE}[v]")
    video = WORK / "next-video.mp4"
    run([*inputs, "-filter_complex", ";".join(graph), "-map", "[v]", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
         "-r", str(FPS), str(video)])

    # Sound: narration over the piano, which is two takes crossfaded so it runs the whole part without a loop seam.
    a_inputs, a_graph, labels = [], [], []
    for k, shot in enumerate(SHOTS):
        for name, at in shot.get("voice", []):
            i = len(labels)
            a_inputs += ["-i", str(audio(name))]
            ms = int((starts[k] + at) * 1000)
            a_graph.append(f"[{i}:a]adelay={ms}|{ms}[n{i}]")
            labels.append(f"[n{i}]")
    m = len(labels)
    piano = audio("music-a-long")
    a_inputs += ["-i", str(piano), "-i", str(piano)]
    a_graph.append(f"[{m}:a][{m + 1}:a]acrossfade=d=4:c1=tri:c2=tri,atrim=0:{total:.3f},volume=0.2,"
                   f"afade=t=in:d=1.5,afade=t=out:st={total - 2.0:.3f}:d=2.0[music]")
    labels.append("[music]")
    a_graph.append(f"anullsrc=r=44100:cl=stereo,atrim=0:{total:.3f}[sil]")
    labels.append("[sil]")
    a_graph.append("".join(labels) + f"amix=inputs={len(labels)}:duration=longest:normalize=0:dropout_transition=0,"
                   f"alimiter=limit=0.95,atrim=0:{total:.3f}[mix]")
    mix = WORK / "next-audio.m4a"
    run([*a_inputs, "-filter_complex", ";".join(a_graph), "-map", "[mix]", "-c:a", "aac", "-b:a", "192k", str(mix)])

    part = OUT / "film-next.mp4"
    run(["-i", str(video), "-i", str(mix), "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "copy", "-shortest",
         "-movflags", "+faststart", str(part)])

    # The whole film: story, demo, what's next.
    pieces = [OUT / "film-story.mp4", OUT / "film-platform.mp4", part]
    inputs, graph = [], []
    for k, p in enumerate(pieces):
        inputs += ["-i", str(p)]
        graph.append(f"[{k}:v]fps={FPS},format=yuv420p,setsar=1[v{k}];[{k}:a]aresample=44100[a{k}]")
    graph.append("".join(f"[v{k}][a{k}]" for k in range(len(pieces))) + f"concat=n={len(pieces)}:v=1:a=1[v][a]")
    full = OUT / "film-full.mp4"
    run([*inputs, "-filter_complex", ";".join(graph), "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "18",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(full)])
    print(f"wrote {part} ({total:.1f}s) and {full} ({sum(duration(p) for p in pieces):.1f}s)")


if __name__ == "__main__":
    main()
