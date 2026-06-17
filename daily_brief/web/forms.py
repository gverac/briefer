"""Parse setup-UI form submissions back into config objects.

The brief editor is one form: a hidden `order` field (maintained by SortableJS)
lists the original section indices in their new order, and each section's inputs
are namespaced `sec-<origindex>-<key>`. We rebuild each section starting from its
*original* options (so any keys not exposed as spec fields survive) and overlay
the edited spec fields.
"""

from __future__ import annotations

import re

from ..config import SectionConfig
from ..sources import DEFAULT_SECTION_ICONS, SECTION_SPECS


def _coerce(field, raw, options):
    """Apply one spec field's submitted value onto `options` in place."""
    key, kind = field.key, field.kind
    present = raw is not None
    if kind == "bool":
        options[key] = raw is not None  # checkbox: present == checked
    elif kind == "int":
        if present and str(raw).strip():
            try:
                options[key] = int(str(raw).strip())
            except ValueError:
                pass
    elif kind == "secret":
        if raw:  # blank submission keeps the existing secret
            options[key] = raw.strip()
    else:  # text | select | textarea
        if present:
            v = raw.strip()
            if v:
                options[key] = v
            else:
                options.pop(key, None)


def _section_from_form(form, oi: int, original: SectionConfig | None) -> SectionConfig:
    p = f"sec-{oi}-"
    type_ = form.get(p + "type") or (original.type if original else "joke")
    spec = SECTION_SPECS.get(type_)
    options = dict(original.options) if original else {}

    for field in (spec.fields if spec else []):
        _coerce(field, form.get(p + field.key), options)

    # Header icon (stored in options["icon"]); only persist when it differs from
    # the type's default, so config stays minimal but "" can disable a default.
    icon = form.get(p + "icon", "")
    default_icon = DEFAULT_SECTION_ICONS.get(type_, "")
    if icon != default_icon:
        options["icon"] = icon
    else:
        options.pop("icon", None)

    title = (form.get(p + "title") or "").strip() or None
    enabled = (p + "enabled") in form
    return SectionConfig(type=type_, title=title, enabled=enabled, options=options)


def apply_section_form(form, original_sections, skip: int | None = None) -> list[SectionConfig]:
    """Rebuild a brief's section list from the editor form, honoring `order`.

    `skip` drops that original index (used by the per-section delete button).
    """
    by_index = {i: s for i, s in enumerate(original_sections)}
    order_raw = form.get("order", "")
    order = [int(x) for x in order_raw.split(",") if x.strip().isdigit()]
    if not order:  # no JS / empty: keep original order
        order = list(by_index)
    return [_section_from_form(form, oi, by_index.get(oi)) for oi in order if oi != skip]


def _set_int(form, key, default):
    raw = (form.get(key) or "").strip()
    try:
        return int(raw, 0) if raw else default  # int(.,0) handles "0x1d81"
    except ValueError:
        return default


def _set_float(form, key, default):
    raw = (form.get(key) or "").strip()
    try:
        return float(raw) if raw else default
    except ValueError:
        return default


def parse_globals_form(form, cfg) -> None:
    """Update global config sections (printer/location/render/claude/network)."""
    cfg.printer.backend = form.get("printer_backend", cfg.printer.backend)
    cfg.printer.usb.vendor_id = _set_int(form, "usb_vendor_id", cfg.printer.usb.vendor_id)
    cfg.printer.usb.product_id = _set_int(form, "usb_product_id", cfg.printer.usb.product_id)
    cfg.printer.serial.port = form.get("serial_port", cfg.printer.serial.port).strip()
    cfg.printer.serial.baudrate = _set_int(form, "serial_baudrate", cfg.printer.serial.baudrate)

    cfg.location.lat = _set_float(form, "lat", cfg.location.lat)
    cfg.location.lon = _set_float(form, "lon", cfg.location.lon)
    cfg.location.tz = form.get("tz", cfg.location.tz).strip() or "UTC"

    cfg.render.dot_width = _set_int(form, "dot_width", cfg.render.dot_width)
    cfg.render.body_size = _set_int(form, "body_size", cfg.render.body_size)
    cfg.render.heading_size = _set_int(form, "heading_size", cfg.render.heading_size)
    cfg.render.margin = _set_int(form, "margin", cfg.render.margin)
    cfg.render.time_format = "12h" if form.get("time_format") == "12h" else "24h"
    cfg.render.temp_unit = "F" if form.get("temp_unit") == "F" else "C"

    cfg.claude.enabled = "claude_enabled" in form  # checkbox: present == on
    if form.get("claude_api_key"):  # blank keeps existing
        cfg.claude.api_key = form["claude_api_key"].strip()
    cfg.claude.model = form.get("claude_model", cfg.claude.model).strip()

    cfg.email.enabled = "email_enabled" in form
    cfg.email.imap_host = form.get("email_imap_host", cfg.email.imap_host).strip()
    cfg.email.imap_port = _set_int(form, "email_imap_port", cfg.email.imap_port)
    cfg.email.username = (form.get("email_username") or "").strip() or None
    if form.get("email_password"):  # blank keeps existing secret
        cfg.email.password = form["email_password"].strip()
    cfg.email.allowed_senders = [
        s.strip() for s in re.split(r"[\n,]", form.get("email_allowed_senders", "")) if s.strip()
    ]
    cfg.email.require_auth = "email_require_auth" in form
    cfg.email.max_chars = _set_int(form, "email_max_chars", cfg.email.max_chars)
    cfg.email.print_images = "email_print_images" in form
    cfg.email.mark_read = "email_mark_read" in form
    cfg.email.poll_seconds = _set_int(form, "email_poll_seconds", cfg.email.poll_seconds)

    cfg.network.ap_ssid = form.get("ap_ssid", cfg.network.ap_ssid).strip()
    if form.get("ap_password"):
        cfg.network.ap_password = form["ap_password"].strip()
    cfg.network.console_host = form.get("console_host", cfg.network.console_host).strip()
    gpio = (form.get("button_gpio") or "").strip()
    cfg.network.button_gpio = int(gpio) if gpio.isdigit() else None
