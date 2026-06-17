"""Mailbox watcher: allow-list, auth-header gating, and print/mark-read flow."""

from __future__ import annotations

import io
from email.message import EmailMessage

import pytest
from PIL import Image

from daily_brief import mailbox as mb
from daily_brief.config import Config, EmailConfig


def _message(from_addr="alice@example.com", *, auth="dkim=pass", body="hello",
             subject="Hi", with_image=False) -> bytes:
    msg = EmailMessage()
    msg["From"] = f"Alice <{from_addr}>"
    msg["Subject"] = subject
    msg["Date"] = "Mon, 15 Jun 2026 09:30:00 +0000"
    if auth:
        msg["Authentication-Results"] = f"mx.google.com; {auth}"
    msg.set_content(body)
    if with_image:
        img = Image.new("RGB", (20, 10), "white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        msg.add_attachment(buf.getvalue(), maintype="image", subtype="png",
                           filename="p.png")
    return msg.as_bytes()


class FakeIMAP:
    """Minimal imaplib.IMAP4_SSL stand-in serving one fixed message."""

    def __init__(self, raw: bytes | None):
        self.raw = raw
        self.stored: list = []

    def login(self, u, p):
        return ("OK", [])

    def select(self, mailbox):
        return ("OK", [])

    def uid(self, cmd, *args):
        if cmd == "search":
            return ("OK", [b"7" if self.raw is not None else b""])
        if cmd == "fetch":
            return ("OK", [(b"7 (RFC822", self.raw), b")"])
        if cmd == "store":
            self.stored.append(args)
            return ("OK", [])
        return ("NO", [])

    def logout(self):
        return ("OK", [])


@pytest.fixture
def cfg():
    c = Config()
    c.printer.backend = "dummy"
    c.email = EmailConfig(enabled=True, username="p", password="x",
                          allowed_senders=["alice@example.com"])
    return c


def _install(monkeypatch, raw):
    fake = FakeIMAP(raw)
    monkeypatch.setattr(mb.imaplib, "IMAP4_SSL", lambda *a, **k: fake)
    return fake


def test_prints_and_marks_read(monkeypatch, cfg):
    fake = _install(monkeypatch, _message(with_image=True))
    assert mb.poll_and_print(cfg) == 1
    assert fake.stored  # marked \Seen


def test_inactive_is_noop(monkeypatch, cfg):
    cfg.email.enabled = False
    # Should not even construct an IMAP connection.
    monkeypatch.setattr(mb.imaplib, "IMAP4_SSL",
                        lambda *a, **k: pytest.fail("connected while inactive"))
    assert mb.poll_and_print(cfg) == 0


def test_disallowed_sender_skipped(monkeypatch, cfg):
    fake = _install(monkeypatch, _message(from_addr="eve@evil.com"))
    assert mb.poll_and_print(cfg) == 0
    assert not fake.stored


def test_domain_allow_entry(monkeypatch, cfg):
    cfg.email.allowed_senders = ["@example.com"]
    _install(monkeypatch, _message(from_addr="anyone@example.com"))
    assert mb.poll_and_print(cfg) == 1


def test_require_auth_drops_unauthenticated(monkeypatch, cfg):
    fake = _install(monkeypatch, _message(auth="spf=pass; dkim=fail"))
    assert mb.poll_and_print(cfg) == 0
    assert not fake.stored


def test_require_auth_off_allows_unauthenticated(monkeypatch, cfg):
    cfg.email.require_auth = False
    _install(monkeypatch, _message(auth=None))
    assert mb.poll_and_print(cfg) == 1


def test_no_mark_read_when_disabled(monkeypatch, cfg):
    cfg.email.mark_read = False
    fake = _install(monkeypatch, _message())
    assert mb.poll_and_print(cfg) == 1
    assert not fake.stored


def test_unreachable_mailbox_is_noop(monkeypatch, cfg):
    def boom(*a, **k):
        raise OSError("connection refused")

    monkeypatch.setattr(mb.imaplib, "IMAP4_SSL", boom)
    assert mb.poll_and_print(cfg) == 0


def test_body_truncated_to_max_chars(monkeypatch, cfg):
    cfg.email.max_chars = 10
    from email import message_from_bytes
    from daily_brief.brief import Text

    section = mb._section_for(message_from_bytes(_message(body="x" * 50)),
                              cfg.email, cfg.render)
    text = next(i for i in section.items if isinstance(i, Text))
    assert text.text.endswith("…") and len(text.text) <= 11
