"""Setup-mode web app: edit briefs, schedules, and global settings.

Server-rendered Flask (no build step). `create_app()` returns the app; routes
load `config.toml`, apply edits from forms, and write it back via
`config.save_config`. Run standalone for development:

    python -m daily_brief.web            # http://127.0.0.1:8080

On the Pi the daemon starts this in setup mode (see daily_brief.daemon).
"""

from __future__ import annotations

import io
import secrets
from pathlib import Path

from flask import (
    Flask, abort, flash, redirect, render_template, request, send_file, session, url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from ..brief import build_brief
from ..config import (
    DEFAULT_CONFIG_PATH, EXAMPLE_CONFIG_PATH, BriefConfig, ScheduleConfig,
    SectionConfig, load_config, save_config,
)
from ..render import render_brief
from ..sources import (
    AVAILABLE_ICONS, DEFAULT_SECTION_ICONS, SECTION_SPECS, strftime_legend,
)
from .forms import apply_section_form, parse_globals_form

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def create_app(config_path: str | Path | None = None) -> Flask:
    app = Flask(__name__)
    app.config["CONFIG_PATH"] = Path(config_path) if config_path else DEFAULT_CONFIG_PATH

    def load_current():
        path = app.config["CONFIG_PATH"]
        cfg = load_config(path)
        if not cfg.briefs and EXAMPLE_CONFIG_PATH.exists():
            cfg = load_config(EXAMPLE_CONFIG_PATH)  # seed first-run from example
        return cfg

    def store(cfg):
        save_config(cfg, app.config["CONFIG_PATH"])

    # Stable session-signing key: generate once and persist to config.
    _cfg = load_current()
    if not _cfg.web.secret_key:
        _cfg.web.secret_key = secrets.token_hex(32)
        store(_cfg)
    app.secret_key = _cfg.web.secret_key

    # --- auth --------------------------------------------------------------

    @app.before_request
    def _require_auth():
        if request.endpoint in (None, "static"):
            return None
        cfg = load_current()
        if not cfg.web.password_hash:  # first run: force creating a password
            if request.endpoint != "set_password":
                return redirect(url_for("set_password"))
        elif not session.get("auth"):
            if request.endpoint != "login":
                return redirect(url_for("login"))
        return None

    @app.route("/login", methods=["GET", "POST"])
    def login():
        cfg = load_current()
        if request.method == "POST":
            if check_password_hash(cfg.web.password_hash, request.form.get("password", "")):
                session["auth"] = True
                return redirect(url_for("dashboard"))
            flash("Incorrect password.", "error")
        return render_template("login.html")

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.route("/set-password", methods=["GET", "POST"])
    def set_password():
        cfg = load_current()
        changing = bool(cfg.web.password_hash)
        if request.method == "POST":
            pw, pw2 = request.form.get("password", ""), request.form.get("confirm", "")
            if len(pw) < 6:
                flash("Use at least 6 characters.", "error")
            elif pw != pw2:
                flash("Passwords don't match.", "error")
            else:
                cfg.web.password_hash = generate_password_hash(pw)
                store(cfg)
                session["auth"] = True
                flash("Password updated.", "ok")
                return redirect(url_for("dashboard"))
        return render_template("set_password.html", changing=changing)

    @app.route("/")
    def dashboard():
        cfg = load_current()
        return render_template("dashboard.html", cfg=cfg, specs=SECTION_SPECS)

    # --- briefs ------------------------------------------------------------

    @app.route("/brief/new", methods=["POST"])
    def brief_new():
        cfg = load_current()
        name = (request.form.get("name") or "").strip()
        if not name:
            flash("Brief name required.", "error")
        elif cfg.brief(name):
            flash(f"Brief {name!r} already exists.", "error")
        else:
            cfg.briefs.append(BriefConfig(name=name))
            store(cfg)
            return redirect(url_for("brief_edit", name=name))
        return redirect(url_for("dashboard"))

    @app.route("/brief/<name>/delete", methods=["POST"])
    def brief_delete(name):
        cfg = load_current()
        cfg.briefs = [b for b in cfg.briefs if b.name != name]
        store(cfg)
        flash(f"Deleted brief {name!r}.", "ok")
        return redirect(url_for("dashboard"))

    @app.route("/brief/<name>", methods=["GET", "POST"])
    def brief_edit(name):
        cfg = load_current()
        brief = cfg.brief(name)
        if brief is None:
            abort(404)

        if request.method == "POST":
            action = request.form.get("action", "save")
            skip = int(action.split(":", 1)[1]) if action.startswith("delete:") else None
            brief.sections = apply_section_form(request.form, brief.sections, skip=skip)
            if action == "add":
                brief.sections.append(SectionConfig(type=request.form.get("add_type", "joke")))
            store(cfg)
            flash("Saved." if action == "save" else f"Done ({action}).", "ok")
            return redirect(url_for("brief_edit", name=name))

        return render_template(
            "brief.html", cfg=cfg, brief=brief, specs=SECTION_SPECS,
            default_icons=DEFAULT_SECTION_ICONS, icons=AVAILABLE_ICONS,
            strftime_legend=strftime_legend(),
        )

    # --- schedules ---------------------------------------------------------

    @app.route("/schedules", methods=["GET", "POST"])
    def schedules():
        cfg = load_current()
        if request.method == "POST":
            action = request.form.get("action", "save")
            new = []
            i = 0
            while f"sch-{i}-brief" in request.form:
                p = f"sch-{i}-"
                new.append(ScheduleConfig(
                    name=(request.form.get(p + "name") or "Schedule").strip(),
                    brief=request.form.get(p + "brief", ""),
                    time=(request.form.get(p + "time") or "07:30").strip(),
                    days=[d for d in DAYS if f"{p}day-{d}" in request.form],
                    enabled=(p + "enabled") in request.form,
                ))
                i += 1
            cfg.schedules = [s for s in new if s.brief]
            if action == "add":
                first = cfg.briefs[0].name if cfg.briefs else ""
                cfg.schedules.append(ScheduleConfig(name="New schedule", brief=first))
            elif action.startswith("delete:"):
                idx = int(action.split(":", 1)[1])
                if 0 <= idx < len(cfg.schedules):
                    del cfg.schedules[idx]
            store(cfg)
            flash("Saved.", "ok")
            return redirect(url_for("schedules"))
        return render_template("schedules.html", cfg=cfg, days=DAYS)

    # --- global settings ---------------------------------------------------

    @app.route("/settings", methods=["GET", "POST"])
    def settings():
        cfg = load_current()
        if request.method == "POST":
            parse_globals_form(request.form, cfg)
            store(cfg)
            flash("Settings saved.", "ok")
            return redirect(url_for("settings"))
        return render_template("settings.html", cfg=cfg)

    # --- wifi (setup mode) -------------------------------------------------

    @app.route("/wifi", methods=["GET", "POST"])
    def wifi():
        from .. import network

        if request.method == "POST":
            ssid = (request.form.get("ssid") or "").strip()
            if not ssid:
                flash("Choose a network.", "error")
            else:
                ok, msg = network.connect(ssid, request.form.get("password") or None)
                flash(msg, "ok" if ok else "error")
            return redirect(url_for("wifi"))

        avail = network.available()
        return render_template(
            "wifi.html",
            available=avail,
            online=network.is_online() if avail else False,
            current=network.current_ssid() if avail else None,
            nets=network.scan() if avail else [],
        )

    # --- preview / print ---------------------------------------------------

    @app.route("/preview/<name>.png")
    def preview(name):
        cfg = load_current()
        brief = cfg.brief(name)
        if brief is None:
            abort(404)
        if request.args.get("fresh"):  # force a fully fresh rebuild
            from ..sources._http import cache_clear

            cache_clear()
        img = render_brief(None, build_brief(cfg, brief), cfg.render)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return send_file(buf, mimetype="image/png")

    @app.route("/print/<name>", methods=["POST"])
    def print_now(name):
        from .. import lastbrief

        cfg = load_current()
        brief = cfg.brief(name)
        if brief is None:
            abort(404)
        try:
            # Records it as the last brief too, so the button can reprint it.
            lastbrief.print_and_save(cfg, build_brief(cfg, brief))
            flash(f"Printed {name!r}.", "ok")
        except Exception as exc:
            flash(f"Print failed: {exc}", "error")
        return redirect(url_for("dashboard"))

    return app
