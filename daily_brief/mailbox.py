"""Watch a mailbox and print approved email as it arrives.

Independent of briefs and schedules: the daemon calls `poll_and_print()` on an
interval (`[email] poll_seconds`). Each new unread message from an approved
sender is rendered as its own receipt and printed immediately, then marked read
so it prints only once. The mailbox itself is the queue and the "already
printed" state — there's no local state file.

Security note: an email `From:` header is trivially forgeable, so the allow-list
alone is a soft gate. With `require_auth` on (the default) we additionally
require the receiving provider's `Authentication-Results` to show DKIM or DMARC
*pass* — Gmail stamps these — which rejects almost all spoofing, since a forged
From won't carry a valid DKIM signature for its domain. SPF-pass alone is not
trusted (it authenticates the envelope, not the visible From).

Configure under `[email]` (see `config.EmailConfig` / `config.example.toml`).
For Gmail: enable IMAP and create an App Password (the account password won't
work with 2FA), and use a dedicated, unpublished address so the allow-list
isn't the only thing between strangers and your printer.
"""

from __future__ import annotations

import email
import imaplib
import io
import logging
import re
from datetime import datetime
from email.header import decode_header, make_header
from email.message import Message
from email.utils import parseaddr, parsedate_to_datetime

from .brief import Brief, KeyVal, Picture, Section, Text
from .config import Config, EmailConfig
from .render import render_brief

log = logging.getLogger("daily_brief.mailbox")

IMAP_TIMEOUT = 10  # never hang on a slow/offline mailbox


def poll_and_print(config: Config, *, now: datetime | None = None) -> int:
    """Print every new approved message in the inbox. Returns how many printed.

    No-ops (returns 0) when the feature is inactive or the mailbox is
    unreachable, so it's safe to call on a loop from the often-offline Pi.
    """
    ec = config.email
    if not ec.active:
        return 0

    allowed = [s.strip().lower() for s in ec.allowed_senders if s.strip()]
    try:
        conn = imaplib.IMAP4_SSL(ec.imap_host, ec.imap_port, timeout=IMAP_TIMEOUT)
    except (OSError, imaplib.IMAP4.error) as exc:
        log.warning("cannot reach %s:%s (%s)", ec.imap_host, ec.imap_port, exc)
        return 0

    printed = 0
    printer = None
    try:
        conn.login(ec.username, ec.password)
        conn.select("INBOX")
        typ, data = conn.uid("search", None, "UNSEEN")
        if typ != "OK" or not data or not data[0]:
            return 0

        for uid in data[0].split():  # oldest first, in arrival order
            typ, raw = conn.uid("fetch", uid, "(RFC822)")
            if typ != "OK" or not raw or not raw[0]:
                continue
            msg = email.message_from_bytes(raw[0][1])

            _, from_addr = parseaddr(msg.get("From", ""))
            if not _sender_allowed(from_addr, allowed):
                continue
            if ec.require_auth and not _auth_ok(msg):
                log.warning("dropping unauthenticated message from %s", from_addr)
                continue

            section = _section_for(msg, ec, config.render)
            brief = Brief(date=now or datetime.now(), sections=[section])

            # Open the printer lazily, only once we actually have mail to print.
            if printer is None:
                from .printer import open_printer

                printer = open_printer(config.printer).__enter__()
            render_brief(printer, brief, config.render, footer=False, printer_cfg=config.printer)
            printed += 1

            if ec.mark_read:
                conn.uid("store", uid, "+FLAGS", "(\\Seen)")
    except (OSError, imaplib.IMAP4.error) as exc:
        log.warning("IMAP error (%s)", exc)
    finally:
        if printer is not None:
            try:
                printer.close()
            except Exception:
                pass
        try:
            conn.logout()
        except (OSError, imaplib.IMAP4.error):
            pass

    if printed:
        log.info("printed %d new message(s)", printed)
    return printed


# --- message -> printable section ------------------------------------------


def _section_for(msg: Message, ec: EmailConfig, render) -> Section:
    from_name, from_addr = parseaddr(msg.get("From", ""))
    items: list = [KeyVal("From", _decode(from_name) or from_addr)]

    subject = _decode(msg.get("Subject"))
    items.append(KeyVal("Subject", subject) if subject else KeyVal("Subject", "(no subject)"))

    try:
        received = parsedate_to_datetime(msg.get("Date"))
        if received is not None:
            items.append(KeyVal("Received", render.format_time(received)))
    except (TypeError, ValueError):
        pass

    body = _extract_body(msg)
    if len(body) > ec.max_chars:
        body = body[: ec.max_chars].rstrip() + "…"
    if body:
        items.append(Text(body))

    if ec.print_images:
        items.extend(_extract_images(msg))

    return Section("MESSAGE", items)


# --- helpers ---------------------------------------------------------------


def _sender_allowed(addr: str, allowed: list[str]) -> bool:
    addr = (addr or "").strip().lower()
    if not addr:
        return False
    domain = "@" + addr.split("@", 1)[1] if "@" in addr else ""
    for entry in allowed:
        if entry.startswith("@"):  # whole-domain allow, e.g. "@example.com"
            if domain == entry:
                return True
        elif addr == entry:
            return True
    return False


def _auth_ok(msg: Message) -> bool:
    """True if a provider Authentication-Results header shows DKIM/DMARC pass.

    SPF-pass alone is intentionally not accepted: it authenticates the envelope
    sender, not the visible From, so it doesn't defend against From spoofing.
    """
    for header in msg.get_all("Authentication-Results", []):
        h = header.lower()
        if re.search(r"\bdkim=pass\b", h) or re.search(r"\bdmarc=pass\b", h):
            return True
    return False


def _decode(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value))).strip()
    except (ValueError, LookupError):
        return value.strip()


def _extract_body(msg: Message) -> str:
    """Best plain-text body: prefer text/plain, fall back to stripped HTML."""
    plain, html = None, None
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        if part.get_filename():  # an attachment, not body
            continue
        ctype = part.get_content_type()
        if ctype == "text/plain" and plain is None:
            plain = _part_text(part)
        elif ctype == "text/html" and html is None:
            html = _part_text(part)
    text = plain if plain else _strip_html(html or "")
    # Collapse the runs of blank lines email bodies are full of.
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _part_text(part: Message) -> str:
    payload = part.get_payload(decode=True)
    if payload is None:
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except (LookupError, ValueError):
        return payload.decode("utf-8", errors="replace")


def _strip_html(html: str) -> str:
    html = re.sub(r"(?is)<(script|style).*?</\1>", "", html)
    html = re.sub(r"(?i)<br\s*/?>", "\n", html)
    html = re.sub(r"(?i)</p>", "\n\n", html)
    text = re.sub(r"(?s)<[^>]+>", "", html)
    return re.sub(r"[ \t]+", " ", text)


def _extract_images(msg: Message) -> list:
    from PIL import Image  # local: keep PIL out of import cost when unused

    items: list = []
    for part in msg.walk():
        if part.get_content_maintype() != "image":
            continue
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        try:
            img = Image.open(io.BytesIO(payload))
            img.load()
        except Exception as exc:  # any decode failure -> just skip the image
            log.warning("skipping undecodable image (%s)", exc)
            continue
        items.append(Picture(img))
    return items
