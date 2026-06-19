"""Persist the most recently printed brief so it can be reprinted on demand.

The physical button's single-tap action reprints the last brief *without*
rebuilding it — no network, no AI, instant — which is handy when a print is
smudged, jams, or someone wants a second copy. We do this by saving the exact
rendered bitmap to disk after each brief print and re-sending it later.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .printer import open_printer, send_image

log = logging.getLogger("daily_brief.lastbrief")

# Sits alongside the HTTP/Claude TTL cache (~/.cache/daily_brief/).
LAST_BRIEF_PATH = Path.home() / ".cache" / "daily_brief" / "last_brief.png"


def save(image) -> None:
    """Store `image` as the last printed brief (best-effort; never raises)."""
    try:
        LAST_BRIEF_PATH.parent.mkdir(parents=True, exist_ok=True)
        image.save(LAST_BRIEF_PATH)
    except Exception as exc:
        log.warning("could not save last brief: %s", exc)


def print_and_save(cfg, brief):
    """Print a built `Brief` and record it as the last brief (for reprinting).

    The single entry point every brief-print path should use, so the button's
    reprint always has the latest brief — whether it was fired by the scheduler,
    the CLI, or the web console's "Print now".
    """
    from .render import render_brief

    with open_printer(cfg.printer) as printer:
        image = render_brief(printer, brief, cfg.render, printer_cfg=cfg.printer)
    save(image)
    return image


def reprint(cfg) -> bool:
    """Reprint the last saved brief. Returns False if there's none, or on error."""
    from PIL import Image

    if not LAST_BRIEF_PATH.is_file():
        log.warning("no saved brief to reprint")
        return False
    try:
        with Image.open(LAST_BRIEF_PATH) as image, open_printer(cfg.printer) as printer:
            send_image(printer, image, cfg.printer)
        return True
    except Exception as exc:
        log.error("reprint failed: %s", exc)
        return False
