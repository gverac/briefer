"""Entry point: build the daily brief and send it to the printer.

    python -m daily_brief                      # use config.toml (or defaults)
    python -m daily_brief --config foo.toml
    python -m daily_brief --backend usb        # override the configured backend
    python -m daily_brief --dry-run            # no printer; write a PNG preview
    python -m daily_brief --out brief.png       # also save the rendered bitmap

The brief is rendered as one bitmap (see daily_brief.render), so --dry-run
saves a PNG you can open on a laptop instead of decoding ESC/POS text.
"""

from __future__ import annotations

import argparse
import logging
import sys

from .brief import build_brief
from .config import load_config
from .printer import open_printer
from .render import render_brief

DEFAULT_PREVIEW = "preview.png"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="daily_brief", description=__doc__)
    parser.add_argument("--config", help="Path to a TOML config file.")
    parser.add_argument("--brief", help="Which brief to print (default: the first one).")
    parser.add_argument(
        "--backend",
        choices=["dummy", "usb", "serial"],
        help="Override the printer backend from config.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't touch hardware; render to a PNG preview instead.",
    )
    parser.add_argument(
        "--out",
        help=f"Save the rendered bitmap to this PNG path (default in dry-run: {DEFAULT_PREVIEW}).",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging.")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    config = load_config(args.config)
    if args.backend:
        config.printer.backend = args.backend
    if args.dry_run:
        config.printer.backend = "dummy"

    preview_path = args.out or (DEFAULT_PREVIEW if args.dry_run else None)

    brief_cfg = config.brief(args.brief)
    if brief_cfg is None:
        which = f" {args.brief!r}" if args.brief else ""
        print(f"error: no brief{which} configured", file=sys.stderr)
        return 1

    brief = build_brief(config, brief_cfg)

    try:
        if args.dry_run:
            # No printer object at all: render straight to the preview PNG.
            render_brief(None, brief, config.render, preview_path=preview_path)
            print(f"dry run: wrote {preview_path} ({len(brief.sections)} sections)")
            return 0

        with open_printer(config.printer) as printer:
            image = render_brief(printer, brief, config.render, preview_path=preview_path)
            if preview_path:
                print(f"printed brief; preview saved to {preview_path}")
        from . import lastbrief

        lastbrief.save(image)  # reprintable via the button without rebuilding
    except Exception as exc:  # surface hardware/render errors clearly
        print(f"error: failed to print brief: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
