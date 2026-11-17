"""Compose the storyboard figures from captured screens: docs/storyboard_<n>.png, one image per storyboard.

    py -3.11 tools/make_storyboards.py            after: node tools/capture.mjs --stories

Every frame is a real screen of the running prototype, captured by tools/capture.mjs. All frames share one
size, so a whole storyboard fits on one report page: a shorter card sits at the top of its frame, and
tools/capture.mjs records what may be left out at a marked cut (on a review card the When / Only if / Then
rows after the first, which the sentence below them restates; on a reopened question its scene). The title
gives the request and the person's goal. Labels are short on purpose: who acts and what the system does
in response. Explanations belong in the report text. Storyboard 2 ends with a zoom row: the review card's
lines about leaving home in frames 3 and 5, outlined in both places, so the change after Back is legible.
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
    ], [   # zoom row: (frame number, marks to show, label)
        (3, ["never", "leave"], "Zoom of frame 3: after Not sure, leaving keeps the light on"),
        (5, ["lastrule", "leave"], "Zoom of frame 5: after Back, Yes and Add, it turns off"),
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
MARK = "#f2a900"                               # outline of what the zoom row magnifies
ZOOM_LABEL_H, ZOOM_GAP, ARROW_W, ZOOM_MAX_H = 46, 12, 70, 200


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


class Frame:
    """One screen, with the parts capture.mjs marked as repeated cut out at a marked band.

    image is the frame at storyboard size; full is the same at screen resolution, for the zoom row;
    box(name) gives a recorded mark as (x0, y0, x1, y1) in full-resolution px after the cut."""

    def __init__(self, file, meta):
        im = Image.open(SCREENS / file).convert("RGB")
        self.info = meta[file]
        self.scale = im.height / self.info["height"]     # screen px per CSS px (2 at the capture's device scale)
        cut = self.cut = self.info.get("elide")
        if cut:
            top = im.crop((0, 0, im.width, round(cut["from"] * self.scale)))
            bottom = im.crop((0, round(cut["to"] * self.scale), im.width, im.height))
            band = cut_band(im.width, round(CUT_CSS * self.scale), background(im), self.scale,
                            cut.get("note", "more When / Only if / Then rows left out here"))
            joined = Image.new("RGB", (im.width, top.height + band.height + bottom.height))
            for part, y in ((top, 0), (band, top.height), (bottom, top.height + band.height)):
                joined.paste(part, (0, y))
            im = joined
        self.full = im
        self.ratio = FRAME_W / im.width
        self.image = im.resize((FRAME_W, round(im.height * self.ratio)), Image.LANCZOS)

    def _y(self, css):
        cut = self.cut
        if cut and css >= cut["to"]:
            return (css - cut["to"] + cut["from"] + CUT_CSS) * self.scale
        return css * self.scale

    def box(self, name, pad=4):
        m = self.info["marks"][name]
        return (round((m["x"] - pad) * self.scale), round(self._y(m["y"] - pad)),
                round((m["x"] + m["w"] + pad) * self.scale), round(self._y(m["y"] + m["h"] + pad)))


def fit(draw, text, name, size, width):
    """The largest font size, at most `size`, that keeps the text within `width`."""
    while size > 12 and draw.textlength(text, font=font(name, size)) > width:
        size -= 1
    return font(name, size)


def zoom_panels(frames, zoom, panel_w):
    """For each zoomed frame: its marked parts at screen resolution, stacked, each outlined, fitted to panel_w."""
    panels = []
    for number, names, label in zoom:
        frame = frames[number - 1][0]
        pieces = [frame.full.crop(frame.box(n)) for n in names]
        width = max(p.width for p in pieces)
        stack = Image.new("RGB", (width, sum(p.height for p in pieces) + ZOOM_GAP * (len(pieces) - 1)),
                          background(frame.full))
        draw, y = ImageDraw.Draw(stack), 0
        for piece in pieces:
            stack.paste(piece, (0, y))
            draw.rectangle([1, y + 1, piece.width - 2, y + piece.height - 2], outline=MARK, width=4)
            y += piece.height + ZOOM_GAP
        factor = min(1.0, panel_w / stack.width, ZOOM_MAX_H / stack.height)
        panels.append((stack.resize((round(stack.width * factor), round(stack.height * factor)), Image.LANCZOS),
                       label))
    return panels


def compose(name, title, requests, goal, frames, frame_h, zoom=None):
    rows = -(-len(frames) // COLS)
    width = MARGIN * 2 + COLS * FRAME_W + (COLS - 1) * GAP_X
    height = MARGIN + TITLE_H + rows * (LABEL_H + frame_h) + (rows - 1) * GAP_Y + MARGIN
    panels = zoom_panels(frames, zoom, (width - 2 * MARGIN - ARROW_W) // 2) if zoom else []
    zoom_top = height - MARGIN + GAP_Y
    if panels:
        height = zoom_top + ZOOM_LABEL_H + max(p.height for p, _ in panels) + MARGIN
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
        screen = Image.new("RGB", (FRAME_W, frame_h), background(im.image))
        screen.paste(im.image, (0, 0))
        for number, names, _ in (zoom or []):        # outline, in the frame, what the zoom row magnifies
            if number == n:
                outline = ImageDraw.Draw(screen)
                for mark in names:
                    x0, y0, x1, y1 = (round(v * im.ratio) for v in im.box(mark))
                    outline.rectangle([x0, y0, x1, y1], outline=MARK, width=3)
        canvas.paste(screen, (x, y + LABEL_H), mask)
    if panels:
        panel_w = (width - 2 * MARGIN - ARROW_W) // 2
        for i, (panel, label) in enumerate(panels):
            x = MARGIN + i * (panel_w + ARROW_W)
            draw.text((x, zoom_top + 21), label, font=fit(draw, label, "segoeui.ttf", 23, panel_w), fill=INK, anchor="lm")
            canvas.paste(panel, (x, zoom_top + ZOOM_LABEL_H))
        draw.text((MARGIN + panel_w + ARROW_W // 2, zoom_top + ZOOM_LABEL_H + max(p.height for p, _ in panels) // 2),
                  "→", font=font("segoeuib.ttf", 44), fill=INK, anchor="mm")
    out = ROOT / "docs" / f"{name}.png"
    canvas.save(out, optimize=True)
    print(f"wrote {out.relative_to(ROOT)} ({canvas.width}x{canvas.height}, frames {FRAME_W}x{frame_h})")


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    meta = json.loads((SCREENS / "frames.json").read_text(encoding="utf-8"))
    loaded = {}
    for name, (_, _, _, frames, *_) in STORIES.items():
        missing = [f for f, _ in frames if not (SCREENS / f).exists() or f not in meta]
        if missing:
            sys.exit(f"{name}: missing {', '.join(missing)} (run node tools/capture.mjs --stories first)")
        loaded[name] = [(Frame(f, meta), label) for f, label in frames]
    # One frame height for every storyboard, so the figures match each other too.
    frame_h = max(im.image.height for frames in loaded.values() for im, _ in frames)
    for name, (title, requests, goal, _, *zoom) in STORIES.items():
        if not only or only == name:
            compose(name, title, requests, goal, loaded[name], frame_h, zoom[0] if zoom else None)


if __name__ == "__main__":
    main()
