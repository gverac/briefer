"""Printer backend factory.

All hardware access goes through `make_printer()`, which returns a
python-escpos device. Keeping this behind one function means the rest of the
app talks to a single interface (the escpos `Escpos` API) and can run against
the `dummy` backend on a laptop with no printer attached.

escpos is imported lazily so that `config` and tests stay importable even if
the native USB libs aren't present.
"""

from __future__ import annotations

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
