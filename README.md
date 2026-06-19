# Daily Brief

Software for the Raspberry Pi Zero 2 W powered brief printer.
Prints a daily briefing with customizable sections: weather, birthdays, events, word of the day, trivia,
"on this day", a joke
Requires an ESC/POS thermal printer driven by [python-escpos](https://github.com/python-escpos/python-escpos).

> ## ⚠️ Disclaimer
>
> **Most of this repo was vibe coded** by Claude with a human in the
> loop driving the hardware decisions and acceptance testing. It works on the
> author's specific build, but your mileage may vary.

## How it works

Runs as an appliance: a password-protected **web console** edits most config,
**briefs** are named, ordered sets of sections and they are fired by **schedules**.
An offline or misconfigured source prints "(unavailable)"
instead of failing the brief.

### Sample brief

![Sample brief](sample_brief.png)

- **Model:** `section`s containes `brief`s which are assigned to `schedule`s, all in one `config.toml`.
- **Console:** reorder sections (drag-drop), edit keys / calendar URLs / prompts,
  manage briefs + schedules + settings, enter WiFi, print/preview.
- **Setup AP:** with no WiFi the Pi becomes an access point to reach the console
  and join a network; it drops once online. A GPIO button re-opens it.
  (Bookworm + NetworkManager.)

### Sections

Available sections: 
- `greeting`
- `weather` (OpenWeatherMap)
- `birthdays` (webcal or iCal)
- `events` (webcal or iCal)
- `oncall` (webcal or iCal)
- `word`
- `trivia`
- `onthisday`
- `daylight`
- `joke`
- `ascii`
- `ai` (custom prompt, Claude only)
- `iss` (current location of the ISS)
- `moon` (phase)
- `planets` (visible planets)

### Email printing

There is also an email integration where you can provide an email and an app password for it.
The daemon will monitor this email's inbox and print all emails, up to some configurable character limit.
There's also an allow-list so only approved senders get printed.

### Button

There is support for a button that can do three actions:
1. Single press: reprints the last printed brief
2. Double press: enters WiFi setup mode. Will print the advertised SSID and password, the user can then
choose a different network to join on the console
3. Long press (5 seconds): shuts down the raspberry pi safely

## Project layout

```
daily_brief/            Python package
  __main__.py           print CLI: build + print a brief (--brief, --dry-run, --out)
  daemon.py             long-running service: scheduler + setup-mode state machine
  config.py             load/save config.toml; briefs/schedules/globals dataclasses
  printer.py            make_printer() — the only place that touches hardware
  brief.py              Brief/Section/Item data model + build_brief(config, brief)
  render.py             draws the brief to a bitmap and prints it as an image
  network.py            nmcli wrapper (AP / WiFi / connectivity); no-ops off-Pi
  sources/              one builder per section + specs.py (field schema for the UI)
  web/                  Flask setup UI (templates, static, forms)
  assets/               bundled fonts + weather/header pictograms + ISS world map
scripts/                install.sh, printer_test.py, build-release.sh
systemd/                daily-brief.service + the release-updater unit
config.example.toml     copy to config.toml (or let the web UI write it)
```

## Hardware

This is what I used and what will work witht the 3D models [here](https://www.printables.com/model/1758897). I included STEP files so you
can use these or modify the models to your needs (e.g. if you want to use a different button, or no button).

- Raspberry Pi Zero 2 W (I don't think the Zero would work)
- Receipt printer module. I think any ECS/POS one would work, but I used [this one](https://www.amazon.com/dp/B0GJDZKYKV)
- Short USB B to micro USB [cable](https://www.amazon.com/dp/B0DJVG778V)
- 5V Power supply. Mine is 5 amps
- I used [these DC jack conenctors](https://www.amazon.com/dp/B07LF1193N)
- [Button](https://www.amazon.com/dp/B0FM8VM8Z5)
- 4 [M2.5 self tapping screws](https://www.amazon.com/dp/B08V8BYWHQ) to attach the lid to the housing
- 4 [M2.5 standoffs](https://www.amazon.com/dp/B075K3QBMX) to attach the Pi to the housing

The wiring is pretty simple. the Pi and the printer are connected via USB. You need to supply
5 V to both the Pi and the printer from the power supply, and if you want the button, connect GPIO
pin 24 (or any pin you choose) to ground through the button.

## Run on the Pi

See **[INSTALL.md](INSTALL.md)** for more details.

```bash
sudo ./scripts/install.sh
```

## Printer setup

1. Find how it connects:
   ```bash
   python scripts/printer_test.py --list-usb     # raw USB → note vendor:product
   ls -l /dev/ttyUSB* /dev/serial* 2>/dev/null   # serial → note the port
   ```
   (Ignore `1d6b:xxxx` — that's the Pi's internal USB hub.)
2. Set `[printer.usb]` (vendor_id / product_id) or `[printer.serial]` (port /
   baudrate) in `config.toml`, and `backend` to match.
3. Test — prints a page exercising alignment, styles, a ruler, and a QR code:
   ```bash
   python scripts/printer_test.py --backend usb   # or: --backend serial
   ```

Raw-USB permission error on Linux? Add a udev rule (your IDs):

```bash
echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="1d81", ATTRS{idProduct}=="5721", GROUP="plugdev", MODE="0660"' \
  | sudo tee /etc/udev/rules.d/99-escpos.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
```

Three sources need credentials; everything else works out of the box:

- **`weather`** — free [OpenWeatherMap](https://openweathermap.org/api) `api_key`
- **`birthdays` / `events` / `oncall`** — a published iCal `.ics` URL (`webcal://` also works)
- **AI (Claude)** — if you want to use the AI feature, you need to supply a claude API key

## Known issues

- Sometimes the first few lines of the brief get printed wrong, where the left side of the text is printed
 on the right side and the right side on the left. I think this has to do with the printer's hardware and buffer
 because the briefs are generated fine. I've attempted to fix this by introducing configurable wait times and
limiting the height of each printed chunk, but you may need to play around with your setup if this happens.

## Other features

### Updater

This is disabled by default, but it technically works. You can create a release by running the `build-release.sh`
script and then upload the tarball on the web console to update the software. I did this so I can give printers
to non-technial friends and family and still be able to update the software. However, as-is, it's basically a
remote code execution vulnerability so until it's improved, it's going to be disabled by default.

### WiFi AP for selecting wifi

This is also a convenience feature for non-technical people. When the device is not connected to any WiFi or when
the button is pressed twice, it will enter AP mode and advertise its own network (it will print the details too).
Then the user can join that network, log into the console and select some other WiFi network.

## Assets
- Map assets created with https://www.mapchart.net