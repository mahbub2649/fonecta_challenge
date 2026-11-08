#!/usr/bin/env python3
"""The animated graphic for the "What's next" part, in the style of slide 7 of the team's pitch deck.

    python3 tools/render_next.py        # writes demo/out/work/next-cards.mp4 and next-title.png

Demo-only tool (needs Pillow and imageio-ffmpeg). one continuous graphic: each card slides up while its number counts up, earlier cards dim a little as the next
arrives, and the footnote comes last. Text is drawn by code. next-title.png is the closing "Let's connect!".
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_animatic import FFMPEG, FPS, WORK  # noqa: E402

W, H = 1920, 1080
FONT = "/System/Library/Fonts/Avenir Next.ttc"
FACES = {"bold": 0, "demi": 2, "medium": 5, "regular": 7}
TOP, BOTTOM = (11, 18, 112), (31, 72, 224)

CARDS = [
    {"n": "01", "title": "Usage signals",
     "body": "How customers reply, how fast they decide, whether they approve, edit or ignore, and who grants standing permission.",
     "stat": "53%", "stat_text": "of 2025 pilot suggestions got no reply", "count": (0, 53, "{:.0f}%")},
    {"n": "02", "title": "Churn risk",
     "body": "The less a customer engages, the less value they get from Connect. Quiet customers are flagged before they leave.",
     "stat": "1.5x to 1.8x", "stat_text": "search demand on peak special days", "count": (1.0, 1.5, "{:.1f}x to 1.8x")},
    {"n": "03", "title": "Revenue action",
     "body": "Show the value in visits protected, offer paid auto-update with standing permission, and time save and upsell offers.",
     "stat": "36%", "stat_text": "of at-risk views sit in the top 10% of needed changes", "count": (0, 36, "{:.0f}%")},
]
X0, CARD_W, GAP, CARD_Y, CARD_H = 130, 500, 90, 395, 300


def font(size, face="regular"):
    return ImageFont.truetype(FONT, size, index=FACES[face])


def ease(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def background() -> Image.Image:
    img = Image.new("RGB", (W, H))
    px = img.load()
    for y in range(H):
        for x in range(0, W, 4):
            t = (x / W * 0.55 + y / H * 0.45)
            c = tuple(int(TOP[i] + (BOTTOM[i] - TOP[i]) * t) for i in range(3))
            for dx in range(4):
                if x + dx < W:
                    px[x + dx, y] = c
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((1150, 120, 1820, 790), outline=(140, 160, 255, 70), width=3)
    img.paste(glow, (0, 0), glow)
    d = ImageDraw.Draw(img)
    d.text((X0, 130), "WHAT'S NEXT", font=font(28, "demi"), fill=(175, 192, 255))
    d.text((X0, 175), "Our next step: Leveraging usage to determine churn", font=font(66, "bold"), fill="white")
    d.text((X0, 272), "Turning a cost center into potential revenue opportunities", font=font(36), fill=(215, 222, 255))
    return img


def wrap(d, text, fnt, width):
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if d.textlength(trial, font=fnt) <= width:
            line = trial
        else:
            lines.append(line)
            line = word
    return lines + [line]


def card_layer(k: int, stat_value: str, highlight: bool) -> Image.Image:
    """One card and its stat on a transparent layer, at its final position."""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    c = CARDS[k]
    x = X0 + k * (CARD_W + GAP)
    fill = (243, 246, 255, 255) if highlight else (30, 43, 176, 235)
    outline = None if highlight else (70, 90, 230, 255)
    d.rounded_rectangle((x, CARD_Y, x + CARD_W, CARD_Y + CARD_H), 22, fill=fill, outline=outline, width=2)
    ink, soft = ((14, 22, 128), (40, 50, 110)) if highlight else ((255, 255, 255), (222, 228, 255))
    d.text((x + 30, CARD_Y + 30), c["n"], font=font(24, "demi"), fill=(60, 90, 220) if highlight else (180, 195, 255))
    d.text((x + 30, CARD_Y + 66), c["title"], font=font(40, "demi"), fill=ink)
    y = CARD_Y + 128
    for line in wrap(d, c["body"], font(25), CARD_W - 60):
        d.text((x + 30, y), line, font=font(25), fill=soft)
        y += 35
    sy = CARD_Y + CARD_H + 40
    d.rectangle((x, sy, x + 4, sy + 120), fill=(150, 170, 255, 255))
    d.text((x + 24, sy - 6), stat_value, font=font(62, "bold"), fill="white")
    for j, line in enumerate(wrap(d, c["stat_text"], font(25), CARD_W - 40)):
        d.text((x + 24, sy + 72 + j * 33), line, font=font(25), fill=(222, 228, 255))
    return layer


def arrow_layer(k: int, progress: float) -> Image.Image:
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if progress <= 0:
        return layer
    d = ImageDraw.Draw(layer)
    x1 = X0 + (k + 1) * CARD_W + k * GAP + 18
    y = CARD_Y + CARD_H // 2
    x2 = x1 + int((GAP - 36) * progress)
    d.line((x1, y, x2, y), fill=(140, 165, 255, 255), width=6)
    if progress > 0.6:
        d.polygon([(x2 + 4, y), (x2 - 14, y - 12), (x2 - 14, y + 12)], fill=(140, 165, 255, 255))
    return layer


def fade(layer: Image.Image, opacity: float) -> Image.Image:
    if opacity >= 1:
        return layer
    r, g, b, a = layer.split()
    return Image.merge("RGBA", (r, g, b, a.point(lambda v: int(v * max(0.0, opacity)))))


def render(starts: tuple, seconds: float, out: Path, footnote_at: float) -> None:
    """One continuous graphic: card k arrives at starts[k]; earlier cards dim as the next arrives; then the footnote."""
    base = background()
    frames = round(seconds * FPS)
    proc = subprocess.Popen([FFMPEG, "-nostdin", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                             "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                             "-crf", "18", str(out)], stdin=subprocess.PIPE)
    note = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(note).text((X0, 990), "Hypotheses to validate with Connect's real usage data", font=font(26), fill=(205, 214, 255, 255))
    for f in range(frames):
        t = f / FPS
        img = base.copy().convert("RGBA")
        for k, a in enumerate(starts):
            if t < a:
                continue
            nxt = starts[k + 1] if k + 1 < len(starts) else None
            dim = 1 - 0.45 * ease((t - nxt) / 0.5) if nxt is not None else 1.0
            if k:
                img.alpha_composite(fade(arrow_layer(k - 1, ease((t - a - 0.15) / 0.45)), dim))
            lo, hi, fmt = CARDS[k]["count"]
            value = fmt.format(lo + (hi - lo) * ease((t - a - 0.9) / 1.3))
            appear = ease((t - a - (0.45 if k else 0.2)) / 0.6)
            img.alpha_composite(fade(card_layer(k, value, k == 2), appear * dim), (0, int(40 * (1 - appear))))
        img.alpha_composite(fade(note, ease((t - footnote_at) / 0.8)))
        proc.stdin.write(img.convert("RGB").tobytes())
    proc.stdin.close()
    proc.wait()


def title_overlay(out: Path) -> None:
    """The closing slogan: a pun on Fonecta Connect, and an invitation."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    shade = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shade).rectangle((0, 700, W, H), fill=(6, 10, 50, 140))
    img.alpha_composite(shade.filter(ImageFilter.GaussianBlur(60)))
    d = ImageDraw.Draw(img)
    d.text((W / 2, 880), "Let's connect!", font=font(120, "bold"), fill="white", anchor="mm")
    img.save(out)


# When each card arrives inside the graphic (seconds), and the graphic's length. build_next.py times the narration
# to these: line 2 with card 01, line 3 with card 02, line 4 with card 03.
CARD_STARTS = (0.0, 11.0, 17.2)
FOOTNOTE_AT = 23.8
LENGTH = 25.2


def main() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    render(CARD_STARTS, LENGTH, WORK / "next-cards.mp4", FOOTNOTE_AT)
    print(f"wrote next-cards.mp4 ({LENGTH}s)", flush=True)
    title_overlay(WORK / "next-title.png")


if __name__ == "__main__":
    main()
