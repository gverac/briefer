# Installing Daily Brief on a Raspberry Pi

From a freshly-flashed card to a printing appliance. Targets a **Raspberry Pi
Zero 2 W** running **Raspberry Pi OS Bookworm (64-bit)** with NetworkManager.

The examples assume hostname `cedar`, user `briefer`, and the project at
`/home/briefer/briefer` — adjust if yours differ (and update
`systemd/daily-brief.service` to match).

## 1. Flash Raspberry Pi OS

In **Raspberry Pi Imager**, choose **Raspberry Pi OS (64-bit)**. Open the **⚙
settings** before writing and set:

- Hostname: `cedar`
- Username: `briefer` (+ a password)
- Enable **SSH**
- WiFi SSID/password + country — *optional*; leave blank to exercise the
  access-point setup flow instead.

The **hostname you pick here is the console's address**: it's reachable at
`http://<hostname>.local` (so `http://cedar.local`) both during setup and on your
home network afterward, via mDNS. Choose something memorable.

Write the card and boot the Pi.

## 2. SSH in

```bash
ssh briefer@cedar.local      # or briefer@<pi-ip>
```

If you didn't set a hostname in the Imager (or want to change it), set it now —
this is the name `<hostname>.local` resolves to:

```bash
sudo hostnamectl set-hostname cedar      # then reconnect as briefer@cedar.local
```

`avahi-daemon` (which answers `.local`) ships with Raspberry Pi OS; confirm it's
running with `systemctl is-active avahi-daemon` (expect `active`). If you change
the hostname, the console follows automatically — `console_host` in
`config.toml` is only needed to advertise a *different* name.

## 3. System packages

```bash
sudo apt update
sudo apt install -y python3-venv python3-dev build-essential \
                    libusb-1.0-0 \
                    python3-gpiozero python3-lgpio
```

- `libusb-1.0-0` — USB printer access
- `python3-gpiozero`, `python3-lgpio` — the physical setup button (optional)
- `python3-dev`, `build-essential` — so any source-only wheel can compile

## 4. Get the code onto the Pi

From your **laptop** (rsyncs to `briefer@cedar:/home/briefer/briefer`):

```bash
./scripts/sync-to-pi.sh      # Ctrl-C after the first "initial sync" finishes
```

Or clone it directly on the Pi:

```bash
git clone <your-repo> /home/briefer/briefer
```

## 5. Python environment + dependencies (on the Pi)

```bash
cd ~/briefer
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`--system-site-packages` is what lets the venv see the apt-installed
`python3-gpiozero` / `python3-lgpio` from step 3 (they ship native libraries, so
they're installed via apt, not pip). Without it the button is silently disabled
with `button unavailable: No module named 'gpiozero'` in the logs.

## 6. Find and wire the printer

Plug the printer into the Pi's USB, then:

```bash
python scripts/printer_test.py --list-usb      # confirm it shows 1d81:5721

# allow non-root USB access (handy for manual tests):
echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="1d81", ATTRS{idProduct}=="5721", MODE="0666"' \
  | sudo tee /etc/udev/rules.d/99-escpos.rules
sudo udevadm control --reload-rules && sudo udevadm trigger

python scripts/printer_test.py --backend usb   # should print a test receipt
```

## 7. Install the daemon as a service

```bash
sudo cp systemd/daily-brief.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now daily-brief
journalctl -u daily-brief -f                    # watch it start; Ctrl-C to stop watching
```

The daemon runs as **root** (it needs port 80, `nmcli`, and GPIO). It starts the
always-on web console + the scheduler, and brings up the WiFi access point when
the Pi is offline.

## 8. Finish setup in the browser

- **Already on WiFi:** browse to `http://cedar.local` (or `http://<pi-ip>`).
- **No WiFi configured:** join the `daily-brief-setup` network (password
  `briefme123`) from your phone/laptop, browse to `http://cedar.local` (use your
  Pi's hostname; or `http://10.42.0.1` if mDNS isn't available on your device),
  and use the **WiFi** page to join your network. The AP drops once the Pi is
  online; the *same* `*.local` URL keeps reaching the console on your LAN. The
  name comes from the Pi's hostname (override it with `console_host` under
  `[network]`).

In the console:

1. **Set a console password** (first-visit prompt).
2. **Settings** → printer **Backend = usb**, your **location** (lat/lon/tz), and
   optionally a **Claude API key**.
3. **Briefs** → edit a brief: drag to reorder sections, fill in your
   **OpenWeatherMap key** and **calendar URLs**, **Save**, then **Print now** to test.
4. **Schedules** → set when each brief prints.

Edits are saved to `~/briefer/config.toml`; the daemon reloads automatically — no
restart needed.

## Day-to-day

```bash
sudo systemctl status daily-brief     # is it running?
journalctl -u daily-brief -f          # live logs
sudo systemctl restart daily-brief    # after upgrading code
```

- **Button** (GPIO 24): **single tap** reprints the last brief, **double tap**
  re-opens the WiFi setup AP (and prints a slip with the network name, password,
  and the console URL), **5s hold** powers the Pi off. The AP also opens
  automatically whenever WiFi drops.
- **First print of the day** may lag a few seconds while network sources fetch
  live data (cached afterward).
- The console is **HTTP** — fine on a trusted LAN; the password still gates
  access, but it crosses the network in cleartext.

## Updating

### Hands-on (your own Pi, on your LAN)

```bash
# from your laptop:
./scripts/sync-to-pi.sh               # (or git pull on the Pi)
# on the Pi, if dependencies changed:
cd ~/briefer && source .venv/bin/activate && pip install -r requirements.txt
sudo systemctl restart daily-brief
```

### Remote (a device at someone else's house)

For devices you can't SSH into, updates are done by **uploading a release
tarball through the console** (Software page). The install is atomic and
self-healing: the new version is built and smoke-tested in its own slot before
going live, and if it fails to start the device automatically rolls back to the
previous version. The friend's `config.toml` (WiFi, keys, schedules) is never
touched.

**One-time: convert the device to the release layout.** On the Pi:

```bash
cd ~/briefer
sudo -u briefer ./scripts/setup-releases.sh    # builds releases/<v>, current, staging
sudo cp ~/current/systemd/daily-brief.service        /etc/systemd/system/
sudo cp ~/current/systemd/daily-brief-update.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart daily-brief
```

This moves `config.toml` up to `~/config.toml` and points the service at
`~/current` (a symlink to the active release).

**Each release: bump the version, commit, build, send.** On your laptop:

```bash
# 1. bump __version__ in daily_brief/__init__.py, then commit it:
git commit -am "Release 0.2.0"
# 2. build (archives the committed tree):
./scripts/build-release.sh             # writes dist/briefer-<version>.tgz
```

A release is built from the committed tree (`git HEAD`), so the build **refuses
to run with uncommitted changes** — otherwise the version string and the shipped
code could disagree (a tarball named 0.2.0 that still contains 0.1.x). Commit
first. To test a work-in-progress build without committing, use
`./scripts/build-release.sh --dev`, which bundles your working tree as-is and
tags the version `+dev` so it's never mistaken for a real release.

Send that `.tgz` to your friend. They open the console (`http://<hostname>.local`)
on their WiFi, go to **Software**, upload the file, and wait ~30s. The Software
page shows the result (and rolls back automatically if the new build won't run).

> The console is LAN-only, so the friend does the upload from their network — you
> can't reach it from afar without a tunnel (e.g. Tailscale).

## Troubleshooting

- **Service won't start / port 80 in use** — `journalctl -u daily-brief -e`.
  Another web server on 80? Change `[web] port` in `config.toml`.
- **Nothing prints on schedule** — check the printer with
  `python scripts/printer_test.py --backend usb`, and confirm `[printer] backend
  = "usb"` in Settings. Verify the schedule time/day and that it's enabled.
- **`pip install` stalls building a wheel** — ensure step 3's `python3-dev` /
  `build-essential` are installed (most arm64 packages ship prebuilt wheels, so
  this is rare).
- **Button does nothing / `button unavailable: No module named 'gpiozero'`** —
  the venv can't see the apt-installed `gpiozero`/`lgpio`. Recreate it with
  system packages exposed:
  ```bash
  cd ~/briefer && rm -rf .venv
  python3 -m venv --system-site-packages .venv
  source .venv/bin/activate && pip install -r requirements.txt
  sudo systemctl restart daily-brief
  ```
- **Forgot the console password** — edit `~/briefer/config.toml`, delete the
  `password_hash` line under `[web]`, `sudo systemctl restart daily-brief`, then
  set a new one on next visit.
