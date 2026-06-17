"""Config model: load/save round-trip and legacy migration."""

from __future__ import annotations

from daily_brief.config import load_config, save_config


def test_example_config_has_briefs_and_schedules():
    cfg = load_config("config.example.toml")
    assert [b.name for b in cfg.briefs] == ["morning", "midday-joke"]
    assert any(s.brief == "morning" for s in cfg.schedules)


def test_save_round_trip(tmp_path):
    cfg = load_config("config.example.toml")
    out = tmp_path / "config.toml"
    save_config(cfg, out)
    again = load_config(out)

    assert [b.name for b in again.briefs] == [b.name for b in cfg.briefs]
    m = again.brief("morning")
    assert len(m.sections) == len(cfg.brief("morning").sections)
    # per-section options survive the round-trip
    greeting = next(s for s in m.sections if s.type == "greeting")
    assert greeting.get("date_format") == "%A, %d %B %Y"
    assert [s.name for s in again.schedules] == [s.name for s in cfg.schedules]


def test_email_config_round_trip(tmp_path):
    from daily_brief.config import Config, EmailConfig

    cfg = load_config("config.example.toml")
    cfg.email = EmailConfig(
        enabled=True, username="printer@gmail.com", password="apppw",
        allowed_senders=["alice@example.com", "@fam.example"],
        max_chars=250, poll_seconds=45,
    )
    out = tmp_path / "config.toml"
    save_config(cfg, out)
    again = load_config(out).email

    assert again.enabled and again.active
    assert again.username == "printer@gmail.com" and again.password == "apppw"
    assert again.allowed_senders == ["alice@example.com", "@fam.example"]
    assert again.max_chars == 250 and again.poll_seconds == 45


def test_email_inactive_without_creds():
    from daily_brief.config import EmailConfig

    assert not EmailConfig(enabled=True).active  # no username/password/allow-list
    assert not EmailConfig(enabled=False, username="u", password="p",
                           allowed_senders=["a@b.com"]).active  # disabled


def test_legacy_flat_sections_migrate_to_default_brief(tmp_path):
    legacy = tmp_path / "old.toml"
    legacy.write_text('[[sections]]\ntype="joke"\n[[sections]]\ntype="daylight"\n')
    cfg = load_config(legacy)
    assert len(cfg.briefs) == 1
    assert cfg.briefs[0].name == "default"
    assert [s.type for s in cfg.briefs[0].sections] == ["joke", "daylight"]
