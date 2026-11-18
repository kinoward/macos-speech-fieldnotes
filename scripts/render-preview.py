"""Render the silent, scripted README illustration with Pillow and macOS fonts."""
import math
from pathlib import Path
import random

from PIL import Image, ImageDraw, ImageFont

ASSETS = Path(__file__).resolve().parents[1] / "docs/assets"
FONTS = Path("/System/Library/Fonts")
INK = "#e5ede7"
MUTED = "#a5b8b5"
MINT = "#95e6c3"
GOLD = "#ffcb8f"
BG = "#102126"
PANEL = "#152c30"
BORDER = "#385457"


def font(file, size, index=0):
    return ImageFont.truetype(str(FONTS / file), size=size, index=index)


TITLE = font("Avenir Next.ttc", 54, 2)
SUBTITLE = font("Avenir Next.ttc", 29, 2)
BODY = font("Avenir Next.ttc", 28, 5)
LABEL = font("Menlo.ttc", 14)
ZH = font("STHeiti Medium.ttc", 30, 1)
CAPTION = font("STHeiti Medium.ttc", 26, 1)
WIDTH, HEIGHT = 1120, 532
CARD_W, CARD_H = 511, 270
LEFT, RIGHT, TOP = 36, 573, 125
PHRASE = "夜空中有一颗星星。"
STATES = [
    ("夜空中", ["In the night sky"], False),
    ("夜空中有一颗", ["There is one…"], False),
    ("夜空中有一颗星", ["There is a star", "in the night sky."], False),
    (PHRASE, ["There is a star", "in the night sky."], True),
]


def landscape():
    width, height = CARD_W - 4, CARD_H - 57
    sky = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(sky)
    for row in range(height):
        mix = row / height
        draw.line((0, row, width, row), fill=(int(27 + 26 * mix), int(49 + 38 * mix), int(66 + 27 * mix)))
    rng = random.Random(16)
    for _ in range(75):
        x, y = rng.randrange(width), rng.randrange(95)
        draw.point((x, y), fill=rng.choice(["#e9dfcd", "#8eb2bb", "#a7c4c4"]))
    draw.ellipse((346, 22, 404, 80), fill="#fce2b6")
    draw.ellipse((358, 14, 414, 70), fill="#213a4c")
    for ridge, shade, grain in [(101, "#536f77", 22), (122, "#36545f", 25), (151, "#233f48", 16)]:
        points = [(0, height)]
        for x in range(-1, width + 14, 12):
            y = ridge + 12 * math.sin(x / 76 + ridge) + 13 * math.sin(x / 43 - ridge) + rng.randrange(grain)
            points.append((x, y))
        draw.polygon(points + [(width, height)], fill=shade)
    return sky


SCENE = landscape()


def label(draw, xy, text, color=MUTED):
    draw.text(xy, text, font=LABEL, fill=color, anchor="lm")


def card(is_live, stage):
    title = "Live translation" if is_live else "Video captions"
    accent = MINT if is_live else GOLD
    canvas = Image.new("RGB", (CARD_W, CARD_H), BG)
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((0, 0, CARD_W - 1, CARD_H - 1), radius=15, fill=PANEL, outline=BORDER, width=2)
    draw.rounded_rectangle((18, 21, 22, 38), radius=2, fill=accent)
    draw.text((34, 29), title, font=SUBTITLE, fill=INK, anchor="lm")
    label(draw, (CARD_W - 108, 29), "ZH → EN" if is_live else "H.265", accent)
    draw.line((1, 55, CARD_W - 2, 55), fill=BORDER)
    if not is_live:
        canvas.paste(SCENE, (2, 56))
        draw.text((CARD_W / 2, CARD_H - 32), PHRASE, font=CAPTION, fill="white", stroke_width=2,
                  stroke_fill="#18262d", anchor="mm")
        return canvas
    zh, english, final = STATES[stage]
    label(draw, (20, 83), "ZH", MINT)
    label(draw, (CARD_W - 101, 83), "FINAL" if final else "DRAFT", MINT if final else GOLD)
    draw.text((20, 118), zh, font=ZH, fill=INK, anchor="lm")
    draw.line((20, 151, CARD_W - 20, 151), fill=BORDER)
    label(draw, (20, 177), "EN", MINT)
    for number, line in enumerate(english):
        draw.text((20, 210 + number * 31), line, font=BODY, fill=INK, anchor="lm")
    return canvas


def wave(draw, left, right, middle, progress):
    for x in range(left, right, 6):
        pos = (x - left) / (right - left)
        envelope = sum(amp * math.exp(-((pos - center) / spread) ** 2) for center, spread, amp in
                       [(0.12, 0.07, 0.7), (0.37, 0.08, 1.0), (0.61, 0.10, 0.65), (0.80, 0.07, 0.85)])
        level = 2 + round(16 * envelope * (0.28 + 0.72 * abs(math.sin(x * 0.42))))
        draw.rounded_rectangle((x, middle - level, x + 2, middle + level), 1,
                               fill=MINT if pos <= progress else "#476063")
    playhead = round(left + (right - left) * progress)
    draw.line((playhead, middle - 27, playhead, middle + 27), fill=GOLD, width=2)


def frame(stage, progress, mobile=False):
    width, height = (545, 775) if mobile else (WIDTH, HEIGHT)
    image = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(image)
    margin = 17 if mobile else LEFT
    label(draw, (margin, 23 if mobile else 29), "macOS   /   APPLE SPEECH", MINT)
    draw.text((margin, 66 if mobile else 78), "Speech field notes", font=TITLE, fill=INK, anchor="lm")
    if not mobile:
        label(draw, (RIGHT + 223, 79), "MANDARIN   •   ON DEVICE")
    top = 110 if mobile else TOP
    image.paste(card(False, stage), (margin, top))
    image.paste(card(True, stage), (margin if mobile else RIGHT, top + (CARD_H + 15 if mobile else 0)))
    bottom = top + CARD_H + (CARD_H + 15 if mobile else 0)
    label(draw, (margin, bottom + 34), "AUDIO INPUT")
    wave(draw, margin, width - margin - 1, bottom + 78, progress)
    return image


def main():
    ASSETS.mkdir(parents=True, exist_ok=True)
    frame(3, 0.95).save(ASSETS / "preview.png", optimize=True)
    frame(3, 0.95, mobile=True).save(ASSETS / "preview-mobile.png", optimize=True)
    frames = [frame(min(number // 5, 3), 0.06 + 0.88 * number / 19) for number in range(20)]
    palette = frames[-1].quantize(colors=180)
    frames = [image.quantize(palette=palette, dither=Image.Dither.NONE) for image in frames]
    frames[0].save(ASSETS / "preview.gif", save_all=True, append_images=frames[1:],
                   duration=[180] * 19 + [2000], loop=0, optimize=True, disposal=1)


if __name__ == "__main__":
    main()
