"""Load, validate, and save configuration from a TOML file.

Reading uses the stdlib `tomllib` (Python 3.11+). Writing (from the setup web
UI) uses `tomli_w`. The data model is:

    section  -- one content block (a source type + its options)
    brief    -- a named, ordered set of sections
    schedule -- a (time -> brief) firing rule

Globals (`[printer] [location] [render] [claude] [network] [web]`) are shared by
all briefs. Old flat `[[sections]]` configs are migrated to a single "default"
brief so existing files keep working.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

# Project root + default config locations.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.toml"
EXAMPLE_CONFIG_PATH = PROJECT_ROOT / "config.example.toml"
ASSETS_DIR = Path(__file__).resolve().parent / "assets"


@dataclass
class UsbConfig:
    vendor_id: int = 0x1D81
    product_id: int = 0x5721
    in_ep: int | None = None
    out_ep: int | None = None


@dataclass
class SerialConfig:
    port: str = "/dev/ttyUSB0"
    baudrate: int = 19200


@dataclass
class PrinterConfig:
    backend: str = "dummy"  # "dummy" | "usb" | "serial"
    profile: str = "default"
    usb: UsbConfig = field(default_factory=UsbConfig)
    serial: SerialConfig = field(default_factory=SerialConfig)
    # Raster pacing: send the bitmap in short bands with a pause between them so
    # the printer's input buffer can drain (avoids the opening-burst overrun
    # that shifts the first sections sideways). See printer.send_image.
    band_height: int = 64
    band_pause: float = 0.05


@dataclass
class LocationConfig:
    lat: float = 0.0
    lon: float = 0.0
    tz: str = "UTC"


@dataclass
class RenderConfig:
    dot_width: int = 384  # 58mm @ 203 dpi
    font: str | None = None  # path to a regular TTF; None -> bundled default
    font_bold: str | None = None
    font_mono: str | None = None  # monospace TTF for ASCII art; None -> bundled default
    body_size: int = 22
    heading_size: int = 26
    margin: int = 8  # left/right inner margin in dots
    time_format: str = "24h"  # "24h" (military) or "12h" (am/pm)
    temp_unit: str = "C"  # weather display: "C" (°C) or "F" (°F)

    def format_temp(self, celsius) -> str:
        """Render a Celsius value as a degree string honouring `temp_unit`."""
        if celsius is None:
            return "--"
        if self.temp_unit == "F":
            return f"{round(celsius * 9 / 5 + 32)}°F"
        return f"{round(celsius)}°C"

    def format_time(self, dt) -> str:
        """Render a datetime/time as a clock string honouring `time_format`.

        24h -> "07:05"; 12h -> "7:05 AM" (leading zero stripped for a cleaner
        look, since %I is zero-padded and %-I isn't portable).
        """
        if self.time_format == "12h":
            s = dt.strftime("%I:%M %p")
            return s[1:] if s.startswith("0") else s
        return dt.strftime("%H:%M")

    def resolve_font(self, bold: bool = False) -> str:
        """Return an absolute path to the requested font face.

        Falls back to the bundled Inter face when no font is configured.
        Relative paths are resolved against the project root.
        """
        configured = self.font_bold if bold else self.font
        if configured:
            p = Path(configured)
            return str(p if p.is_absolute() else PROJECT_ROOT / p)
        bundled = ASSETS_DIR / "fonts" / ("Inter-Bold.ttf" if bold else "Inter-Regular.ttf")
        return str(bundled)

    def resolve_mono(self) -> str:
        """Absolute path to the monospace font (bundled DejaVu Sans Mono default)."""
        if self.font_mono:
            p = Path(self.font_mono)
            return str(p if p.is_absolute() else PROJECT_ROOT / p)
        return str(ASSETS_DIR / "fonts" / "DejaVuSansMono.ttf")


@dataclass
class ClaudeConfig:
    """Claude API access. `enabled` is the master AI toggle (a checkbox in the
    UI); AI is `active` only when it's enabled *and* a key is set."""

    api_key: str | None = None
    model: str = "claude-sonnet-4-6"
    enabled: bool = True

    @property
    def active(self) -> bool:
        return self.enabled and bool(self.api_key)


@dataclass
class EmailConfig:
    """Inbox watcher: print approved email as it arrives (independent of briefs).

    The daemon polls `imap_host` every `poll_seconds` and prints each new
    message whose `From:` is on `allowed_senders` (and, with `require_auth`,
    that passes DKIM/DMARC). `active` (= enabled + creds + an allow-list) gates
    the whole feature, mirroring `ClaudeConfig.active`.
    """

    enabled: bool = False
    imap_host: str = "imap.gmail.com"
    imap_port: int = 993
    username: str | None = None
    password: str | None = None
    allowed_senders: list[str] = field(default_factory=list)
    require_auth: bool = True  # require DKIM/DMARC pass — blocks From spoofing
    max_chars: int = 600       # truncate long bodies to this many characters
    print_images: bool = True
    mark_read: bool = True      # mark printed messages read so each prints once
    poll_seconds: int = 60

    @property
    def active(self) -> bool:
        return bool(
            self.enabled and self.username and self.password and self.allowed_senders
        )


@dataclass
class NetworkConfig:
    """Setup-mode access point + the physical button that re-opens setup."""

    ap_ssid: str = "daily-brief-setup"
    ap_password: str = "briefme123"
    button_gpio: int | None = 24
    # Hostname the control console is reachable at, e.g. "daily-brief.local". Served
    # by the Pi's mDNS (avahi, preinstalled on Raspberry Pi OS), so the same URL
    # works during setup *and* afterward on the home network. Empty = derive it
    # from the Pi's own hostname, so the printed name can't drift from reality.
    console_host: str = ""

    def effective_console_host(self) -> str:
        """The console hostname to advertise: the override, or `<hostname>.local`."""
        if self.console_host:
            return self.console_host
        import socket

        return f"{socket.gethostname().split('.')[0]}.local"


@dataclass
class WebConfig:
    """Always-on control-console web server + its auth."""

    host: str = "0.0.0.0"
    port: int = 80
    password_hash: str = ""  # werkzeug hash; empty = first-run, prompt to set one
    secret_key: str = ""     # Flask session signing; auto-generated on first run
    # Allow installing an uploaded release tarball from the console's Software
    # page. Off by default: accepting and running an arbitrary build is risky,
    # so it's a deliberate opt-in (set `allow_remote_update = true`).
    allow_remote_update: bool = False


@dataclass
class SectionConfig:
    """One section: a source type plus its options.

    `options` holds every key other than the recognised top-level ones, so each
    source reads its own settings (api_key, ical_url, horizon_days, …) without
    config.py needing to know about them.
    """

    type: str
    title: str | None = None
    enabled: bool = True
    options: dict = field(default_factory=dict)

    def get(self, key: str, default=None):
        return self.options.get(key, default)


@dataclass
class BriefConfig:
    """A named, ordered set of sections. Schedules point to these by name."""

    name: str
    sections: list[SectionConfig] = field(default_factory=list)


@dataclass
class ScheduleConfig:
    """A firing rule: print `brief` at `time` on `days` (empty days = daily)."""

    name: str
    brief: str
    time: str = "07:30"  # "HH:MM" 24h, local time
    days: list[str] = field(default_factory=list)  # mon..sun; empty = every day
    enabled: bool = True


@dataclass
class Config:
    printer: PrinterConfig = field(default_factory=PrinterConfig)
    location: LocationConfig = field(default_factory=LocationConfig)
    render: RenderConfig = field(default_factory=RenderConfig)
    claude: ClaudeConfig = field(default_factory=ClaudeConfig)
    email: EmailConfig = field(default_factory=EmailConfig)
    network: NetworkConfig = field(default_factory=NetworkConfig)
    web: WebConfig = field(default_factory=WebConfig)
    briefs: list[BriefConfig] = field(default_factory=list)
    schedules: list[ScheduleConfig] = field(default_factory=list)

    def brief(self, name: str | None = None) -> BriefConfig | None:
        """Find a brief by name, or the first brief when name is None."""
        if not self.briefs:
            return None
        if name is None:
            return self.briefs[0]
        return next((b for b in self.briefs if b.name == name), None)


# --- loading ---------------------------------------------------------------

# Keys handled explicitly on a section entry; everything else -> options.
_SECTION_RESERVED = {"type", "title", "enabled"}


def load_config(path: Path | str | None = None) -> Config:
    """Load configuration from a TOML file.

    Falls back to `config.example.toml`, then to built-in defaults, so the
    project runs out of the box in dummy mode without any local setup.
    """
    candidates: list[Path] = []
    if path is not None:
        candidates.append(Path(path))
    else:
        candidates.extend([DEFAULT_CONFIG_PATH, EXAMPLE_CONFIG_PATH])

    for candidate in candidates:
        if candidate.is_file():
            with candidate.open("rb") as fh:
                data = tomllib.load(fh)
            return _from_dict(data)

    return Config()


def _section_from_dict(raw: dict) -> SectionConfig | None:
    if "type" not in raw:
        return None
    options = {k: v for k, v in raw.items() if k not in _SECTION_RESERVED}
    return SectionConfig(
        type=raw["type"],
        title=raw.get("title"),
        enabled=raw.get("enabled", True),
        options=options,
    )


def _sections_from_list(raw_list) -> list[SectionConfig]:
    out = []
    for raw in raw_list or []:
        sec = _section_from_dict(raw)
        if sec is not None:
            out.append(sec)
    return out


def _from_dict(data: dict) -> Config:
    printer_raw = data.get("printer", {})
    usb_raw = printer_raw.get("usb", {})
    serial_raw = printer_raw.get("serial", {})
    location_raw = data.get("location", {})
    render_raw = data.get("render", {})
    claude_raw = data.get("claude", {})
    email_raw = data.get("email", {})
    network_raw = data.get("network", {})
    web_raw = data.get("web", {})

    printer = PrinterConfig(
        backend=printer_raw.get("backend", "dummy"),
        profile=printer_raw.get("profile", "default"),
        usb=UsbConfig(
            vendor_id=usb_raw.get("vendor_id", 0x1D81),
            product_id=usb_raw.get("product_id", 0x5721),
            in_ep=usb_raw.get("in_ep"),
            out_ep=usb_raw.get("out_ep"),
        ),
        serial=SerialConfig(
            port=serial_raw.get("port", "/dev/ttyUSB0"),
            baudrate=serial_raw.get("baudrate", 19200),
        ),
        band_height=int(printer_raw.get("band_height", 64)),
        band_pause=float(printer_raw.get("band_pause", 0.05)),
    )
    location = LocationConfig(
        lat=float(location_raw.get("lat", 0.0)),
        lon=float(location_raw.get("lon", 0.0)),
        tz=location_raw.get("tz", "UTC"),
    )
    render = RenderConfig(
        dot_width=int(render_raw.get("dot_width", 384)),
        font=render_raw.get("font"),
        font_bold=render_raw.get("font_bold"),
        font_mono=render_raw.get("font_mono"),
        body_size=int(render_raw.get("body_size", 22)),
        heading_size=int(render_raw.get("heading_size", 26)),
        margin=int(render_raw.get("margin", 8)),
        time_format=render_raw.get("time_format", "24h"),
        temp_unit=render_raw.get("temp_unit", "C"),
    )
    claude = ClaudeConfig(
        api_key=claude_raw.get("api_key"),
        model=claude_raw.get("model", "claude-sonnet-4-6"),
        enabled=claude_raw.get("enabled", True),
    )
    email = EmailConfig(
        enabled=email_raw.get("enabled", False),
        imap_host=email_raw.get("imap_host", "imap.gmail.com"),
        imap_port=int(email_raw.get("imap_port", 993)),
        username=email_raw.get("username"),
        password=email_raw.get("password"),
        allowed_senders=[str(s).strip() for s in email_raw.get("allowed_senders", []) if str(s).strip()],
        require_auth=email_raw.get("require_auth", True),
        max_chars=int(email_raw.get("max_chars", 600)),
        print_images=email_raw.get("print_images", True),
        mark_read=email_raw.get("mark_read", True),
        poll_seconds=int(email_raw.get("poll_seconds", 60)),
    )
    network = NetworkConfig(
        ap_ssid=network_raw.get("ap_ssid", "daily-brief-setup"),
        ap_password=network_raw.get("ap_password", "briefme123"),
        button_gpio=network_raw.get("button_gpio", 24),
        console_host=network_raw.get("console_host", ""),
    )
    web = WebConfig(
        host=web_raw.get("host", "0.0.0.0"),
        port=int(web_raw.get("port", 80)),
        password_hash=web_raw.get("password_hash", ""),
        secret_key=web_raw.get("secret_key", ""),
        allow_remote_update=bool(web_raw.get("allow_remote_update", False)),
    )

    # Briefs: new `[[briefs]]` schema, else migrate flat `[[sections]]`.
    briefs: list[BriefConfig] = []
    if data.get("briefs"):
        for raw in data["briefs"]:
            briefs.append(
                BriefConfig(
                    name=raw.get("name", "default"),
                    sections=_sections_from_list(raw.get("sections")),
                )
            )
    elif data.get("sections"):  # legacy flat config -> one "default" brief
        briefs.append(BriefConfig(name="default",
                                  sections=_sections_from_list(data["sections"])))

    schedules = [
        ScheduleConfig(
            name=raw.get("name", raw.get("brief", "schedule")),
            brief=raw.get("brief", ""),
            time=raw.get("time", "07:30"),
            days=list(raw.get("days", [])),
            enabled=raw.get("enabled", True),
        )
        for raw in data.get("schedules", [])
        if raw.get("brief")
    ]

    return Config(
        printer=printer, location=location, render=render, claude=claude,
        email=email, network=network, web=web, briefs=briefs, schedules=schedules,
    )


# --- saving (setup web UI) -------------------------------------------------


def _section_to_dict(sec: SectionConfig) -> dict:
    out: dict = {"type": sec.type}
    if sec.title is not None:
        out["title"] = sec.title
    out["enabled"] = sec.enabled
    # options are already TOML-native values; drop Nones tomli_w can't serialize
    for k, v in sec.options.items():
        if v is not None:
            out[k] = v
    return out


def to_dict(config: Config) -> dict:
    """Serialize a Config to a plain dict ready for tomli_w (drops None values)."""
    data: dict = {
        "printer": {
            "backend": config.printer.backend,
            "profile": config.printer.profile,
            "band_height": config.printer.band_height,
            "band_pause": config.printer.band_pause,
            "usb": {
                "vendor_id": config.printer.usb.vendor_id,
                "product_id": config.printer.usb.product_id,
            },
            "serial": {
                "port": config.printer.serial.port,
                "baudrate": config.printer.serial.baudrate,
            },
        },
        "location": {
            "lat": config.location.lat,
            "lon": config.location.lon,
            "tz": config.location.tz,
        },
        "render": {
            "dot_width": config.render.dot_width,
            "body_size": config.render.body_size,
            "heading_size": config.render.heading_size,
            "margin": config.render.margin,
            "time_format": config.render.time_format,
            "temp_unit": config.render.temp_unit,
        },
        "claude": {"model": config.claude.model, "enabled": config.claude.enabled},
        "email": {
            "enabled": config.email.enabled,
            "imap_host": config.email.imap_host,
            "imap_port": config.email.imap_port,
            "allowed_senders": config.email.allowed_senders,
            "require_auth": config.email.require_auth,
            "max_chars": config.email.max_chars,
            "print_images": config.email.print_images,
            "mark_read": config.email.mark_read,
            "poll_seconds": config.email.poll_seconds,
        },
        "network": {
            "ap_ssid": config.network.ap_ssid,
            "ap_password": config.network.ap_password,
            **({"console_host": config.network.console_host} if config.network.console_host else {}),
        },
        "web": {
            "host": config.web.host,
            "port": config.web.port,
            **({"password_hash": config.web.password_hash} if config.web.password_hash else {}),
            **({"secret_key": config.web.secret_key} if config.web.secret_key else {}),
            **({"allow_remote_update": True} if config.web.allow_remote_update else {}),
        },
        "briefs": [
            {
                "name": b.name,
                "sections": [_section_to_dict(s) for s in b.sections],
            }
            for b in config.briefs
        ],
        "schedules": [
            {
                "name": s.name,
                "brief": s.brief,
                "time": s.time,
                **({"days": s.days} if s.days else {}),
                "enabled": s.enabled,
            }
            for s in config.schedules
        ],
    }
    # Optional values only when set.
    for opt, val in (
        ("in_ep", config.printer.usb.in_ep),
        ("out_ep", config.printer.usb.out_ep),
    ):
        if val is not None:
            data["printer"]["usb"][opt] = val
    for opt, val in (("font", config.render.font), ("font_bold", config.render.font_bold),
                     ("font_mono", config.render.font_mono)):
        if val is not None:
            data["render"][opt] = val
    if config.claude.api_key:
        data["claude"]["api_key"] = config.claude.api_key
    if config.email.username:
        data["email"]["username"] = config.email.username
    if config.email.password:
        data["email"]["password"] = config.email.password
    if config.network.button_gpio is not None:
        data["network"]["button_gpio"] = config.network.button_gpio
    return data


def save_config(config: Config, path: Path | str | None = None) -> Path:
    """Write `config` to TOML (machine-managed; comments are not preserved)."""
    import tomli_w

    target = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    tmp = target.with_suffix(target.suffix + ".tmp")
    with tmp.open("wb") as fh:
        tomli_w.dump(to_dict(config), fh)
    tmp.replace(target)  # atomic
    return target
