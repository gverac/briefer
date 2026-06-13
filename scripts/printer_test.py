#!/usr/bin/env python3
"""Printer smoke test for the Daily Brief project.

Run this on the Raspberry Pi (with the printer attached) to confirm the
hardware works before worrying about weather/calendar/etc.

Typical workflow on the Pi
--------------------------
1. Figure out how the printer connects:

       python scripts/printer_test.py --list-usb
       ls -l /dev/ttyUSB* /dev/serial* 2>/dev/null

   - If it shows up in --list-usb with a real vendor:product (NOT 1d6b, which
     is the Pi's internal root hub), it's a raw USB ESC/POS printer. Put those
     IDs in config.toml under [printer.usb] and use --backend usb.
   - If a /dev/ttyUSB0 (or /dev/serial0) appears, it's serial. Set the port in
     config.toml under [printer.serial] and use --backend serial.

2. Print the test page:

       python scripts/printer_test.py --backend usb
       # or
       python scripts/printer_test.py --backend serial

3. No printer yet? See what would be sent, on any machine:

       python scripts/printer_test.py --backend dummy
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running as a plain script (`python scripts/printer_test.py`) by putting
# the repo root on the import path.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from daily_brief.config import load_config  # noqa: E402
from daily_brief.printer import make_printer  # noqa: E402


def list_usb() -> int:
    """Print every USB device so the user can identify the printer's IDs."""
    try:
        import usb.core
    except ImportError:
        print(
            "pyusb is not installed. Install requirements first:\n"
            "    pip install -r requirements.txt",
            file=sys.stderr,
        )
        return 1

    devices = list(usb.core.find(find_all=True))
    if not devices:
        print(
            "No USB devices found. On Linux you may need sudo / a udev rule, "
            "or libusb may be missing (sudo apt install libusb-1.0-0).",
            file=sys.stderr,
        )
        return 1

    print(f"{'idVendor:idProduct':<20} {'bus/addr':<10} description")
    print("-" * 60)
    for dev in devices:
        ids = f"{dev.idVendor:04x}:{dev.idProduct:04x}"
        loc = f"{dev.bus}/{dev.address}"
        try:
            desc = usb.util.get_string(dev, dev.iProduct) or ""
            maker = usb.util.get_string(dev, dev.iManufacturer) or ""
            label = f"{maker} {desc}".strip()
        except Exception:
            label = "(could not read string descriptor; try sudo)"
        note = "  <- root hub, ignore" if dev.idVendor == 0x1D6B else ""
        print(f"{ids:<20} {loc:<10} {label}{note}")

    print(
        "\nThe printer is the line that is NOT a root hub (1d6b). "
        "Copy its idVendor / idProduct into config.toml [printer.usb]."
    )
    return 0


def _make_test_image(dot_width: int = 384):
    """Build a PIL test image that exercises thermal-printer image rendering.

    Sections (top to bottom):
      - Solid black bar       -- check full-width fill
      - Thin horizontal lines -- check fine detail / gaps
      - Diagonal hatching     -- check diagonal rendering
      - Grey gradient         -- check dithering across tones
      - Bold label            -- check text-as-image legibility
      - Solid black bar       -- bookend
    """
    from PIL import Image, ImageDraw, ImageFont

    W = dot_width
    ROW = W // 8   # height of each section

    img = Image.new("L", (W, ROW * 6 + 4), color=255)  # white background
    draw = ImageDraw.Draw(img)

    y = 0

    # Solid black bar
    draw.rectangle([0, y, W - 1, y + ROW - 1], fill=0)
    y += ROW + 2

    # Thin horizontal lines (1px on, 1px off)
    for row in range(ROW):
        if row % 2 == 0:
            draw.line([0, y + row, W - 1, y + row], fill=0)
    y += ROW + 2

    # Diagonal hatching (45°, every 4px)
    for offset in range(0, W + ROW, 4):
        draw.line([offset, y, offset - ROW, y + ROW - 1], fill=0)
    y += ROW

    # Greyscale gradient (dithered by PIL when printed)
    for x in range(W):
        grey = int(x / W * 255)
        draw.line([x, y, x, y + ROW - 1], fill=grey)
    y += ROW

    # Bold label — use default bitmap font (always available, no TTF needed)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
    except OSError:
        font = ImageFont.load_default()
    label = "IMAGE TEST"
    bbox = draw.textbbox((0, 0), label, font=font)
    lw, lh = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((W - lw) // 2, y + (ROW - lh) // 2), label, fill=0, font=font)
    y += ROW

    # Closing solid black bar
    draw.rectangle([0, y, W - 1, y + ROW - 1], fill=0)

    return img


def print_test_page(printer, width: int) -> None:
    """Exercise the common ESC/POS features so you can eyeball the output."""
    rule = "=" * width

    printer.set(align="center", bold=True, double_height=True, double_width=True)
    printer.text("PRINTER TEST\n")
    printer.set(align="center", bold=False, double_height=False, double_width=False)
    printer.text("Daily Brief project\n")
    printer.text(rule + "\n")

    printer.set(align="left")
    printer.text("Alignment:\n")
    printer.set(align="left")
    printer.text("left\n")
    printer.set(align="center")
    printer.text("center\n")
    printer.set(align="right")
    printer.text("right\n")

    printer.set(align="left", bold=True)
    printer.text("\nStyles:\n")
    printer.set(align="left", bold=True)
    printer.text("bold\n")
    printer.set(align="left", bold=False, underline=1)
    printer.text("underline\n")
    printer.set(align="left", underline=0, double_width=True)
    printer.text("double width\n")
    printer.set(align="left", double_width=False, double_height=True)
    printer.text("double height\n")
    printer.set(align="left", double_height=False)

    printer.text("\nWidth ruler (each line = stated width):\n")
    for w in range(24, 49, 2):
        printer.text("".join(str(i % 10) for i in range(w)) + f" {w}\n")

    # Image test — generated with PIL so no file is needed.
    try:
        printer.text("\nImage test:\n")
        img = _make_test_image(dot_width=384)
        printer.image(img, impl="bitImageRaster")
    except Exception as exc:
        printer.text(f"(image not supported: {exc})\n")

    # QR + barcode are good end-to-end checks of graphics support.
    try:
        printer.text("\nQR code:\n")
        printer.qr("https://github.com/python-escpos/python-escpos", size=6)
    except Exception as exc:
        printer.text(f"(QR not supported: {exc})\n")

    printer.set(align="center")
    printer.text("\n" + rule + "\n")
    printer.text("test complete\n\n\n")
    try:
        printer.cut()
    except Exception:
        printer.text("\n\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Smoke-test the thermal printer.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--list-usb",
        action="store_true",
        help="List USB devices to find the printer's vendor/product IDs, then exit.",
    )
    parser.add_argument(
        "--backend",
        choices=["dummy", "usb", "serial"],
        help="Override the backend from config for this run.",
    )
    parser.add_argument("--config", help="Path to a TOML config file.")
    args = parser.parse_args(argv)

    if args.list_usb:
        return list_usb()

    config = load_config(args.config)
    if args.backend:
        config.printer.backend = args.backend

    print(f"Using backend: {config.printer.backend}", file=sys.stderr)
    try:
        printer = make_printer(config.printer)
    except Exception as exc:
        print(f"error: could not open printer: {exc}", file=sys.stderr)
        print(
            "Hint: run with --list-usb to find IDs, check config.toml, and on "
            "Linux confirm permissions (udev rule or sudo).",
            file=sys.stderr,
        )
        return 1

    try:
        print_test_page(printer, width=config.layout.width_chars)
    finally:
        close = getattr(printer, "close", None)
        if callable(close):
            close()

    if config.printer.backend.lower() == "dummy":
        output = getattr(printer, "output", b"")
        text = bytes(
            b for b in output if b == 0x0A or 0x20 <= b < 0x7F
        ).decode("ascii", errors="replace")
        print("--- dummy backend: decoded text ---")
        print(text)
        print(f"--- {len(output)} raw bytes would have been sent ---")
    else:
        print("Sent test page to the printer.", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
