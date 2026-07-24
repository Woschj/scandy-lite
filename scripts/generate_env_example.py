"""
Generiert .env.example automatisch aus app.core.config.Settings - die Datei
kann dadurch nie mehr veralten/von den tatsächlichen Konfigurationsfeldern
abweichen (was bei einer von Hand gepflegten .env.example über die Zeit
zwangsläufig passiert, sobald neue Felder in Settings dazukommen und das
Aktualisieren der Beispieldatei vergessen wird).

Nutzung:
    python -m scripts.generate_env_example

Kommentare/Gruppierung/Platzhalterwerte kommen aus ENV_DOC unten (von Hand
gepflegt, aber bewusst getrennt von den Feldnamen selbst - ein neues Feld in
Settings taucht automatisch mit seinem Code-Default in der generierten Datei
auf, auch OHNE Eintrag hier; ein Eintrag hier ergänzt nur Kommentar/eigenen
Beispielwert/Gruppierung, erzeugt aber kein Feld, das es in Settings nicht
gibt - ein CI-Check (siehe .github/workflows) prüft genau das).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import Settings  # noqa: E402

# (Feldname, Beispielwert-Override oder None für Code-Default, Kommentar oder None)
# Reihenfolge hier bestimmt die Reihenfolge in der generierten Datei.
_GROUPS: list[tuple[str, list[tuple[str, str | None, str | None]]]] = [
    ("App", [
        ("APP_NAME", None, None),
        ("ENV", None, "development | production - production erzwingt echte SECRET_KEY/POSTGRES_PASSWORD (siehe unten)"),
        ("SECRET_KEY", "change-me-in-production", "Erzeugen mit: openssl rand -hex 32 - siehe INSTALL.md"),
    ]),
    ("Datenbank", [
        ("DATABASE_URL", None, "Async-Verbindung (asyncpg) für die laufende App"),
        ("DATABASE_URL_SYNC", None, "Sync-Verbindung (psycopg2) - wird für Alembic-Migrationen gebraucht"),
    ]),
    ("Auth", [
        ("ACCESS_TOKEN_EXPIRE_MINUTES", None, None),
        ("JWT_ALGORITHM", None, None),
        ("SESSION_COOKIE_NAME", None, None),
        ("SESSION_COOKIE_SECURE", None, "Erst auf true, wenn ein Reverse-Proxy TLS terminiert - sonst Login-Loop über HTTP"),
    ]),
    ("SSO (optional, OpenID Connect - z.B. Authentik)", [
        ("OIDC_ISSUER", "", "Leer lassen = Feature aus, Login-Seite zeigt nur das lokale Formular"),
        ("OIDC_CLIENT_ID", "", None),
        ("OIDC_CLIENT_SECRET", "", None),
        ("OIDC_PROVIDER_NAME", None, "Beschriftung des Login-Buttons, z.B. 'Authentik'"),
    ]),
    ("Multi-Abteilung", [
        ("DEFAULT_DEPARTMENT_CODE", None, None),
    ]),
    ("Bild-Uploads", [
        ("UPLOADS_DIR", None, None),
        ("MAX_UPLOAD_BYTES", None, "vor der Pillow-Verarbeitung"),
        ("IMAGE_MAX_DIMENSION", None, "px, längere Kante"),
    ]),
]


def generate() -> str:
    defaults = Settings.model_construct().model_dump()  # Code-Defaults ohne .env zu lesen
    documented_fields = {name for _, fields in _GROUPS for name, _, _ in fields}
    missing = set(defaults) - documented_fields
    if missing:
        raise SystemExit(
            f"Neue(s) Settings-Feld(er) ohne Eintrag in scripts/generate_env_example.py: {sorted(missing)}\n"
            "Bitte dort (Gruppe + optionaler Kommentar) ergänzen, bevor .env.example neu erzeugt wird."
        )

    lines = ["# Automatisch generiert aus app/core/config.py::Settings - siehe", "# scripts/generate_env_example.py. Nicht von Hand nachpflegen, stattdessen:", "#   python -m scripts.generate_env_example", ""]
    for group_title, fields in _GROUPS:
        lines.append(f"# --- {group_title} ---")
        for name, override, comment in fields:
            if comment:
                lines.append(f"# {comment}")
            value = override if override is not None else defaults[name]
            if isinstance(value, bool):
                value = str(value).lower()
            lines.append(f"{name}={value}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    output_path = Path(__file__).resolve().parents[1] / ".env.example"
    output_path.write_text(generate(), encoding="utf-8")
    print(f"{output_path} aktualisiert.")


if __name__ == "__main__":
    main()
