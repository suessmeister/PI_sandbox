"""Render payload text in a readable panel below the base image."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def payload_font() -> ImageFont.FreeTypeFont:
    # Pillow's default font renders superscripts and dashes as missing glyphs.
    for name in (
        "DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ):
        try:
            return ImageFont.truetype(name, size=24)
        except OSError:
            continue
    raise RuntimeError("Install DejaVu Sans or Arial to render game formulas correctly.")


def render_payload(base_image: Path, payload: str, output: Path) -> Path:
    if not payload.strip():
        raise ValueError("Payload must not be empty.")
    font = payload_font()
    with Image.open(base_image) as source:
        base = source.convert("RGB")
    width, margin = max(base.width, 800), 24
    measure = ImageDraw.Draw(base)
    lines = []
    for paragraph in payload.split("\n"):
        line = ""
        for character in paragraph:
            if line and measure.textlength(line + character, font=font) > width - 2 * margin:
                # Prefer a word boundary; split only tokens wider than the panel.
                boundary = line.rfind(" ")
                if boundary > 0:
                    lines.append(line[:boundary])
                    line = line[boundary + 1:]
                else:
                    lines.append(line)
                    line = ""
            line += character
        lines.append(line)
    canvas = Image.new("RGB", (width, base.height + 2 * margin + 34 * len(lines)), "white")
    canvas.paste(base, ((width - base.width) // 2, 0))
    draw = ImageDraw.Draw(canvas)
    for index, line in enumerate(lines):
        draw.text((margin, base.height + margin + 34 * index), line, font=font, fill="black")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as handle:
        canvas.save(handle, format="PNG")
    return output
