#!/usr/bin/env python3
"""Cut the story film (part 1) from the generated clips, screens, narration and sounds: demo/out/film-story.mp4.

    python3 tools/build_film.py

Demo-only tool (needs imageio-ffmpeg). It works like an edit decision list:
- each shot plays one stretch of a clip (in-point, length, optional speed);
- shots are joined with dissolves (fades through black between acts);
- a split shot keeps its clip running on the left while a phone panel slides in on the right, changes at the tap,\n  and slides out again;
- every sound is placed at a moment inside a shot and is cut off at the end of that shot unless it's narration.
Still images are never moved, so nothing shakes.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_animatic import FPS, OUT, SCREENS, WORK, asset, audio, duration, run, video_for  # noqa: E402

W, H = 1920, 1080
DISSOLVE, ACT = 0.4, 0.8  # Seconds of cross-dissolve between shots, and of the fade through black between acts.
SPLIT_IN = 0.7  # Seconds for the phone panel to slide in.
END_FADE = 1.0  # Seconds of fade to black (picture and sound) at the end.
# Felt piano; strings join for summer. The winter take came out about 23 dB quieter, so it gets more gain: both end up
# about 14 dB under the narration.
MUSIC_WINTER, MUSIC_WARM = ("story-a-winter", 1.5), ("story-a-warm", 0.11)

# The cut. "at" times in sounds are seconds from the start of that shot.
SHOTS = [
    {"id": "walk", "clip": "v11-emma-walk", "in": 0.0, "dur": 4.0,
     "sounds": [("g1-map", 0.4, 1.0, "voice")]},
    {"id": "door", "clip": "v13b-emma-door", "in": 0.0, "dur": 4.6,
     "sounds": [("fx-handle-rattle", 0.4, 0.6), ("g2-door", 2.0, 1.0, "voice")]},
    {"id": "counter", "clip": "v21-aleksi-counter", "in": 0.0, "dur": 3.8, "join": "act",
     "sounds": [("g3-aleksi", 0.9, 1.0, "voice"), ("fx-chime", 3.1, 0.7)]},
    {"id": "nod", "clip": "v22-aleksi-nod", "in": 0.0, "dur": 6.0,
     "split": {"open_at": 0.0, "panels": [("ui22-message", 0.0), ("ui22-message-yes", 5.4)]},
     "sounds": [("g4-noticed", 1.0, 1.0, "voice"), ("sfx08-tap", 5.4, 0.8)]},
    {"id": "serve", "clip": "v23-aleksi-serve", "in": 0.0, "dur": 4.6,
     "split": {"open_at": None, "close_at": 2.9,
               "panels": [("ui23-updated-0", 0.0), ("ui23-updated-1", 1.3), ("ui23-updated-2", 1.8), ("ui23-updated-3", 2.3)]},
     "sounds": [("g5-updated", 0.4, 1.0, "voice"),
                ("sfx08-tap", 1.3, 0.3), ("sfx08-tap", 1.8, 0.3), ("sfx08-tap", 2.3, 0.3)]},
    {"id": "park", "clip": "v31-summer-park", "in": 0.5, "dur": 4.4, "join": "act",
     "sounds": [("g6-summer", 0.4, 1.0, "voice")]},
    {"id": "sanna", "clip": "v34-sanna-take", "in": 0.8, "dur": 7.6,
     "split": {"open_at": 2.6, "close_at": 5.8, "panels": [("ui33-message", 0.0), ("ui33-message-yes", 5.2)]},
     "sounds": [("g7-sanna", 0.6, 1.0, "voice"), ("fx-chime", 1.6, 0.7),
                ("g8-midnight", 3.2, 1.0, "voice"), ("sfx08-tap", 5.2, 0.8)]},
    # The act 1 locked-door framing again: the door is shut until she pulls it (clip 2.4 s), then the bell.
    {"id": "emma-open", "clip": "v44b-emma-door-opens", "in": 0.8, "dur": 4.2, "join": "act",
     "sounds": [("fx-door-bell", 1.6, 0.8), ("h9-xmas-open", 1.2, 1.0, "voice")]},
    {"id": "terrace", "clip": "v43-terrace-night", "in": 0.0, "dur": 4.8,
     "sounds": [("h10-summer-open", 0.3, 1.0, "voice")]},
]


def clip_path(name: str) -> Path:
    found = video_for(name) or sorted((Path(__file__).resolve().parent.parent / "demo" / "assets").glob(f"{name}-*.mp4"))
    if isinstance(found, list):
        found = found[-1] if found else None
    if not found:
        sys.exit(f"No video clip for {name}")
    return Path(found)


def render(shot: dict, out: Path) -> None:
    dur = shot["dur"]
    if "still" in shot:
        run(["-loop", "1", "-t", f"{dur:.3f}", "-i", str(asset(shot["still"])), "-vf",
             f"scale={W}:{H},fps={FPS},format=yuv420p,setsar=1", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS), str(out)])
        return
    speed = shot.get("speed", 1.0)
    base = (f"[0:v]trim=start={shot['in']:.3f},setpts=(PTS-STARTPTS)/{speed},fps={FPS},"
            f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
            f"tpad=stop_mode=clone:stop_duration=10,trim=duration={dur:.3f},setpts=PTS-STARTPTS,setsar=1[base]")
    split = shot.get("split")
    if not split:
        run(["-i", str(clip_path(shot["clip"])), "-filter_complex", base, "-map", "[base]", "-an",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS), str(out)])
        return
    # p goes 0 -> 1 with an ease while the panel slides in; the picture slides left by a quarter frame meanwhile.
    t0, t1 = split.get("open_at"), split.get("close_at")
    opening = "1" if t0 is None else f"if(lt(t,{t0}),0,if(lt(t,{t0 + SPLIT_IN}),(1-cos(PI*(t-{t0})/{SPLIT_IN}))/2,1))"
    closing = "1" if t1 is None else f"if(lt(t,{t1}),1,if(lt(t,{t1 + SPLIT_IN}),(1+cos(PI*(t-{t1})/{SPLIT_IN}))/2,0))"
    p = f"({opening})*({closing})"
    inputs = ["-i", str(clip_path(shot["clip"]))]
    graph = [base, f"color=c=black:s={W}x{H}:r={FPS}:d={dur:.3f}[bg]", f"[bg][base]overlay=x='-{W // 4}*{p}':y=0:shortest=1[v0]"]
    last = "v0"
    for k, (panel, start) in enumerate(split["panels"]):
        inputs += ["-loop", "1", "-t", f"{dur:.3f}", "-i", str(SCREENS / f"{panel}.png")]
        enable = f":enable='gte(t,{start})'" if start > 0 else ""
        graph.append(f"[{k + 1}:v]fps={FPS},format=rgba[p{k}]")
        graph.append(f"[{last}][p{k}]overlay=x='{W}-{W // 2}*{p}':y=0:shortest=1:eval=frame{enable}[v{k + 1}]")
        last = f"v{k + 1}"
    run([*inputs, "-filter_complex", ";".join(graph), "-map", f"[{last}]", "-an", "-t", f"{dur:.3f}",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS), str(out)])


def main() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    files, starts, t = [], [], 0.0
    for k, shot in enumerate(SHOTS):
        out = WORK / f"story-{k:02d}-{shot['id']}.mp4"
        render(shot, out)
        files.append(out)
        if k:
            t -= ACT if shot.get("join") == "act" else DISSOLVE
        starts.append(t)
        t += shot["dur"]
    total = t

    # Video: chain the shots with dissolves (or fades through black at act changes).
    inputs = [x for f in files for x in ("-i", str(f))]
    graph, last = [], "0:v"
    for k in range(1, len(files)):
        act = SHOTS[k].get("join") == "act"
        kind, length = ("fadeblack", ACT) if act else ("fade", DISSOLVE)
        graph.append(f"[{last}][{k}:v]xfade=transition={kind}:duration={length}:offset={starts[k]:.3f}[x{k}]")
        last = f"x{k}"
    graph.append(f"[{last}]fade=t=out:st={total - END_FADE:.3f}:d={END_FADE}[end]")
    last = "end"
    video = WORK / "story-video.mp4"
    run([*inputs, "-filter_complex", ";".join(graph), "-map", f"[{last}]", "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-r", str(FPS), str(video)])

    # Audio: each sound at its moment. Effects stop (with a short fade) when their shot ends; narration plays out.
    a_inputs, a_graph, labels = [], [], []
    for k, shot in enumerate(SHOTS):
        end = starts[k] + shot["dur"]
        for sound in shot.get("sounds", []):
            name, at, volume = sound[:3]
            voice = len(sound) > 3
            start = starts[k] + at
            i = len(labels)
            a_inputs += ["-i", str(audio(name))]
            chain = f"[{i}:a]volume={volume}"
            if not voice:
                keep = max(0.3, end - start)
                chain += f",atrim=0:{keep:.3f},afade=t=out:st={max(0.0, keep - 0.35):.3f}:d=0.35"
            ms = int(start * 1000)
            a_graph.append(f"{chain},adelay={ms}|{ms}[a{i}]")
            labels.append(f"[a{i}]")
    # A silent bed exactly as long as the film is the base of the mix, so the mix ends on time (padding the end of a
    # mix instead can stall this ffmpeg build).
    # Music: the winter piano under the winter scenes, crossfading into the warm version where summer begins.
    turn = starts[next(k for k, shot in enumerate(SHOTS) if shot["id"] == "park")]
    i = len(labels)
    a_inputs += ["-i", str(audio(MUSIC_WINTER[0])), "-i", str(audio(MUSIC_WARM[0]))]
    a_graph.append(f"[{i}:a]atrim=0:{turn + 1.5:.3f},volume={MUSIC_WINTER[1]},afade=t=in:d=1.5,"
                   f"afade=t=out:st={turn - 1.5:.3f}:d=3.0[mw]")
    warm_ms = int((turn - 1.5) * 1000)
    a_graph.append(f"[{i + 1}:a]atrim=0:{total - turn + 1.5:.3f},volume={MUSIC_WARM[1]},afade=t=in:d=3.0,"
                   f"adelay={warm_ms}|{warm_ms}[mh]")
    labels += ["[mw]", "[mh]"]
    a_graph.append(f"anullsrc=r=44100:cl=stereo,atrim=0:{total:.3f}[bed]")
    labels.append("[bed]")
    a_graph.append("".join(labels) + f"amix=inputs={len(labels)}:duration=longest:normalize=0:dropout_transition=0,"
                   f"alimiter=limit=0.95,atrim=0:{total:.3f},afade=t=out:st={total - END_FADE:.3f}:d={END_FADE}[mix]")
    mix = WORK / "story-audio.m4a"
    run([*a_inputs, "-filter_complex", ";".join(a_graph), "-map", "[mix]", "-c:a", "aac", "-b:a", "192k", str(mix)])

    final = OUT / "film-story.mp4"
    run(["-i", str(video), "-i", str(mix), "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "copy", "-shortest",
         "-movflags", "+faststart", str(final)])
    for k, shot in enumerate(SHOTS):
        print(f"{starts[k]:5.1f}s  {shot['id']}")
    print(f"wrote {final}  ({total:.1f}s)")


if __name__ == "__main__":
    main()
