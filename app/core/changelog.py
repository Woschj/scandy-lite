"""
Liest CHANGELOG.md ein und parst es fürs Anzeigen unter Einstellungen ->
Changelog. Bewusst ein eigener, kleiner Parser statt einer zusätzlichen
Markdown-Abhängigkeit: das Format (Keep a Changelog: "## [Version] - Datum",
"### Kategorie", "- "-Listenpunkte mit optionaler eingerückter Fortsetzungs-
zeile) legen wir selbst fest und pflegen es auch selbst, ein vollständiger
Markdown-Parser wäre für diesen einen Anwendungsfall Overkill.
"""
import re
from pathlib import Path

from markupsafe import Markup, escape

CHANGELOG_PATH = Path(__file__).resolve().parent.parent.parent / "CHANGELOG.md"

_VERSION_RE = re.compile(r"^##\s+\[(?P<version>[^\]]+)\]\s*-\s*(?P<date>.+)$")
_SECTION_RE = re.compile(r"^###\s+(?P<name>.+)$")

_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_INLINE_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")


def _render_inline(text: str) -> Markup:
    """`code` -> <code>, **bold** -> <strong> - erst escapen (XSS-Schutz,
    falls je ein `<`/`&` in einem Eintrag landet), dann die zwei Muster
    ersetzen, danach als sicher markieren."""
    rendered = str(escape(text))
    rendered = _INLINE_CODE_RE.sub(r"<code>\1</code>", rendered)
    rendered = _INLINE_BOLD_RE.sub(r"<strong>\1</strong>", rendered)
    return Markup(rendered)


def parse_changelog(path: Path = CHANGELOG_PATH) -> list[dict]:
    """Gibt eine Liste von Releases zurück, neueste zuerst (= Reihenfolge im
    File): [{"version": "0.9.0", "date": "2026-07-17",
    "sections": {"Changed": [Markup, ...], ...}}, ...].
    Text vor der ersten "## [Version]"-Zeile (Titel, Format-Hinweis) wird für
    die App-Ansicht ignoriert - der ist fürs Repo/GitHub gedacht."""
    if not path.exists():
        return []

    releases: list[dict] = []
    current_release: dict | None = None
    current_section: list | None = None
    current_item_lines: list[str] | None = None

    def flush_item() -> None:
        nonlocal current_item_lines
        if current_section is not None and current_item_lines:
            current_section.append(_render_inline(" ".join(current_item_lines)))
        current_item_lines = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()

        version_match = _VERSION_RE.match(line)
        if version_match:
            flush_item()
            current_release = {
                "version": version_match.group("version"),
                "date": version_match.group("date").strip(),
                "sections": {},
            }
            releases.append(current_release)
            current_section = None
            continue

        if current_release is None:
            continue  # Intro-Text vor der ersten Version

        section_match = _SECTION_RE.match(line)
        if section_match:
            flush_item()
            current_section = current_release["sections"].setdefault(section_match.group("name"), [])
            continue

        if line.startswith("- "):
            flush_item()
            current_item_lines = [line[2:].strip()]
            continue

        if line.strip():
            if current_item_lines is not None:
                current_item_lines.append(line.strip())
            continue

        flush_item()  # Leerzeile beendet den aktuellen Listenpunkt

    flush_item()
    return releases
