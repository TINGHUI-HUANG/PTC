"""Compose the storyboard figures from captured screens: docs/storyboard_<n>.png, one image per storyboard.

    py -3.11 tools/make_storyboards.py            after: node tools/capture.mjs --stories

Every frame is a real screen of the running prototype, captured by tools/capture.mjs. All frames share one
size, so a whole storyboard fits on one report page: a shorter card sits at the top of its frame, and
tools/capture.mjs records what may be left out at a marked cut (on a review card the When / Only if / Then
rows after the first, which the sentence below them restates; on a reopened question its scene). The title
gives the request and the person's goal. Labels are short on purpose: who acts and what the system does
in response. Explanations belong in the report text.
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
SCREENS = ROOT / "docs" / "screens"
FONTS = Path("C:/Windows/Fonts")
REQUESTS = {r["id"]: r["text"] for r in json.loads((ROOT / "data" / "requests.json").read_text(encoding="utf-8"))["requests"]}

# title, requests, the person's goal, then (screen, label). A label names who acts: the person's action,
# then the system's response (Lecture 06: mark each storyboard frame with who acts).
STORIES = {
    "storyboard_1": ("Storyboard 1 · Three readings narrowed, then an error all three share", ["B"],
                     "Goal: the light on whenever I am home after dark, and off when I leave.", [
        ("s1_1.png", "Person picks a sentence; scope shown"),
        ("s1_2.png", "System asks where 3 readings differ"),
        ("s1_3.png", "Person: Yes, Yes → System probes leaving"),
        ("s1_4.png", "Person: Yes → System proposes a rule"),
        ("s1_5.png", "Person: Add → System restates the rule"),
        ("s1_6.png", "Person: Save → stored only now"),
    ]),
    "storyboard_2": ("Storyboard 2 · No, Not sure, then Back and Revisit", ["E"],
                     "Goal: the light on when I am home after dark; unsure at first whether leaving should turn it off.", [
        ("s2_1.png", "System asks where 2 readings differ"),
        ("s2_2.png", "Person: No → System probes arriving"),
        ("s2_3.png", "Person: Yes, Add, Not sure → gap stated"),
        ("s2_4.png", "Person: Back, Yes → System proposes"),
        ("s2_5.png", "Person: Add → review has no gap"),
        ("s2_6.png", "Person reopens Q1 → answers kept"),
    ]),
    "storyboard_3": ("Storyboard 3 · A decline, then one reading: probes ask, the answer decides", ["F", "C"],
                     "Goal: lock the door (not supported); then the light on at home after dark, left on when I go out.", [
        ("s3_1.png", "Person asks for a door lock → declined"),
        ("s3_2.png", "Person edits to C → System probes"),
        ("s3_3.png", "Person: Yes → System proposes a rule"),
        ("s3_4.png", "Person: Add → System probes leaving"),
        ("s3_5.png", "Person: No → review: never off"),
        ("s3_6.png", "Person: Save → saved as answered"),
    ]),
}

COLS, FRAME_W, MARGIN, GAP_X, GAP_Y, TITLE_H, LABEL_H, RADIUS = 3, 500, 24, 24, 28, 136, 50, 16
CUT_CSS = 36                                   # height of the marked cut, in CSS px of the screen
BG, INK, MUTED, ACCENT = "#ffffff", "#1f2328", "#57606a", "#1f5fbf"


def font(name, size):
    for candidate in (name, "arial.ttf"):
        path = FONTS / candidate
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def background(im):
    """The page colour around the card: the most common colour of the screen's bottom rows."""
    strip = im.crop((0, im.height - 4, im.width, im.height)).getcolors(im.width * 4)
    return max(strip)[1]


def cut_band(width, height, fill, scale, note):
    """The marked cut: dashed edges and a short note, on the page colour."""
    band = Image.new("RGB", (width, height), fill)
    draw = ImageDraw.Draw(band)
    line, dash = (120, 134, 126), round(8 * scale)
    for y in (round(3 * scale), height - round(3 * scale) - 1):
        for x in range(0, width, dash * 2):
            draw.line([(x, y), (x + dash, y)], fill=line, width=max(1, round(scale)))
    draw.text((width // 2, height // 2), note,
              font=font("segoeuisl.ttf", round(13 * scale)), fill=(170, 182, 175), anchor="mm")
    return band


def load(file, meta):
    """One screen, with the review card's repeated rule rows cut out where capture.mjs recorded them."""
    im = Image.open(SCREENS / file).convert("RGB")
    info = meta[file]
    scale = im.height / info["height"]          # screen px per CSS px (2 at the capture's device scale)
    cut = info.get("elide")
    if cut:
        top = im.crop((0, 0, im.width, round(cut["from"] * scale)))
        bottom = im.crop((0, round(cut["to"] * scale), im.width, im.height))
        band = cut_band(im.width, round(CUT_CSS * scale), background(im), scale,
                        cut.get("note", "more When / Only if / Then rows left out here"))
        joined = Image.new("RGB", (im.width, top.height + band.height + bottom.height))
        for part, y in ((top, 0), (band, top.height), (bottom, top.height + band.height)):
            joined.paste(part, (0, y))
        im = joined
    return im.resize((FRAME_W, round(im.height * FRAME_W / im.width)), Image.LANCZOS)


def fit(draw, text, name, size, width):
    """The largest font size, at most `size`, that keeps the text within `width`."""
    while size > 12 and draw.textlength(text, font=font(name, size)) > width:
        size -= 1
    return font(name, size)


def compose(name, title, requests, goal, frames, frame_h):
    rows = -(-len(frames) // COLS)
    width = MARGIN * 2 + COLS * FRAME_W + (COLS - 1) * GAP_X
    height = MARGIN + TITLE_H + rows * (LABEL_H + frame_h) + (rows - 1) * GAP_Y + MARGIN
    canvas = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(canvas)
    text_w = width - 2 * MARGIN
    draw.text((MARGIN, MARGIN), title, font=fit(draw, title, "segoeuib.ttf", 34, text_w), fill=INK)
    quoted = "    ".join(f"Request {r}: “{REQUESTS[r]}”" for r in requests)
    draw.text((MARGIN, MARGIN + 52), quoted, font=fit(draw, quoted, "segoeui.ttf", 25, text_w), fill=MUTED)
    draw.text((MARGIN, MARGIN + 88), goal, font=fit(draw, goal, "segoeui.ttf", 25, text_w), fill=MUTED)
    mask = Image.new("L", (FRAME_W, frame_h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, FRAME_W - 1, frame_h - 1], radius=RADIUS, fill=255)
    number_font = font("segoeuib.ttf", 22)
    for n, (im, label) in enumerate(frames, 1):
        r, c = divmod(n - 1, COLS)
        x = MARGIN + c * (FRAME_W + GAP_X)
        y = MARGIN + TITLE_H + r * (LABEL_H + frame_h + GAP_Y)
        draw.ellipse([x, y + 6, x + 34, y + 40], fill=ACCENT)
        draw.text((x + 17, y + 23), str(n), font=number_font, fill="#ffffff", anchor="mm")
        draw.text((x + 44, y + 23), label, font=fit(draw, label, "segoeui.ttf", 25, FRAME_W - 44), fill=INK,
                  anchor="lm")
        screen = Image.new("RGB", (FRAME_W, frame_h), background(im))
        screen.paste(im, (0, 0))
        canvas.paste(screen, (x, y + LABEL_H), mask)
    out = ROOT / "docs" / f"{name}.png"
    canvas.save(out, optimize=True)
    print(f"wrote {out.relative_to(ROOT)} ({canvas.width}x{canvas.height}, frames {FRAME_W}x{frame_h})")


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    meta = json.loads((SCREENS / "frames.json").read_text(encoding="utf-8"))
    loaded = {}
    for name, (_, _, _, frames) in STORIES.items():
        missing = [f for f, _ in frames if not (SCREENS / f).exists() or f not in meta]
        if missing:
            sys.exit(f"{name}: missing {', '.join(missing)} (run node tools/capture.mjs --stories first)")
        loaded[name] = [(load(f, meta), label) for f, label in frames]
    # One frame height for every storyboard, so the figures match each other too.
    frame_h = max(im.height for frames in loaded.values() for im, _ in frames)
    for name, (title, requests, goal, _) in STORIES.items():
        if not only or only == name:
            compose(name, title, requests, goal, loaded[name], frame_h)


if __name__ == "__main__":
    main()
