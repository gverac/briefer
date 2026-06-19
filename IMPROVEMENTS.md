# Potential improvements

A backlog of follow-up features, split by scope. **Minor** = a focused change in
one or two files with little new infrastructure. **Major** = new subsystems,
persistence, or cross-cutting work.

## Minor features

### Carried over from earlier findings
- **"Clear caches" button in Settings.** `cache_clear()` already exists in
  `sources/_http.py`; it's only reachable today via the per-brief Preview button.
  A global one in Settings is a few lines.
- **Split "Preview" vs "Force fresh".** Preview currently always evicts caches
  (`?fresh=1`). Offer a fast cached preview plus an explicit force-fresh.

### Content & display
- **Multi-day weather forecast.** `weather` shows only today's hi/lo; add an
  N-day strip.
- **Apply the time-format setting to the greeting's date line.** Today
  `date_format` is free-form strftime; optionally honor the global 12h/24h choice.

### Brief / section management
- **Duplicate a brief** and **duplicate a section** — common when building
  variants (e.g. morning vs weekend). UI + a route.
- **Confirm-on-remove for sections.** Section "Remove" is instant; briefs already
  confirm on delete.
- **"Last printed" timestamp + result on the dashboard cards.** Small persisted
  bit of state; useful feedback.
- **Test-print / printer-reachable indicator** on the dashboard or Settings
  (wraps `scripts/printer_test.py`).

### Ops niceties
- **Export/import `config.toml`** (download current, upload to restore) — handy
  since the file is gitignored and comments are stripped on save.
- **Dark mode** via `prefers-color-scheme` — the CSS is already fully
  variable-driven, so it's mostly a `:root` override block.

## Major features

### New content sources
Each is a `sources/foo.py` + `SectionSpec`, but collectively a big surface:
RSS/news headlines, stocks/crypto, to-do integrations (Todoist/Google Tasks),
commute/transit times, sports scores, air-quality index, package tracking, a
habit/streak tracker. The plugin architecture (`BUILDERS` + `SECTION_SPECS`)
makes these additive, but each needs API handling, caching, and graceful
degradation.

### Platform / architecture
- **Print history & retry, persisted.** A real log (SQLite or JSONL) of every
  print attempt with status/error, surfaced in the UI with re-print. There's no
  history today. Foundation for failure notifications.
- **Failure notifications.** Push/email when a scheduled print fails (printer
  offline, source down). Builds on the history store.
- **Parallel/async source fetching.** `build_brief` runs sources sequentially in
  `brief.py`; on the Pi Zero 2 W, network sources serialize the whole job.
  Concurrent fetch with per-source timeouts would noticeably speed up builds.
- **REST API + token auth for remote triggering.** A webhook/endpoint to print an
  arbitrary note or trigger a brief from a phone shortcut. Needs auth hardening
  beyond the current single-password session: tokens, rate limiting, optional HTTPS.
- **Ad-hoc "print this text now"** from the phone — a quick-note queue, distinct
  from scheduled briefs.

### Scheduling & theming
- **Richer scheduling:** specific dates, holiday skips, cron-style expressions,
  "skip weekends." Today it's `time` + `days` only (`ScheduleConfig`).
- **Layout/theme engine with live preview:** density presets, swappable fonts,
  per-brief styling — currently a few global `RenderConfig` knobs.

### Quality & i18n
- **Golden-image render tests.** Tests cover config/web/daemon/printer but not the
  bitmap output of `render.py`/sources; snapshot tests would catch layout
  regressions like the checkbox-overflow bug.
- **Localization (i18n)** of the UI and brief copy (greetings, labels), plus
  multi-location/timezone support.
- **OTA/update + backup-restore UI** with config schema versioning/migrations
  (there's already a legacy `[[sections]]`→brief migration to build on).
