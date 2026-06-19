# Installing Daily Brief on a Raspberry Pi

Targets a **Raspberry Pi Zero 2 W** on **Raspberry Pi OS Bookworm (64-bit)** with
NetworkManager. `scripts/install.sh` does the whole setup and leaves the daemon
running **unprivileged** as a `daily-brief` user, under `/opt/daily-brief`.

Below, `<you>` is your Pi login and `<pi>` is its hostname — substitute your own.

## 1. Flash Raspberry Pi OS

I used the **Raspberry Pi Imager** and chose **Raspberry Pi OS (64-bit)**.

## 2. SSH in

```bash
ssh <you>@<pi>.local      # or <you>@<pi-ip>
```

To change the hostname later: `sudo hostnamectl set-hostname <pi>`. The console
address follows it automatically (`console_host` in `config.toml` only overrides
it to a different name).

## 3. Prerequisites + code

```bash
sudo apt update
sudo apt install -y git python3-venv python3-dev build-essential \
                    libusb-1.0-0 python3-gpiozero python3-lgpio
git clone <your-repo> ~/briefer && cd ~/briefer
```

`gpiozero`/`lgpio` are the (optional) setup button; `libusb-1.0-0` is for USB
printers.

## 4. Install

```bash
sudo ./scripts/install.sh
```

This creates the `daily-brief` user, adds it to the groups that grant
hardware/network access without root (`netdev`/`gpio`/`dialout`/`plugdev`/`lp`),
installs a scoped sudoers drop-in (only `shutdown` + `systemctl restart`), builds
the release under `/opt/daily-brief`, and starts the service. Re-run it to update
a Pi you can SSH into.

For a raw-USB printer, pass its id (from `printer_test.py --list-usb`) so a udev
rule is added — a serial printer needs none:

```bash
sudo ESCPOS_USB_ID=1d81:5721 ./scripts/install.sh
# Test print
sudo -u daily-brief /opt/daily-brief/current/.venv/bin/python scripts/printer_test.py --backend usb
```

## 5. Finish in the browser

- **On WiFi:** open `http://<pi>.local` (or `http://<pi-ip>`).
- **No WiFi:** join the `daily-brief-setup` network (password `briefme123`), open
  `http://<pi>.local` (or `http://10.42.0.1`), and use the **WiFi** page to join
  your network. The AP drops once online; the `.local` URL keeps working on your LAN.

Then: set a console password, fill in **Settings** (printer backend, location,
optional Claude key), edit a **brief** (weather/calendar keys, reorder, **Print
now**), and set **Schedules**. Edits save to `/opt/daily-brief/config.toml` and
reload automatically.

## Day-to-day

```bash
systemctl status daily-brief          # is it running?
journalctl -u daily-brief -f          # live logs
sudo systemctl restart daily-brief    # restart the service
```

- **Button** (GPIO 24): single tap reprints the last brief; double tap re-opens
  the WiFi setup AP (printing a slip with the network + console URL); 5s hold
  powers off. The AP also opens automatically whenever WiFi drops.
- The console is **HTTP** — fine on a trusted LAN, password-gated, but cleartext.

## Updating

**Over SSH:**

```bash
cd ~/briefer && git pull
sudo ./scripts/install.sh       # rebuilds + restarts
```

## How the privileges work

The daemon runs as the unprivileged `daily-brief` user; everything is granted
narrowly:

| Need | Granted by |
|------|-----------|
| GPIO button | `gpio` group |
| Printer (USB-serial / raw-USB) | `dialout` / `plugdev` + udev rule |
| NetworkManager (AP + WiFi) | `netdev` group (NM polkit) |
| Bind port 80 | `AmbientCapabilities=CAP_NET_BIND_SERVICE` |
| `shutdown`, `systemctl restart` | `/etc/sudoers.d/daily-brief` (NOPASSWD, exact commands) |

The code shells out to the last two via `sudo -n` (`daily_brief/privilege.py`).

## Troubleshooting

- **Won't start / port 80 in use** — `journalctl -u daily-brief -e`. Change
  `[web] port`, or confirm the unit keeps `AmbientCapabilities=CAP_NET_BIND_SERVICE`.
- **Nothing prints** — test as the service user (`sudo -u daily-brief
  /opt/daily-brief/current/.venv/bin/python scripts/printer_test.py --backend usb`)
  and check `[printer] backend` in Settings.
- **Button / shutdown / self-update fails silently** — confirm
  `/etc/sudoers.d/daily-brief` exists and validates (`sudo visudo -cf
  /etc/sudoers.d/daily-brief`); re-run `install.sh`.
- **AP/WiFi control fails** — confirm `daily-brief` is in `netdev`
  (`id -nG daily-brief`); restart the service if you just added it.
- **`button unavailable: No module named 'gpiozero'`** — the apt packages weren't
  present when the venv was built; install them and re-run `sudo ./scripts/install.sh`.
- **Forgot the console password** — delete the `password_hash` line under `[web]`
  in `/opt/daily-brief/config.toml`, restart, and set a new one on next visit.
