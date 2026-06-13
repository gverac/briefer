# Daily Brief

Print a daily morning briefing — weather, birthdays, upcoming events, a word of
the day, trivia, an "on this day" fact, and a dad joke — on a thermal receipt
printer attached to a Raspberry Pi Zero W.

The printer is an ESC/POS receipt module (USB/serial) driven by
[python-escpos](https://github.com/python-escpos/python-escpos). Paper is 58mm.
The brief is drawn as a bitmap with a modern TrueType font (not the built-in
receipt font), so it can show weather pictograms, birthday checkboxes, and thin
section rules.

## Status

Working. Sections are fully configurable from `config.toml` — enable/disable and
reorder them, each with its own settings. Sources degrade gracefully: a source
that's offline or misconfigured prints "(unavailable)" instead of failing the
whole brief.

Built-in sections: `weather` (OpenWeatherMap), `birthdays` + `events` (iCal),
`oncall` (iCal), `word` (rare/SAT word + Free Dictionary), `trivia`, `onthisday`,
`daylight`, `joke`, `ascii` (a daily ASCII-art doodle), `ai` (your own
prompt → Claude), and space: `iss`, `moon`, `planets`. A `rotate` section cycles
through choices one-per-day (e.g. the space images);
preview them all with `--all-rotations`. The birthdays header gets a small icon
(opt others in with `icon = "<key>"`), and the page is topped with a rotating
funny greeting.

## Project layout

```
daily_brief/            Python package
  __main__.py           entry point: build + print the brief (--dry-run, --out)
  config.py             load config.toml into dataclasses
  printer.py            make_printer() — the only place that touches hardware
  brief.py              Brief/Section/Item data model + build_brief()
  render.py             draws the brief to a bitmap and prints it as an image
  sources/              one builder per section (registered in __init__.py)
  assets/               bundled font (Inter) + weather pictograms
scripts/
  printer_test.py       hardware smoke test + USB device lister
  gen_weather_icons.py  regenerate the weather pictograms
  sync-to-pi.sh         rsync the project to the Pi on every change
tests/
  test_printer.py       runs against the dummy backend, no hardware needed
config.example.toml     copy to config.toml and edit for your setup
requirements.txt
```

## Setup

Works on macOS (for development, using the `dummy` backend) and on the Pi (with
the real printer). Requires Python 3.11+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config.example.toml config.toml      # then edit config.toml
```

On the Pi, the USB backend also needs libusb:

```bash
sudo apt install libusb-1.0-0
```

## Develop on your laptop (no printer)

`--dry-run` renders the brief to a PNG (no printer needed) so you can preview the
exact layout:

```bash
python -m daily_brief --dry-run             # writes preview.png
python -m daily_brief --dry-run --out /tmp/brief.png
python scripts/printer_test.py --backend dummy
pytest                                      # tests use the dummy backend
```

## Bring up the printer on the Pi

1. **Find out how it connects.** These cheap modules are either raw USB ESC/POS
   devices or a USB-serial adapter.

   ```bash
   python scripts/printer_test.py --list-usb     # raw USB? note vendor:product
   ls -l /dev/ttyUSB* /dev/serial* 2>/dev/null   # serial? note the port
   ```

   > Ignore `1d6b:xxxx` entries — that's the Pi's internal USB root hub, not the
   > printer.

2. **Put the details in `config.toml`** — either `[printer.usb]` (vendor_id /
   product_id) or `[printer.serial]` (port / baudrate), and set `backend`
   accordingly.

3. **Print the test page:**

   ```bash
   python scripts/printer_test.py --backend usb      # or: --backend serial
   ```

   You should get a receipt exercising alignment, bold/underline, double
   size, a width ruler, and a QR code. If that looks right, the hardware is good.

4. **Print the brief:**

   ```bash
   python -m daily_brief --backend usb     # or set backend in config.toml
   ```

### USB permissions on Linux

If the USB backend fails with a permission/access error, add a udev rule so you
don't need sudo (replace the IDs with yours):

```bash
echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="1d81", ATTRS{idProduct}=="5721", MODE="0666"' \
  | sudo tee /etc/udev/rules.d/99-escpos.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
```

## Configuration

All settings live in `config.toml` (gitignored). Start from
[`config.example.toml`](config.example.toml).

- `printer.backend` = `dummy` | `usb` | `serial`.
- `[location]` — `lat` / `lon` / `tz`, used by `weather` and `daylight`.
- `[render]` — bitmap width (`dot_width = 384` for 58mm), font, text sizes.
- `[[sections]]` — one block per section. **File order is print order**; set
  `enabled = false` to skip one. Each block's extra keys are passed to that
  source (e.g. `api_key` for weather, `ical_url` for birthdays/events).

### API keys / setup per section

Only two sections need credentials; everything else works out of the box:

- **`weather`** — free [OpenWeatherMap](https://openweathermap.org/api) `api_key`.
- **`birthdays` / `events` / `oncall`** — a published iCal `.ics` URL (e.g. a
  Google Calendar "secret address"; `webcal://` URLs are accepted).
- **`iss`, `moon`, `planets`, `word`, `trivia`, `onthisday`, `daylight`, `joke`,
  `ascii`** — no key needed.
- **Claude (optional)** — set `[claude] api_key` and `pip install anthropic` to
  have Claude write a fresh daily greeting, define the word of the day (with an
  example sentence), and — with `use_claude = true` on the `ascii` section — draw
  the ASCII art. It also unlocks the `ai` section — your own `title` + `prompt`
  fed to Claude, capped to `max_chars`. Without a key, each falls back to its
  built-in behavior (the `ai` section just shows a hint). The SDK
  isn't a default dependency since its `pydantic-core` build is awkward on the Pi
  Zero W (armv6). Defaults to Opus; set `model = "claude-haiku-4-5"` for ~5× lower
  cost on these tiny daily calls.
