"""Load and validate configuration from a TOML file.

Uses the stdlib `tomllib` (Python 3.11+), which both this Mac (3.13) and a
current Raspberry Pi OS (3.11+) provide, so there's no extra dependency.

The brief is fully config-driven: sections are declared as an array of tables
(`[[sections]]`) so their *file order* is the *print order*, each carries an
`enabled` flag, and any extra keys become per-source `options`.
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
    """Optional Claude API access, shared by the greeting and word sources."""

    api_key: str | None = None
    model: str = "claude-opus-4-8"

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)


@dataclass
class SectionConfig:
    """One `[[sections]]` entry: a source type plus its options.

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
class Config:
    printer: PrinterConfig = field(default_factory=PrinterConfig)
    location: LocationConfig = field(default_factory=LocationConfig)
    render: RenderConfig = field(default_factory=RenderConfig)
    claude: ClaudeConfig = field(default_factory=ClaudeConfig)
    sections: list[SectionConfig] = field(default_factory=list)


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

    # No file found anywhere: pure defaults (dummy backend, no sections).
    return Config()


# Keys handled explicitly on a [[sections]] entry; everything else -> options.
_SECTION_RESERVED = {"type", "title", "enabled"}


def _from_dict(data: dict) -> Config:
    printer_raw = data.get("printer", {})
    usb_raw = printer_raw.get("usb", {})
    serial_raw = printer_raw.get("serial", {})
    location_raw = data.get("location", {})
    render_raw = data.get("render", {})
    claude_raw = data.get("claude", {})

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
    )

    claude = ClaudeConfig(
        api_key=claude_raw.get("api_key"),
        model=claude_raw.get("model", "claude-opus-4-8"),
    )

    sections: list[SectionConfig] = []
    for raw in data.get("sections", []):
        if "type" not in raw:
            continue  # skip malformed entries rather than crash
        options = {k: v for k, v in raw.items() if k not in _SECTION_RESERVED}
        sections.append(
            SectionConfig(
                type=raw["type"],
                title=raw.get("title"),
                enabled=raw.get("enabled", True),
                options=options,
            )
        )

    return Config(
        printer=printer,
        location=location,
        render=render,
        claude=claude,
        sections=sections,
    )
