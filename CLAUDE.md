# CLAUDE.md

Guidance for working in this repo.

## What this is

A daily-brief printer. It builds a short briefing (weather, birthdays,
reminders, …) and prints it on a 58mm ESC/POS thermal receipt printer driven by
[python-escpos](https://github.com/python-escpos/python-escpos).

## Where it runs

- **Target hardware:** Raspberry Pi Zero W (ARM, slow). The printer is attached
  to the Pi via USB/serial.
- **Development:** done on a laptop (macOS) using the `dummy` printer backend,
  then deployed to the Pi. Keep all hardware access behind `daily_brief.printer`
  so the rest of the code stays runnable and testable without a printer.
- Python 3.11+ (uses stdlib `tomllib`). Don't add deps that aren't ARM-friendly
  or that bloat install time on the Pi Zero.

## Architecture

The brief is rendered as **one tall bitmap** (modern TrueType font, thin rules,
checkboxes, weather pictograms) and sent to the printer as a raster image — not
with the built-in ESC/POS text font. That's a deliberate choice: it's the only
way to get a non-receipt look and graphics. The Pi Zero W rasterizes this more
slowly than text, but it's a once-a-day print.

- `daily_brief/config.py` — `load_config()` reads `config.toml` into dataclasses.
  Sections are an array of tables (`[[sections]]`): **file order = print order**,
  each has `enabled` + per-source `options`. Falls back to `config.example.toml`,
  then defaults, so it always runs.
- `daily_brief/printer.py` — **the only module that touches hardware.**
  `make_printer(cfg)` returns a python-escpos device (Dummy / Usb / Serial).
- `daily_brief/brief.py` — data model: `Brief` → `Section` → `Item`s
  (`Text`, `Checkbox`, `Bullet`, `Banner`, `KeyVal`, `Weather`, `Picture`, `Mono`).
  `Section.icon` is a header pictogram key. Sources are data-only; the renderer
  owns all drawing. `build_brief(config, expand_rotations=...)` iterates sections.
- `daily_brief/render.py` — `Canvas` (PIL) + `render_brief(printer, brief, cfg)`.
  Draws each Item, crops to height, prints via `printer.image(...)`. `printer`
  may be `None` to only write a PNG preview. Header shows a rotating funny
  greeting (`greetings.py`), shrunk to fit.
- `daily_brief/sources/` — one builder per source, registered in
  `sources/__init__.py` (`BUILDERS`). Every call goes through `safe_build`, which
  turns any failure into an "(unavailable)" section. Header icons are off by
  default except birthdays (`DEFAULT_SECTION_ICONS`); any section can opt in with
  `icon = "<key>"` or out with `icon = ""`. A `rotate` section (config key
  `choices`) cycles one child per day;
  `expand_section` expands all children in test mode. `_http.py` wraps `requests`
  with a timeout + TTL file cache (`~/.cache/daily_brief/`) and stale fallback.
  Space sources live in `space.py` (iss/moon/planets). The `ascii` source draws
  a daily piece from `daily_brief/ascii_art.py` as a `Mono` item, or has Claude
  draw it when `use_claude = true`. The `ai` source (`ai.py`) feeds a config
  `prompt` to Claude and prints the answer, capped to `max_chars`.
- `daily_brief/assets/` — bundled Inter + DejaVu Sans Mono fonts, weather
  pictograms (`weather/`), header/banner icons (`icons/`), and the ISS world map
  (`space/world.png`). Regenerate icons with `scripts/gen_icons.py` /
  `scripts/gen_weather_icons.py`.
- `daily_brief/llm.py` — optional Claude wrapper (`generate()`), used by the
  greeting and `word` sources. Lazily imports the `anthropic` SDK and degrades to
  None if it's missing / no key / the call fails, so callers fall back. `anthropic`
  is an *optional* dep (not in `requirements.txt`): pydantic-core (Rust) is rough
  on the Pi Zero W's armv6. Key + model live in `[claude]` in config.
- `daily_brief/__main__.py` — CLI (`python -m daily_brief`); `--dry-run` writes a
  PNG preview, `--out` saves the bitmap, `--backend` overrides config.
- `scripts/printer_test.py` — hardware smoke test + `--list-usb`.
  `scripts/gen_weather_icons.py` — regenerate the weather pictograms.

## Conventions

- Width is in **dots** (`config.render.dot_width`, 384 for 58mm) — the renderer
  word-wraps to pixel width. Don't hardcode widths or assume a char count.
- New content sources must degrade gracefully (network down, no creds) and never
  crash the print job. Return data Items; let `safe_build` handle failures. Use
  `_http.get_json`/`get_text` so caching + fallback come for free.
- To add a source: write `sources/foo.py` with `build(section_cfg, ctx)`,
  register it in `BUILDERS`, add a `[[sections]]` block (`type = "foo"`).
- Preview on a laptop with `--dry-run` (opens a PNG); the `dummy` backend still
  works for byte capture.
- Secrets / device IDs / calendar URLs / API keys go in `config.toml`
  (gitignored), never in code.

## Common commands

```bash
source .venv/bin/activate
pip install -r requirements.txt

python -m daily_brief --dry-run            # render to preview.png (no printer)
python -m daily_brief --dry-run --out /tmp/b.png
python scripts/printer_test.py --backend dummy
pytest

# On the Pi:
python scripts/printer_test.py --list-usb  # find vendor:product id
python -m daily_brief --backend usb        # build + print for real
```
