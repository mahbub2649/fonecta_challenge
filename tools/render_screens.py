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

    # 5.1 Overview
    img, d = app("Every listing, watched", "3,000 Connect customers in Finland, Sweden and Norway · 7 Nov 2026 – 6 Jan 2027")
    for i, (big, small, color) in enumerate([("3,000", "businesses watched", NAVY), ("753", "owners with hours to fix", BLUE),
                                             ("74%", "of at-risk search views protected", GREEN), ("87%", "of closed-door visits prevented", GREEN)]):
        x = 90 + i * 445
        card(d, (x, 320, x + 415, 560))
        d.text((x + 40, 350), big, font=font(84, "bold"), fill=color)
        text_block(d, (x + 42, 470), small, font(28, "medium"), 340, fill=GREY)
    card(d, (90, 610, 1830, 990))
    d.text((130, 645), "Highest priority this week", font=font(32, "demi"), fill=INK)
    for j, (name, day, views) in enumerate([("Kahvila Aurora", "Christmas Eve · Christmas Day", "430 search views"),
                                            ("Muoti Lyhty", "Christmas Eve · Boxing Day", "390 search views"),
                                            ("Kafé Linnea", "Julafton · Juldagen", "190 search views")]):
        y = 720 + j * 85
        d.text((130, y), name, font=font(30, "demi"), fill=INK)
        d.text((560, y + 2), day, font=font(28), fill=GREY)
        d.text((1790, y + 2), views, font=font(28, "medium"), fill=NAVY, anchor="ra")
    img.save(OUT / "ui51-overview.png")

    # 5.2 Detect
    img, d = app("Detect: Christmas Eve, Thu 24 Dec", "What Connect checked before suggesting anything")
    card(d, (90, 300, 1150, 990))
    rows = [("Map shows today", "7:30–18:00 (regular Thursday hours)"), ("Last year", "7:30–13:00, entered by the owner"),
            ("Customer reviews", "“Closed on the holiday, although the map said open”"), ("Calls and clicks", "Spike on last Christmas Eve"),
            ("Similar cafés nearby", "Most close early on Christmas Eve"), ("Shopping centre and events", "None affect this café")]
    for j, (label, value) in enumerate(rows):
        y = 340 + j * 105
        d.ellipse((130, y + 8, 160, y + 38), fill=GREEN if j < 5 else LINE)
        d.text((185, y), label, font=font(30, "demi"), fill=INK)
        d.text((185, y + 42), value, font=font(26), fill=GREY)
    card(d, (1200, 300, 1830, 990), fill="#EEF1FF")
    d.text((1250, 345), "Suggestion", font=font(30, "demi"), fill=GREY)
    d.text((1250, 400), "7:30–13:00", font=font(84, "bold"), fill=NAVY)
    d.text((1250, 520), "instead of 7:30–18:00", font=font(30), fill=INK)
    tag(d, (1250, 600), "Confident: stated", GREEN)
    text_block(d, (1250, 690), "Reason kept for the owner and the audit trail.", font(28), 530, fill=GREY)
    img.save(OUT / "ui52-detect.png")

    # 5.3 Suggest / ask / quiet
    img, d = app("Suggest only when it's worth it", "How sure Connect is decides how it speaks")
    for i, (head, color, line, example) in enumerate([
            ("Confident", GREEN, "States the suggestion", "“We suggest 7:30–13:00. Last year: 7:30–13:00.”"),
            ("Unsure", AMBER, "Asks as a question", "“We're not completely sure, so is this right?”"),
            ("No evidence", GREY, "Stays quiet", "No message. No guessing, no spam.")]):
        x = 90 + i * 590
        card(d, (x, 320, x + 560, 900))
        tag(d, (x + 40, 360), head, color)
        d.text((x + 40, 450), line, font=font(40, "bold"), fill=INK)
        text_block(d, (x + 40, 540), example, font(30), 480, fill="#2D3142")
    d.text((960, 960), "Nothing is published without the owner's yes, or standing permission they gave.", font=font(28, "medium"), fill=NAVY, anchor="mm")
    img.save(OUT / "ui53-suggest.png")

    # 5.4 Languages
    img = backdrop((1920, 1080))
    d = ImageDraw.Draw(img)
    d.text((960, 90), "One message, in the owner's language", font=font(54, "bold"), fill=INK, anchor="mm")
    for i, (who, title, body, ok, edit, no) in enumerate([
            ("Aleksi · Suomi", "Jouluaatto to 24.12.", "Google näyttää 7.30–18. Ehdotamme: 7.30–13. Viime vuonna: 7.30–13.", "Hyväksy", "Muokkaa", "Ei kiitos"),
            ("Maria · Svenska", "Julafton tors 24/12", "Google visar 8–18. Vi föreslår: stängt. Förra året: stängt.", "Godkänn", "Ändra", "Nej tack"),
            ("Marte · Norsk", "Julaften tor 24.12.", "Google viser 7–18. Vi foreslår: 6–12.", "Godkjenn", "Endre", "Nei takk")]):
        p = phone(who, title, body, buttons=(ok, edit, no)).resize((640, 720))
        img.paste(p, (i * 640, 250))
    img.save(OUT / "ui54-languages.png")

    # 5.5 Apply
    img, d = app("Apply, check, confirm", "Only a change that's been read back counts as done")
    steps = [("Owner said yes", "Christmas Eve 7:30–13:00"), ("Written to Yext", "Connect's backend, the full hours object"),
             ("Read back and checked", "Matches what the owner approved"), ("Owner told where it's live", "Search, maps, directories, AI assistants")]
    for j, (head, sub) in enumerate(steps):
        x = 90 + j * 445
        card(d, (x, 360, x + 415, 760))
        d.ellipse((x + 40, 400, x + 120, 480), fill=GREEN)
        check(d, x + 80, 442, 40, width=7)
        text_block(d, (x + 40, 520), head, font(36, "bold"), 340)
        text_block(d, (x + 40, 640), sub, font(26), 340, fill=GREY)
    d.text((960, 880), "If a write fails, the owner is told nothing changed.", font=font(30, "medium"), fill=NAVY, anchor="mm")
    img.save(OUT / "ui55-apply.png")

    # 5.6 Learning
    img, d = app("It learns from every answer", "Edits, declines and standing permission shape what comes next")
    card(d, (90, 310, 930, 990))
    d.text((130, 350), "What the owner did", font=font(32, "demi"), fill=INK)
    for j, (head, sub) in enumerate([("Edited Christmas Eve to close at 14:00", "Next suggestions move the same way"),
                                     ("Declined Father's Day: “open as usual”", "Connect won't ask about it again"),
                                     ("“Handle public holidays for me”", "Strong suggestions applied, then the owner is told")]):
        y = 430 + j * 170
        d.text((130, y), head, font=font(30, "demi"), fill=INK)
        d.text((130, y + 48), sub, font=font(26), fill=GREY)
    card(d, (980, 310, 1830, 990), fill="#EEF1FF")
    d.text((1030, 350), "Standing permission", font=font(32, "demi"), fill=INK)
    d.rounded_rectangle((1030, 420, 1170, 490), 35, fill=GREEN)
    d.ellipse((1100, 425, 1165, 485), fill="white")
    d.text((1200, 455), "Holidays handled for me", font=font(30, "medium"), fill=INK, anchor="lm")
    d.text((1030, 560), "Applied: Boxing Day, closed", font=font(30), fill=INK)
    d.rounded_rectangle((1030, 630, 1330, 700), 35, outline=NAVY, width=3)
    d.text((1180, 665), "Undo", font=font(30, "demi"), fill=NAVY, anchor="mm")
    text_block(d, (1030, 760), "Every step is in the audit trail: what, why, and who decided.", font(28), 760, fill=GREY)
    img.save(OUT / "ui56-learn.png")

    # 5.7 Value
    img = backdrop((1920, 1080), "#10168A", "#060A4A")
    d = ImageDraw.Draw(img)
    d.text((960, 170), "Tested on the challenge data, with the organisers' scorer", font=font(36, "medium"), fill="#C9CDF5", anchor="mm")
    for i, (big, small) in enumerate([("74%", "of search views at risk\nprotected"), ("87%", "of closed-door visits\nprevented")]):
        x = 560 + i * 800
        d.text((x, 420), big, font=font(190, "bold"), fill="white", anchor="mm")
        for k, line in enumerate(small.split("\n")):
            d.text((x, 590 + k * 54), line, font=font(40, "medium"), fill="#E4E7FF", anchor="mm")
    d.text((960, 860), "Next, on the same loop:  review replies  ·  posts  ·  seasonal hours", font=font(38, "demi"), fill="white", anchor="mm")
    img.save(OUT / "ui57-value.png")

    # Title
    img = Image.new("RGB", (1920, 1080), "#0B0E2E")
    d = ImageDraw.Draw(img)
    d.text((960, 500), "Connect suggests.", font=font(110, "bold"), fill="white", anchor="mm")
    d.text((960, 640), "The owner decides.", font=font(110, "bold"), fill="#AEB5FF", anchor="mm")
    img.save(OUT / "title.png")
    print(f"wrote {len(list(OUT.glob('*.png')))} screens to {OUT}")


if __name__ == "__main__":
    main()
