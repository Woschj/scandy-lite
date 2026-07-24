"""
Stellt sicher, dass .env.example immer zu app.core.config.Settings passt -
verhindert, dass jemand ein neues Settings-Feld hinzufügt und vergisst,
`python -m scripts.generate_env_example` erneut laufen zu lassen (die
generierte Datei würde sonst stillschweigend veralten).
"""
from pathlib import Path

from scripts.generate_env_example import generate

_ENV_EXAMPLE_PATH = Path(__file__).resolve().parents[1] / ".env.example"


def test_env_example_is_up_to_date():
    current = _ENV_EXAMPLE_PATH.read_text(encoding="utf-8")
    expected = generate()
    assert current == expected, (
        ".env.example ist nicht aktuell - bitte `python -m scripts.generate_env_example` "
        "ausführen und das Ergebnis committen."
    )
