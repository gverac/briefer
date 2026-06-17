"""Editable-field schema for each section type.

Drives the setup web UI's forms and save-time validation. Every section also has
the common fields `title` (text), `enabled` (bool), and `icon` (select) handled
by the editor itself; the per-type `fields` below are the type-specific options.
A `bare` spec (the greeting) draws its own centered header, so the editor hides
the Title/Icon fields for it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

# Common strftime codes shown as a legend next to date-format fields, so people
# unfamiliar with strftime can assemble their own line. Examples are rendered
# live from the current time when the legend is built.
STRFTIME_CODES: tuple[tuple[str, str], ...] = (
    ("%A", "Weekday"),
    ("%a", "Weekday, short"),
    ("%d", "Day of month, 01–31"),
    ("%B", "Month"),
    ("%b", "Month, short"),
    ("%m", "Month number, 01–12"),
    ("%Y", "Year, 4-digit"),
    ("%y", "Year, 2-digit"),
    ("%H", "Hour, 24-hour"),
    ("%I", "Hour, 12-hour"),
    ("%M", "Minute"),
    ("%p", "AM / PM"),
)


def strftime_legend(now: datetime | None = None) -> list[tuple[str, str, str]]:
    """Return (code, meaning, live-example) rows for the date-format legend."""
    now = now or datetime.now()
    return [(code, meaning, now.strftime(code)) for code, meaning in STRFTIME_CODES]

# Header icon keys available in assets/icons/ ("" = no icon).
AVAILABLE_ICONS = [
    "", "cake", "calendar", "sun", "cloud", "hourglass", "book", "lightbulb",
    "smiley", "moon", "satellite", "planet", "art", "oncall",
]


@dataclass
class Field:
    key: str
    label: str
    kind: str = "text"  # text | secret | int | bool | select | textarea
    default: object = None
    help: str = ""
    choices: tuple = ()  # for kind == "select"


@dataclass
class SectionSpec:
    type: str
    label: str
    description: str = ""
    requires_claude: bool = False
    bare: bool = False  # renders its own header (greeting) — hide Title/Icon fields
    fields: list[Field] = field(default_factory=list)


SECTION_SPECS: dict[str, SectionSpec] = {
    "greeting": SectionSpec(
        "greeting", "Greeting header", "Big centered greeting + a date line.",
        bare=True,  # draws its own centered header; no section Title/Icon
        fields=[
            Field("use_claude", "Use AI (Claude)", "bool", True,
                  "Claude writes the greeting when AI is on; otherwise a rotating built-in."),
            Field("style", "AI style", "select", "morning",
                  "Ready-made prompt tone (ignored if a custom prompt is set).",
                  choices=("morning", "afternoon", "evening", "weekend")),
            Field("prompt", "Custom AI prompt", "textarea",
                  help="Overrides the style preset."),
            Field("date_format", "Date format", "strftime", "%A, %d %B %Y",
                  "The line under the greeting. Mix codes and plain text, "
                  "e.g. %A, %d %B %Y · %H:%M"),
        ],
    ),
    "weather": SectionSpec(
        "weather", "Weather", "Today's high/low + a pictogram (°C/°F in Settings).",
        fields=[Field("api_key", "OpenWeatherMap API key", "secret",
                      help="Free key from openweathermap.org. Uses [location].")],
    ),
    "birthdays": SectionSpec(
        "birthdays", "Birthdays", "Birthdays from an iCal feed, with checkboxes.",
        fields=[
            Field("ical_url", "iCal URL", "text", help="A published .ics URL (webcal:// ok)."),
            Field("horizon_days", "Look-ahead days", "int", 0, "0 = today only."),
            Field("checkbox", "Show checkboxes", "bool", True),
        ],
    ),
    "events": SectionSpec(
        "events", "Upcoming events", "Events from an iCal feed.",
        fields=[
            Field("ical_url", "iCal URL", "text", help="A published .ics URL (webcal:// ok)."),
            Field("horizon_days", "Days ahead", "int", 3),
            Field("max_items", "Max events", "int", 6),
        ],
    ),
    "lirr": SectionSpec(
        "lirr", "LIRR trains",
        "Next LIRR departures between two stations, with live delays.",
        fields=[
            Field("origin", "From station", "text", "Port Washington",
                  "Station name exactly as it appears in the LIRR schedule."),
            Field("destination", "To station", "text", "Penn Station"),
            Field("count", "How many trains", "int", 4),
            Field("realtime", "Show live delays", "bool", True,
                  "Adds delays from the MTA realtime feed; falls back to schedule."),
        ],
    ),
    "oncall": SectionSpec(
        "oncall", "On-call status", "Whether you're on call, from an iCal feed.",
        fields=[
            Field("ical_url", "iCal URL", "text"),
            Field("keyword", "Match keyword", "text", "primary",
                  "Only events whose title contains this (case-insensitive)."),
            Field("horizon_days", "Look-ahead days", "int", 14),
            Field("hide_when_off", "Hide when not on call", "bool", False),
        ],
    ),
    "onthisday": SectionSpec(
        "onthisday", "On this day", "A historical event for today's date.",
        fields=[
            Field("max_items", "How many", "int", 1),
            Field("min_age_years", "Minimum age (years)", "int", 50,
                  "Skip recent news; only events at least this old."),
        ],
    ),
    "word": SectionSpec(
        "word", "Word of the day", "A rare/SAT word with a definition.",
        fields=[Field("use_claude", "Use AI (Claude)", "bool", True,
                      "Define with Claude (adds an example) when AI is on; "
                      "otherwise use the free dictionary.")],
    ),
    "trivia": SectionSpec(
        "trivia", "Trivia", "A trivia fact.",
        fields=[Field("mode", "Mode", "select", "today", choices=("today", "random"))],
    ),
    "countdown": SectionSpec(
        "countdown", "Countdown",
        "Days remaining until a target date; hides itself once it's passed.",
        fields=[
            Field("target_date", "Target date", "text",
                  help="ISO date, YYYY-MM-DD (e.g. 2026-12-25)."),
            Field("label", "Label", "text",
                  help="What you're counting down to, e.g. Vacation."),
            Field("arrived_message", "Message on the day", "text",
                  help="Printed on the target date. Default: \"<label> is here!\""),
            Field("progress_bar", "Show progress bar", "bool", False,
                  "Draws a bar from the start date to the target. Needs a start date."),
            Field("start_date", "Start date", "text",
                  help="ISO date the countdown began (for the progress bar)."),
        ],
    ),
    "daylight": SectionSpec("daylight", "Daylight", "Sunrise, sunset, and day length."),
    "joke": SectionSpec("joke", "Dad joke", "A dad joke from icanhazdadjoke."),
    "iss": SectionSpec("iss", "ISS tracker", "Live ISS position on a world map."),
    "moon": SectionSpec("moon", "Moon phase", "Tonight's moon phase, drawn."),
    "planets": SectionSpec("planets", "Visible planets", "Planets above the horizon tonight."),
    "ascii": SectionSpec(
        "ascii", "ASCII art", "A daily ASCII-art doodle.",
        fields=[
            Field("use_claude", "Use AI (Claude)", "bool", False,
                  "Draw with Claude when AI is on; otherwise the bundled gallery."),
            Field("subject", "Subject", "text", help="Fixed subject; blank = Claude picks daily."),
        ],
    ),
    "ai": SectionSpec(
        "ai", "AI (custom prompt)", "Your prompt, answered by Claude, length-capped.",
        requires_claude=True,
        fields=[
            Field("prompt", "Prompt", "textarea", help="What Claude should write."),
            Field("max_chars", "Max characters", "int", 280),
        ],
    ),
}
