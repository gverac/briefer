"""Image-based rendering of a Brief.

The whole brief is drawn onto one tall bitmap with a modern TrueType font, then
sent to the printer as a raster image. This is what lets us use a non-receipt
font, thin separator rules, birthday checkboxes, and weather pictograms — none
of which the printer's built-in ESC/POS fonts can do.

`render_brief()` works with any escpos backend (including Dummy) and can also
save the bitmap to a PNG for previewing on a laptop with no printer attached.
"""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

from .brief import (
    Banner, Brief, Bullet, Checkbox, KeyVal, Mono, Picture, ProgressBar, Section,
    Text, Title, Weather,
)
from .config import ASSETS_DIR, RenderConfig

SCRATCH_HEIGHT = 8000  # tall scratch canvas; cropped to used height at the end
ICON_SIZE = 84       # weather pictogram
BANNER_ICON = 52     # smaller inline icon (e.g. on-call bell)
DOTS_PER_MM = 8      # vertical print density at 203 dpi (8 dots/mm)


def _pad_to_min_length(image: Image.Image, min_length_mm: int) -> Image.Image:
    """Extend a short bitmap with blank feed up to `min_length_mm`.

    Guarantees enough paper past the tear bar to grab and tear cleanly. Returns
    the image unchanged when padding is disabled (<= 0) or already long enough.
    """
    if min_length_mm <= 0:
        return image
    min_h = min_length_mm * DOTS_PER_MM
    if image.height >= min_h:
        return image
    padded = Image.new("L", (image.width, min_h), 255)
    padded.paste(image, (0, 0))
    return padded


@lru_cache(maxsize=64)
def _load_icon(category: str, key: str, size: int) -> Image.Image | None:
    path = ASSETS_DIR / category / f"{key}.png"
    if not path.is_file():
        return None
    icon = Image.open(path).convert("L")
    if icon.size != (size, size):
        icon = icon.resize((size, size), Image.LANCZOS)
    return icon


class Canvas:
    """A fixed-width drawing surface with a downward-moving y cursor."""

    def __init__(self, cfg: RenderConfig):
        self.W = cfg.dot_width
        self.margin = cfg.margin
        self.x0 = cfg.margin
        self.x1 = cfg.dot_width - cfg.margin
        self.content_w = self.x1 - self.x0

        reg, bold = cfg.resolve_font(False), cfg.resolve_font(True)
        self.bold_path = bold
        self.title_size = cfg.heading_size + 8
        self.f_title = ImageFont.truetype(bold, self.title_size)
        self.f_head = ImageFont.truetype(bold, cfg.heading_size)
        self.f_big = ImageFont.truetype(bold, cfg.heading_size + 4)
        self.f_bold = ImageFont.truetype(bold, cfg.body_size)
        self.f_body = ImageFont.truetype(reg, cfg.body_size)
        self.mono_path = cfg.resolve_mono()
        self.format_temp = cfg.format_temp  # honors the configured °C/°F unit

        self.img = Image.new("L", (self.W, SCRATCH_HEIGHT), 255)
        self.draw = ImageDraw.Draw(self.img)
        self.y = 0

    # --- low-level helpers -------------------------------------------------

    @staticmethod
    def _line_height(font: ImageFont.FreeTypeFont, leading: int = 3) -> int:
        asc, desc = font.getmetrics()
        return asc + desc + leading

    def _wrap(self, text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
        lines, cur = [], ""
        for word in text.split():
            trial = word if not cur else f"{cur} {word}"
            if not cur or font.getlength(trial) <= max_w:
                cur = trial
            else:
                lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)
        return lines or [""]

    def _draw_block(self, text: str, font: ImageFont.FreeTypeFont, x: int) -> None:
        lh = self._line_height(font)
        for line in self._wrap(text, font, self.x1 - x):
            self.draw.text((x, self.y), line, font=font, fill=0)
            self.y += lh

    def _center(self, text: str, font: ImageFont.FreeTypeFont) -> None:
        w = font.getlength(text)
        self.draw.text(((self.W - w) // 2, self.y), text, font=font, fill=0)
        self.y += self._line_height(font)

    def _center_fit(self, text: str, path: str, size: int, min_size: int = 18) -> None:
        """Center text, shrinking the font until it fits the content width."""
        font = ImageFont.truetype(path, size)
        while size > min_size and font.getlength(text) > self.content_w:
            size -= 1
            font = ImageFont.truetype(path, size)
        self._center(text, font)

    def spacer(self, h: int) -> None:
        self.y += h

    def rule(self, weight: int = 2, pad: int = 7) -> None:
        self.y += pad
        self.draw.rectangle([self.x0, self.y, self.x1, self.y + weight - 1], fill=0)
        self.y += weight + pad

    # --- item renderers ----------------------------------------------------

    def heading(self, title: str, icon_key: str | None = None) -> None:
        asc, _ = self.f_head.getmetrics()
        size = asc  # match icon height to the cap height of the heading
        text_x = self.x0
        icon = _load_icon("icons", icon_key, size) if icon_key else None
        if icon is not None:
            self.img.paste(icon, (self.x0, self.y + 1))
            text_x = self.x0 + size + 8
        self.draw.text((text_x, self.y), title.upper(), font=self.f_head, fill=0)
        self.y += self._line_height(self.f_head, leading=5)

    def text(self, text: str) -> None:
        self._draw_block(text, self.f_body, self.x0)

    def bullet(self, text: str) -> None:
        dash = "-"
        x_text = self.x0 + int(self.f_body.getlength(dash + " "))
        self.draw.text((self.x0, self.y), dash, font=self.f_body, fill=0)
        self._draw_block(text, self.f_body, x_text)  # hanging indent for wraps

    def banner(self, text: str, icon_key: str | None = None) -> None:
        start_y = self.y
        text_x = self.x0
        icon = _load_icon("icons", icon_key, BANNER_ICON) if icon_key else None
        if icon is not None:
            self.img.paste(icon, (self.x0, start_y))
            text_x = self.x0 + BANNER_ICON + 12

        lines = self._wrap(text, self.f_bold, self.x1 - text_x)
        lh = self._line_height(self.f_bold)
        icon_h = BANNER_ICON if icon is not None else 0
        # Vertically center the text block against the icon.
        ty = start_y + max(0, (icon_h - lh * len(lines)) // 2)
        for line in lines:
            self.draw.text((text_x, ty), line, font=self.f_bold, fill=0)
            ty += lh
        self.y = max(start_y + icon_h, ty)

    def checkbox(self, label: str, checked: bool = False) -> None:
        lh = self._line_height(self.f_body)
        asc, _ = self.f_body.getmetrics()
        box = int(asc * 0.85)
        top = self.y + (lh - box) // 2 - 1
        self.draw.rectangle([self.x0, top, self.x0 + box, top + box], outline=0, width=2)
        if checked:
            self.draw.line(
                [self.x0 + 3, top + box // 2, self.x0 + box // 2, top + box - 3], fill=0, width=2
            )
            self.draw.line(
                [self.x0 + box // 2, top + box - 3, self.x0 + box - 2, top + 2], fill=0, width=2
            )
        self._draw_block(label, self.f_body, self.x0 + box + 12)

    def keyval(self, label: str, value: str) -> None:
        lh = self._line_height(self.f_body)
        self.draw.text((self.x0, self.y), label, font=self.f_bold, fill=0)
        vw = self.f_body.getlength(value)
        self.draw.text((self.x1 - vw, self.y), value, font=self.f_body, fill=0)
        self.y += lh

    def weather(self, item: Weather) -> None:
        start_y = self.y
        icon = _load_icon("weather", item.icon_key, ICON_SIZE)
        text_x = self.x0
        if icon is not None:
            self.img.paste(icon, (self.x0, start_y))
            text_x = self.x0 + ICON_SIZE + 14

        temp = f"H {self.format_temp(item.hi)}   L {self.format_temp(item.lo)}"

        self.y = start_y + 8
        self.draw.text((text_x, self.y), temp, font=self.f_big, fill=0)
        self.y += self._line_height(self.f_big, leading=4)
        if item.desc:
            self._draw_block(item.desc, self.f_body, text_x)

        self.y = max(self.y, start_y + ICON_SIZE)

    def mono(self, text: str, max_size: int = 18, min_size: int = 8) -> None:
        """Draw monospace text (ASCII art), shrinking to fit the widest line."""
        lines = text.strip("\n").split("\n")
        width_chars = max((len(line) for line in lines), default=0)
        if width_chars == 0:
            return
        size = max_size
        font = ImageFont.truetype(self.mono_path, size)
        while size > min_size and font.getlength("M" * width_chars) > self.content_w:
            size -= 1
            font = ImageFont.truetype(self.mono_path, size)
        lh = self._line_height(font, leading=1)
        for line in lines:
            self.draw.text((self.x0, self.y), line, font=font, fill=0)
            self.y += lh

    def progress(self, fraction: float, height: int = 16) -> None:
        """Draw a full-width progress bar filled to `fraction` (clamped 0..1)."""
        fraction = max(0.0, min(1.0, fraction))
        top = self.y
        self.draw.rectangle([self.x0, top, self.x1, top + height], outline=0, width=2)
        inner = round((self.x1 - self.x0 - 4) * fraction)
        if inner > 0:
            self.draw.rectangle(
                [self.x0 + 2, top + 2, self.x0 + 2 + inner, top + height - 2], fill=0
            )
        self.y += height + 2

    def picture(self, image) -> None:
        img = image.convert("L") if image.mode != "L" else image
        if img.width > self.content_w:
            h = round(img.height * self.content_w / img.width)
            img = img.resize((self.content_w, h), Image.LANCZOS)
        x = (self.W - img.width) // 2
        self.img.paste(img, (x, self.y))
        self.y += img.height

    def title(self, text: str, subtitle: str = "") -> None:
        """Big centered greeting + centered subtitle (the brief header look)."""
        self._center_fit(text, self.bold_path, self.title_size)
        if subtitle:
            self.spacer(2)
            self._center(subtitle, self.f_body)

    # --- composition -------------------------------------------------------

    def _draw_item(self, item) -> None:
        if isinstance(item, Text):
            self.text(item.text)
        elif isinstance(item, Checkbox):
            self.checkbox(item.label, item.checked)
        elif isinstance(item, Bullet):
            self.bullet(item.text)
        elif isinstance(item, Banner):
            self.banner(item.text, item.icon_key)
        elif isinstance(item, KeyVal):
            self.keyval(item.label, item.value)
        elif isinstance(item, Weather):
            self.weather(item)
        elif isinstance(item, Picture):
            self.picture(item.image)
        elif isinstance(item, ProgressBar):
            self.progress(item.fraction)
        elif isinstance(item, Mono):
            self.mono(item.text)
        elif isinstance(item, Title):
            self.title(item.text, item.subtitle)

    def section(self, section: Section) -> None:
        # A "bare" section (e.g. the greeting) renders its items with no
        # separator rule or heading — just the centered title block.
        if section.bare:
            for item in section.items:
                self._draw_item(item)
            self.spacer(4)
            return
        self.rule()
        self.heading(section.title, section.icon)
        for item in section.items:
            self._draw_item(item)
            self.spacer(2)

    def footer(self) -> None:
        self.rule()
        self._center("have a good day", self.f_body)
        self.spacer(24)  # feed before the cut

    def finish(self) -> Image.Image:
        return self.img.crop((0, 0, self.W, self.y))


def render_brief(printer, brief: Brief, cfg: RenderConfig, preview_path=None,
                 footer: bool = True, printer_cfg=None) -> Image.Image:
    """Render `brief` to an image, print it, and optionally save a PNG preview.

    `printer` may be None (preview only). Returns the rendered PIL image.
    `footer=False` skips the "have a good day" sign-off (used for one-off
    prints like incoming email that aren't a daily brief). `printer_cfg` (a
    `PrinterConfig`) supplies the raster band pacing; if omitted, `send_image`
    falls back to its module defaults.
    """
    canvas = Canvas(cfg)
    canvas.spacer(6)  # small top margin (the greeting is now an ordinary section)
    for section in brief.sections:
        canvas.section(section)
    if footer:
        canvas.footer()
    image = _pad_to_min_length(canvas.finish(), cfg.min_length_mm)

    if preview_path is not None:
        image.save(preview_path)

    if printer is not None:
        from .printer import send_image

        send_image(printer, image, printer_cfg)

    return image
