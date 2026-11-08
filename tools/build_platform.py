#!/usr/bin/env python3
"""Narrate the screen recording of the real app, then join it after the story film.

    python3 tools/build_platform.py

Writes demo/out/film-platform.mp4 (the recording with narration and captions) and demo/out/film-full.mp4 (story film
followed by the recording). Demo-only tool (needs Pillow and imageio-ffmpeg). The raw recording is
demo/implementation_demonstration.mov (git-ignored).

Each segment is a stretch of the recording, shown full screen or zoomed on the phone, at normal or faster speed. The
narration line for a group of segments starts shortly after the group does, and its caption shows while it's spoken.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_animatic import FPS, OUT, ROOT, WORK, audio, duration, run  # noqa: E402

W, H = 1920, 1080
RECORDING = ROOT / "demo" / "implementation_demonstration.mov"
FONT = "/System/Library/Fonts/Avenir Next.ttc"
DISSOLVE = 0.35
VOICE_LEAD = 0.35  # Seconds into a group before its line starts.

# Views on the 4096x2406 recording: the whole screen, or a 16:9 zoom on the phone and the right of the console.
FULL = None
PHONE = (1429, 300, 2667, 1500)  # x, y, width, height

# Segments: (start, end) in the recording, the view, the speed, and the narration line that starts with it (if any).
SEGMENTS = [
    {"src": (0.0, 3.8), "view": FULL, "voice": "q1-demo", "caption": "Now for a quick demonstration."},
    {"src": (3.8, 11.9), "view": FULL, "join": "cut", "voice": "q2-detect",
     "caption": "It finds two days that will show the wrong hours, with the evidence, and how sure it is."},
    {"src": (11.9, 17.6), "view": PHONE, "voice": "q3-message",
     "caption": "One message goes out, in the owner's own language. Here, Finnish."},
    {"src": (17.7, 22.0), "view": PHONE, "join": "cut", "voice": "q4-approve",
     "caption": "The link opens a page with no login. Each day shows what Google says now, the suggestion and why. Approve, edit or decline."},
    {"src": (22.0, 31.0), "view": PHONE, "speed": 1.5, "join": "cut"},
    {"src": (31.1, 44.3), "view": PHONE, "voice": "q5-apply",
     "caption": "Approved. Connect writes it to Yext, checks it saved, and shows where it goes live: Google, Bing, Apple Maps and more. Then it offers to handle holidays from now on."},
    {"src": (44.3, 51.0), "view": FULL, "voice": "q6-standing",
     "caption": "The owner says yes. Next time, holidays just update, with a one-tap undo."},
]


def caption_image(text: str, out: Path, centre: float = W / 2, max_width: int = 1500) -> None:
    """A caption bar on a transparent 1920x1080 frame. In the phone zoom it sits left, so it never covers the phone."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fnt = ImageFont.truetype(FONT, 38, index=5)
    words, lines, line = text.split(), [], ""
    for word in words:
        trial = f"{line} {word}".strip()
        if d.textlength(trial, font=fnt) <= max_width:
            line = trial
        else:
            lines.append(line)
            line = word
    lines.append(line)
    height = 30 + 52 * len(lines)
    top = H - 70 - height
    width = max(d.textlength(x, font=fnt) for x in lines) + 70
    d.rounded_rectangle((centre - width / 2, top, centre + width / 2, top + height), 18, fill=(10, 14, 46, 205))
    for k, x in enumerate(lines):
        d.text((centre, top + 15 + 52 * k + 26), x, font=fnt, fill="white", anchor="mm")
    img.save(out)


def render(seg: dict, out: Path) -> float:
    start, end = seg["src"]
    speed = seg.get("speed", 1.0)
    if seg["view"] is FULL:
        frame = f"scale=-2:{H},pad={W}:{H}:(ow-iw)/2:0:color=#EEF0F5"
    else:
        x, y, w, h = seg["view"]
        frame = f"crop={w}:{h}:{x}:{y},scale={W}:{H}"
    vf = f"trim=start={start}:end={end},setpts=(PTS-STARTPTS)/{speed},fps={FPS},{frame},setsar=1,format=yuv420p"
    run(["-i", str(RECORDING), "-vf", vf, "-an", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(FPS), str(out)])
    return (end - start) / speed


def main() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    files, starts, lengths, t = [], [], [], 0.0
    for k, seg in enumerate(SEGMENTS):
        out = WORK / f"platform-{k:02d}.mp4"
        length = render(seg, out)
        if k:
            t -= 0.0 if seg.get("join") == "cut" else DISSOLVE
        files.append(out)
        starts.append(t)
        lengths.append(length)
        t += length
    total = t

    # Picture: dissolves where the view changes, straight cuts within one view (it's continuous footage), then captions.
    inputs = [x for f in files for x in ("-i", str(f))]
    # Every clip on one timebase first: crossfades refuse inputs whose timebases differ.
    graph = [f"[{k}:v]settb=AVTB,fps={FPS},setpts=PTS-STARTPTS[i{k}]" for k in range(len(files))]
    last = "i0"
    for k in range(1, len(files)):
        if SEGMENTS[k].get("join") == "cut":
            graph.append(f"[{last}][i{k}]concat=n=2:v=1:a=0,settb=AVTB,fps={FPS}[x{k}]")
        else:
            graph.append(f"[{last}][i{k}]xfade=transition=fade:duration={DISSOLVE}:offset={starts[k]:.3f}[x{k}]")
        last = f"x{k}"
    n = len(files)
    voices = []
    for k, seg in enumerate(SEGMENTS):
        if seg.get("voice"):
            at = starts[k] + VOICE_LEAD
            voices.append((seg["voice"], at, at + duration(audio(seg["voice"])), seg["caption"], seg["view"] is not FULL))
    for j, (name, at, until, text, zoomed) in enumerate(voices):
        png = WORK / f"caption-{j}.png"
        caption_image(text, png, 640, 1050) if zoomed else caption_image(text, png)
        inputs += ["-loop", "1", "-t", f"{total:.3f}", "-i", str(png)]
        graph.append(f"[{last}][{n + j}:v]overlay=0:0:shortest=1:enable='between(t,{at:.2f},{until + 0.3:.2f})'[c{j}]")
        last = f"c{j}"
    graph.append(f"[{last}]fade=t=in:d=0.6,fade=t=out:st={total - 0.8:.3f}:d=0.8[v]")
    video = WORK / "platform-video.mp4"
    run([*inputs, "-filter_complex", ";".join(graph), "-map", "[v]", "-t", f"{total:.3f}", "-c:v", "libx264", "-crf", "18",
         "-pix_fmt", "yuv420p", "-r", str(FPS), str(video)])

    # Sound: the narration, over a soft music bed (looped a fixed number of times) that dips under the voice.
    a_inputs, a_graph, labels = [], [], []
    for j, (name, at, *_) in enumerate(voices):
        a_inputs += ["-i", str(audio(name))]
        ms = int(at * 1000)
        a_graph.append(f"[{j}:a]adelay={ms}|{ms}[v{j}]")
        labels.append(f"[v{j}]")
    bed = audio("sfx09-music-bed")
    loops = int(total // duration(bed)) + 1
    a_inputs += ["-stream_loop", str(loops), "-i", str(bed)]
    m = len(voices)
    a_graph.append(f"[{m}:a]atrim=0:{total:.3f},volume=0.12,afade=t=in:d=1.0,afade=t=out:st={total - 1.5:.3f}:d=1.5[bed]")
    labels.append("[bed]")
    a_graph.append(f"anullsrc=r=44100:cl=stereo,atrim=0:{total:.3f}[sil]")
    labels.append("[sil]")
    a_graph.append("".join(labels) + f"amix=inputs={len(labels)}:duration=longest:normalize=0:dropout_transition=0,"
                   f"alimiter=limit=0.95,atrim=0:{total:.3f}[mix]")
    mix = WORK / "platform-audio.m4a"
    run([*a_inputs, "-filter_complex", ";".join(a_graph), "-map", "[mix]", "-c:a", "aac", "-b:a", "192k", str(mix)])

    platform = OUT / "film-platform.mp4"
    run(["-i", str(video), "-i", str(mix), "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "copy", "-shortest",
         "-movflags", "+faststart", str(platform)])

    # The full film: story, then the platform part.
    story = OUT / "film-story.mp4"
    full = OUT / "film-full.mp4"
    run(["-i", str(story), "-i", str(platform), "-filter_complex",
         f"[0:v]fps={FPS},format=yuv420p,setsar=1[sv];[1:v]fps={FPS},format=yuv420p,setsar=1[pv];"
         "[0:a]aresample=44100[sa];[1:a]aresample=44100[pa];[sv][sa][pv][pa]concat=n=2:v=1:a=1[v][a]",
         "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
         "-movflags", "+faststart", str(full)])
    for k, seg in enumerate(SEGMENTS):
        print(f"{starts[k]:5.1f}s  {seg['src'][0]:4.1f}-{seg['src'][1]:4.1f}s of the recording  "
              f"{'phone zoom' if seg['view'] else 'full screen'}{' x' + str(seg['speed']) if seg.get('speed') else ''}")
    print(f"wrote {platform} ({total:.1f}s) and {full} ({duration(story) + total:.1f}s)")


if __name__ == "__main__":
    main()
