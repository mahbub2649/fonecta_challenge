#!/usr/bin/env python3
"""Draw the demo film's phone messages and app views as crisp images (demo/screens/*.png).

    python3 tools/render_screens.py

Demo-only tool: needs Pillow (not a dependency of the app). Text is drawn by code, not generated, so every word on
screen is exactly what the storyboard says. Uses macOS's Avenir Next font.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "demo" / "screens"
FONT = "/System/Library/Fonts/Avenir Next.ttc"
FACES = {"bold": 0, "demi": 2, "medium": 5, "regular": 7}
NAVY, BLUE, INK, GREY, LINE, PAPER = "#10168A", "#2F6BFF", "#1B1E2B", "#6B7080", "#E3E6EE", "#F6F7FB"
GREEN, AMBER = "#1E9E5A", "#C98A12"


def font(size: int, face: str = "regular") -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT, size, index=FACES[face])


def wrap(draw: ImageDraw.ImageDraw, text: str, fnt, width: int) -> list:
    lines = []
    for paragraph in text.split("\n"):
        words, line = paragraph.split(" "), ""
        for word in words:
            trial = f"{line} {word}".strip()
            if draw.textlength(trial, font=fnt) <= width:
                line = trial
            else:
                lines.append(line)
                line = word
        lines.append(line)
    return lines


def text_block(draw, xy, text, fnt, width, fill=INK, spacing=1.35) -> int:
    x, y = xy
    for line in wrap(draw, text, fnt, width):
        draw.text((x, y), line, font=fnt, fill=fill)
        y += int(fnt.size * spacing)
    return y


def check(d, cx, cy, size, color="white", width=None):
    """A check mark drawn as lines (the font has no ✓ glyph)."""
    w = width or max(3, size // 6)
    d.line([(cx - size * 0.45, cy), (cx - size * 0.12, cy + size * 0.33), (cx + size * 0.48, cy - size * 0.35)], fill=color, width=w, joint="curve")


def backdrop(size, top="#EEF1FA", bottom="#DCE3F5") -> Image.Image:
    w, h = size
    img = Image.new("RGB", size, top)
    d = ImageDraw.Draw(img)
    a, b = Image.new("RGB", (1, 1), top).getpixel((0, 0)), Image.new("RGB", (1, 1), bottom).getpixel((0, 0))
    for y in range(h):
        t = y / h
        d.line([(0, y), (w, y)], fill=tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3)))
    return img


def phone(sender: str, title: str, body: str, buttons=("Yes", "Edit", "No thanks"), pressed: str | None = None,
          done: list | None = None, bg=("#EEF1FA", "#DCE3F5")) -> Image.Image:
    """A phone on a 960x1080 half-frame with one message card."""
    img = backdrop((960, 1080), *bg)
    shadow = Image.new("RGBA", (960, 1080), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((235, 75, 745, 1025), 70, fill=(20, 24, 60, 90))
    img.paste(shadow.filter(ImageFilter.GaussianBlur(28)), (0, 18), shadow.filter(ImageFilter.GaussianBlur(28)))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((225, 60, 735, 1020), 68, fill="#15171F")
    d.rounded_rectangle((241, 76, 719, 1004), 56, fill="white")
    d.rounded_rectangle((420, 92, 540, 118), 13, fill="#15171F")
    d.text((275, 135), "9:41", font=font(24, "demi"), fill=INK)
    # Header
    d.ellipse((275, 190, 335, 250), fill=NAVY)
    d.text((305, 220), "C", font=font(30, "bold"), fill="white", anchor="mm")
    d.text((352, 192), sender, font=font(26, "demi"), fill=INK)
    d.text((352, 226), "Connect Suggests", font=font(20), fill=GREY)
    d.line((265, 275, 695, 275), fill=LINE, width=2)
    # Card
    y = 305
    d.rounded_rectangle((265, y, 695, y + 470 if not done else y + 610), 28, fill=PAPER)
    y = text_block(d, (295, y + 28), title, font(28, "bold"), 370) + 10
    y = text_block(d, (295, y), body, font(24), 370, fill="#2D3142") + 18
    if done:
        for item in done:
            label, ok = item if isinstance(item, tuple) else (item, True)
            if ok:
                d.ellipse((295, y + 4, 325, y + 34), fill=GREEN)
                check(d, 310, y + 19, 18)
            else:
                d.ellipse((295, y + 4, 325, y + 34), outline=LINE, width=3)
            d.text((340, y), label, font=font(24, "medium"), fill=INK if ok else GREY)
            y += 52
    else:
        for i, label in enumerate(buttons):
            primary = i == 0
            x0, x1 = (295, 665) if primary else ((295, 475) if i == 1 else (485, 665))
            yy = y if primary else y + 84
            is_pressed = pressed == label
            fill = ("#0B0F63" if is_pressed else NAVY) if primary else ("#E6E9F5" if is_pressed else "white")
            d.rounded_rectangle((x0, yy, x1, yy + 66), 33, fill=fill, outline=None if primary else NAVY, width=2)
            cx = (x0 + x1) / 2 + (14 if is_pressed else 0)
            d.text((cx, yy + 33), label, font=font(26, "demi"), fill="white" if primary else NAVY, anchor="mm")
            if is_pressed:
                check(d, cx - d.textlength(label, font=font(26, "demi")) / 2 - 26, yy + 33, 22, "white" if primary else NAVY)
    return img


def app(title: str, subtitle: str) -> tuple:
    """A full-frame app view with a top bar. Returns (image, draw)."""
    img = Image.new("RGB", (1920, 1080), PAPER)
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, 1920, 96), fill=NAVY)
    d.text((70, 48), "Connect Suggests", font=font(34, "bold"), fill="white", anchor="lm")
    d.text((1850, 48), "Kahvila Aurora · Helsinki", font=font(24, "medium"), fill="#C9CDF5", anchor="rm")
    d.text((90, 150), title, font=font(54, "bold"), fill=INK)
    d.text((92, 225), subtitle, font=font(28), fill=GREY)
    return img, d


def card(d, box, fill="white"):
    d.rounded_rectangle(box, 28, fill=fill, outline=LINE, width=2)


def tag(d, xy, label, color):
    x, y = xy
    w = d.textlength(label, font=font(22, "demi")) + 36
    d.rounded_rectangle((x, y, x + w, y + 44), 22, fill=color)
    d.text((x + w / 2, y + 22), label, font=font(22, "demi"), fill="white", anchor="mm")
    return x + w


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    winter = ("Aleksi, Kahvila Aurora", "Christmas Eve, Thu 24 Dec",
              "Last year you closed at 13:00, but the map shows 18:00.\n\nUpdate to 7:30–13:00?")
    phone(*winter).save(OUT / "ui22-message.png")
    phone(*winter, pressed="Yes").save(OUT / "ui22-message-yes.png")
    listings = ["Google Maps", "Google Business Profile", "Facebook"]
    for n in range(len(listings) + 1):
        phone("Aleksi, Kahvila Aurora", "Hours updated", "Christmas Eve, Thu 24 Dec: 7:30–13:00\n\nUpdating your listings:",
              done=[(name, i < n) for i, name in enumerate(listings)]).save(OUT / f"ui23-updated-{n}.png")
    summer = ("Sanna, Terassi Ranta", "Tonight, Sat 18 Jul",
              "27°C and about 10,000 people at the concert in the park nearby. You usually close at 22:00.\n\nStay open until 00:00?")
    phone(*summer, bg=("#FFF4E2", "#FFE2BF")).save(OUT / "ui33-message.png")
    phone(*summer, pressed="Yes", bg=("#FFF4E2", "#FFE2BF")).save(OUT / "ui33-message-yes.png")

    print(f"wrote {len(list(OUT.glob('*.png')))} screens to {OUT}")


if __name__ == "__main__":
    main()
