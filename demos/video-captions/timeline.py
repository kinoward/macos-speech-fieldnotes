import math
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SYSTEM_FONT = Path("/System/Library/Fonts/STHeiti Medium.ttc")
UNITS = re.compile(r"[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)*|.", re.DOTALL)
TERMINAL = "。！？!?；;"
CLOSING = "。，、！？；：）】》”’!?,.;:)]"


class CaptionLayout:
    def __init__(self, width, height, font_path):
        self.width = width
        self.font_size = max(12, round(height * 0.036))
        self.stroke = max(1, round(self.font_size * 0.068))
        self.margin = max(1, round(height * 0.064))
        self.line_height = round(self.font_size * 1.35)
        self.plate_height = self.line_height * 2 + self.stroke * 4
        self.text_width = width * 0.86
        self.font = ImageFont.truetype(str(font_path or SYSTEM_FONT), self.font_size,
                                       index=0 if font_path else 1)

    def lines(self, text):
        lines = []
        for paragraph in text.splitlines():
            line = ""
            for unit in UNITS.findall(paragraph.strip()):
                if line and self.font.getlength(line + unit) > self.text_width:
                    if unit in CLOSING and len(line) > 1:
                        line, unit = line[:-1], line[-1] + unit
                    if line.strip():
                        lines.append(line.strip())
                    line = ""
                line += unit
            if line.strip():
                lines.append(line.strip())
        return lines

    def render(self, path, text):
        lines = self.lines(text)
        if len(lines) > 2 or any(self.font.getlength(line) > self.text_width for line in lines):
            raise ValueError("A cue does not fit two lines. Shorten it or divide its time range.")
        image = Image.new("RGBA", (self.width, self.plate_height))
        draw = ImageDraw.Draw(image)
        for index, line in enumerate(reversed(lines)):
            baseline = self.plate_height - self.stroke * 2 - self.font_size // 4 - index * self.line_height
            draw.text((self.width / 2, baseline), line, anchor="ms", font=self.font, fill="white",
                      stroke_width=self.stroke, stroke_fill="black")
        image.save(path)


def timed_units(spans):
    word = ""
    for span in spans:
        raw = span["text"]
        trimmed = raw.strip()
        text = trimmed if trimmed and all(char in CLOSING for char in trimmed) else raw
        start, end = span["start"], span["end"]
        for match in UNITS.finditer(text):
            unit = match.group()
            left = start + (end - start) * match.start() / len(text)
            right = start + (end - start) * match.end() / len(text)
            if word and unit in CLOSING:
                word = word.rstrip() + unit
                word_end = right
                held_punctuation |= right - left >= 0.55
            elif word and unit.isspace():
                word += unit
            else:
                if word:
                    yield word, word_start, word_end, held_punctuation
                word, word_start, word_end, held_punctuation = unit, left, right, False
    if word:
        yield word, word_start, word_end, held_punctuation


def make_draft(phrases, layout, offset, duration):
    cues = []
    for spans in phrases:
        text = ""
        start = end = 0
        held_punctuation = False
        for unit, left, right, held in timed_units(spans):
            boundary = (held_punctuation or left - end >= 0.55 or text.rstrip().endswith(tuple(TERMINAL))
                        or right - start > 6 or len(layout.lines(text + unit)) > 2)
            if text.strip() and boundary:
                cues.append({"start": start + offset, "end": end + offset, "text": text.strip()})
                text = ""
            if not text:
                start = left
            end, held_punctuation = right, held
            text += unit
        if text.strip():
            cues.append({"start": start + offset, "end": end + offset, "text": text.strip()})

    normalized = []
    for cue in cues:
        start = max(normalized[-1]["end"] if normalized else 0, round(cue["start"], 3))
        end = min(round(duration, 3), round(cue["end"], 3))
        if end > start:
            normalized.append({"start": start, "end": end, "text": cue["text"]})
        elif normalized:
            normalized[-1]["text"] += cue["text"]
    return normalized


def plates(cues, layout, duration, directory):
    if not isinstance(cues, list):
        raise ValueError("Cues must be a JSON array.")
    layout.render(directory / "blank.png", "")
    entries = ["ffconcat version 1.0"]

    def append(name, milliseconds=None):
        entries.extend([f"file '{name}'", "option framerate 1000"])
        if milliseconds is not None:
            entries.append(f"duration {milliseconds / 1000:.3f}")

    cursor = 0
    for index, cue in enumerate(cues, 1):
        if not isinstance(cue, dict) or not isinstance(cue.get("text"), str) or not cue["text"].strip():
            raise ValueError(f"Cue {index} needs non-empty text.")
        times = [cue.get(key) for key in ("start", "end")]
        if not all(type(value) in (int, float) and math.isfinite(value) for value in times):
            raise ValueError(f"Cue {index} needs finite start and end times in seconds.")
        start, end = (round(value * 1000) for value in times)
        if not (cursor <= start < end <= round(duration * 1000)):
            raise ValueError(f"Cue {index} is reversed, overlapping or outside the media timeline.")
        if start > cursor:
            append("blank.png", start - cursor)
        name = f"cue-{index}.png"
        layout.render(directory / name, cue["text"])
        append(name, end - start)
        cursor = end
    append("blank.png")
    manifest = directory / "plates.ffconcat"
    manifest.write_text("\n".join(entries) + "\n", encoding="utf-8")
    return manifest
