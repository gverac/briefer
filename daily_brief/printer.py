"""Printer backend factory.

All hardware access goes through `make_printer()`, which returns a
python-escpos device. Keeping this behind one function means the rest of the
app talks to a single interface (the escpos `Escpos` API) and can run against
the `dummy` backend on a laptop with no printer attached.

escpos is imported lazily so that `config` and tests stay importable even if
the native USB libs aren't present.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator

from .config import PrinterConfig


def make_printer(cfg: PrinterConfig):
    """Construct a python-escpos device from config.

    Returns an `escpos.escpos.Escpos` subclass instance (Usb / Serial / Dummy).
    The caller is responsible for closing it; prefer `open_printer()` instead.
    """
    backend = cfg.backend.lower()

    if backend == "dummy":
        from escpos.printer import Dummy

        return Dummy(profile=cfg.profile)

    if backend == "usb":
        from escpos.printer import Usb

        kwargs = {}
        if cfg.usb.in_ep is not None:
            kwargs["in_ep"] = cfg.usb.in_ep
        if cfg.usb.out_ep is not None:
            kwargs["out_ep"] = cfg.usb.out_ep
        return Usb(
            idVendor=cfg.usb.vendor_id,
            idProduct=cfg.usb.product_id,
            profile=cfg.profile,
            **kwargs,
        )

    if backend == "serial":
        from escpos.printer import Serial

        return Serial(
            devfile=cfg.serial.port,
            baudrate=cfg.serial.baudrate,
            profile=cfg.profile,
        )

    raise ValueError(
        f"Unknown printer backend {cfg.backend!r}. "
        "Expected one of: dummy, usb, serial."
    )


@contextmanager
def open_printer(cfg: PrinterConfig) -> Iterator:
    """Context manager that builds a printer and closes it on exit."""
    printer = make_printer(cfg)
    try:
        yield printer
    finally:
        close = getattr(printer, "close", None)
        if callable(close):
            close()


# Send the bitmap in short horizontal bands instead of one big raster blob.
# Each band is a self-contained GS v 0 command, so a dropped/late byte can't
# desync the rest of the image into the "row shifted halfway and wrapped to the
# other side" misprint — every band re-declares its width and realigns.
#
# The misprint we actually hit was an *opening-burst overrun*: the host pushes
# the first kilobytes faster than the (slow) thermal head can drain them, the
# printer's input buffer overflows, and bytes are dropped before write-side
# backpressure kicks in — which is why only the first sections were corrupted.
# Two mitigations together fix it: small bands (a smaller burst is less likely
# to overrun, and any single overrun corrupts fewer rows) and a short pause
# between bands so the printer can drain before the next one arrives. Both are
# tunable via [printer] band_height / band_pause; these are the fallbacks for
# when no PrinterConfig is passed (e.g. older callers).
RASTER_FRAGMENT_HEIGHT = 64
BAND_PAUSE_SECONDS = 0.05


def send_image(printer, image, cfg: PrinterConfig | None = None) -> None:
    """Send a rendered bitmap to the printer and cut (feed if no cutter)."""
    band_height = cfg.band_height if cfg else RASTER_FRAGMENT_HEIGHT
    band_pause = cfg.band_pause if cfg else BAND_PAUSE_SECONDS

    try:
        printer.hw("INIT")  # ESC @: clear any stale mode before the image
    except Exception:
        pass

    # Drive the banding ourselves (rather than letting printer.image() split)
    # so we can flush + pause between bands. Each printer.image() call here gets
    # the whole band as one GS v 0 (fragment_height >= band height, so escpos
    # won't split it further).
    height = image.height
    for top in range(0, height, band_height):
        band = image.crop((0, top, image.width, min(top + band_height, height)))
        printer.image(band, impl="bitImageRaster", fragment_height=band.height)
        flush = getattr(printer, "flush", None)
        if callable(flush):
            flush()
        if band_pause > 0:
            time.sleep(band_pause)

    try:
        printer.cut()
    except Exception:
        printer.text("\n\n\n")
