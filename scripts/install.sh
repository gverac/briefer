#!/usr/bin/env bash
# One-command installer for Daily Brief on a Raspberry Pi (Raspberry Pi OS
# Bookworm). Run it ONCE as root from a checkout of this repo:
#
#   sudo ./scripts/install.sh
#
# It sets the device up to run the daemon UNPRIVILEGED, the idiomatic way:
#   1. creates the `daily-brief` system user (home /opt/daily-brief, no login)
#   2. adds it to the groups that grant hardware/network access without root:
#        netdev  -> manage NetworkManager (the WiFi AP + joining networks)
#        gpio    -> the setup button
#        dialout -> a USB-serial printer (/dev/ttyUSB*)
#        plugdev,lp -> a raw-USB ESC/POS printer (with the optional udev rule)
#   3. installs /etc/sudoers.d/daily-brief — NOPASSWD on the *only* two things
#      that still need privilege: `shutdown` (button hold) and `systemctl
#      restart` (self-update)
#   4. copies the code to /opt/daily-brief/briefer, builds the release layout
#      (releases/<v> + venv + the `current` symlink), and moves config.toml out
#      so updates never touch your settings
#   5. installs + enables the systemd units; the daemon then runs as the
#      `daily-brief` user and binds port 80 via CAP_NET_BIND_SERVICE
#
# Re-running is safe (idempotent): it builds a fresh release and restarts.
#
# Prerequisites (install first):
#   sudo apt update
#   sudo apt install -y python3-venv python3-dev build-essential rsync \
#                       libusb-1.0-0 python3-gpiozero python3-lgpio
#
# Raw-USB printer? Pass its USB id so a udev rule is installed for it:
#   sudo ESCPOS_USB_ID=1d81:5721 ./scripts/install.sh
# (Serial printers need no rule — the `dialout` group covers them.)
#
# Developing on the device? REUSE_VENV=1 reuses one shared venv across re-runs
# instead of rebuilding it each time, so a re-install takes seconds not minutes:
#   sudo REUSE_VENV=1 ./scripts/install.sh
# (Leave it off for the device you actually ship — releases stay self-contained.)

set -euo pipefail

USER_NAME="daily-brief"
BASE="/opt/daily-brief"
GROUPS_WANTED="netdev gpio dialout plugdev lp"
SRC="$(cd "$(dirname "$0")/.." && pwd)"   # the checkout this script lives in

if [ "$(id -u)" -ne 0 ]; then
  echo "error: run as root (sudo $0)" >&2
  exit 1
fi

echo "==> Daily Brief installer (base: $BASE, user: $USER_NAME)"

# --- 1. service user --------------------------------------------------------
if ! id -u "$USER_NAME" >/dev/null 2>&1; then
  echo "==> creating system user $USER_NAME"
  useradd --system --home-dir "$BASE" --create-home \
          --shell /usr/sbin/nologin "$USER_NAME"
fi
mkdir -p "$BASE"
chown "$USER_NAME:$USER_NAME" "$BASE"

# --- 2. group memberships ---------------------------------------------------
for g in $GROUPS_WANTED; do
  if getent group "$g" >/dev/null; then
    usermod -aG "$g" "$USER_NAME"
  else
    echo "==> (note) no '$g' group on this system; skipping"
  fi
done
echo "==> $USER_NAME groups: $(id -nG "$USER_NAME")"

# --- 3. sudoers drop-in -----------------------------------------------------
install -m 0440 "$SRC/systemd/daily-brief.sudoers" /etc/sudoers.d/daily-brief
if ! visudo -cf /etc/sudoers.d/daily-brief >/dev/null; then
  echo "error: sudoers file failed validation; removing it" >&2
  rm -f /etc/sudoers.d/daily-brief
  exit 1
fi
echo "==> installed /etc/sudoers.d/daily-brief"

# --- 4. optional udev rule for a raw-USB printer ----------------------------
if [ -n "${ESCPOS_USB_ID:-}" ]; then
  vid="${ESCPOS_USB_ID%%:*}"
  pid="${ESCPOS_USB_ID##*:}"
  printf 'SUBSYSTEM=="usb", ATTRS{idVendor}=="%s", ATTRS{idProduct}=="%s", GROUP="plugdev", MODE="0660"\n' \
    "$vid" "$pid" > /etc/udev/rules.d/99-daily-brief-usb.rules
  udevadm control --reload-rules && udevadm trigger
  echo "==> installed udev rule for USB printer $vid:$pid"
else
  echo "==> (skip udev) serial printers need none; for a raw-USB printer re-run with ESCPOS_USB_ID=VVVV:PPPP"
fi

# --- 5. place the code under the base ---------------------------------------
DEST="$BASE/briefer"
if [ "$SRC" != "$DEST" ]; then
  echo "==> copying source to $DEST"
  mkdir -p "$DEST"
  rsync -a --delete \
    --exclude='.venv' --exclude='.git' --exclude='__pycache__' \
    --exclude='.pytest_cache' --exclude='*.pyc' --exclude='config.toml' \
    --exclude='dist' --exclude='releases' --exclude='staging' \
    "$SRC/" "$DEST/"
fi
chown -R "$USER_NAME:$USER_NAME" "$DEST"

# --- 6. build the release layout (as the service user) ----------------------
echo "==> building release (the venv build can take a few minutes on a Pi Zero)"
# REUSE_VENV=1 (set when developing) makes setup-releases reuse one shared venv
# instead of rebuilding from scratch; pass it through the sudo env barrier.
sudo -u "$USER_NAME" env REUSE_VENV="${REUSE_VENV:-0}" "$DEST/scripts/setup-releases.sh"

# --- 7. systemd units -------------------------------------------------------
install -m 0644 "$BASE/current/systemd/daily-brief.service"        /etc/systemd/system/
install -m 0644 "$BASE/current/systemd/daily-brief-update.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now daily-brief
echo "==> daily-brief service enabled and started (running as $USER_NAME)"

# --- 8. done ----------------------------------------------------------------
HOST="$(hostname).local"
cat <<EOF

Done. The daemon is running unprivileged as '$USER_NAME'.

Open the console to finish setup (set a password, enter WiFi, configure briefs):
  http://$HOST          (on your home network)
  http://10.42.0.1      (if joining the 'daily-brief-setup' access point)

Useful:
  systemctl status daily-brief
  journalctl -u daily-brief -f
  cd $DEST && git pull && sudo ./scripts/install.sh   # update a self-hosted Pi
EOF
