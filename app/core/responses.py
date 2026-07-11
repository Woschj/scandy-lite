"""Redirect-Hilfsfunktion mit korrekt escapten Query-Parametern.

Ersetzt das bisherige Muster roher f-Strings (`f"/scan?error={item.name}..."`),
das bei DB-Werten mit Sonderzeichen (`&`, `#`, `%`) die Query-String-Struktur
bricht - `urlencode` escaped zuverlässig und erzeugt weiterhin `+` für
Leerzeichen (gleiche Optik wie die bisherigen manuell verketteten Strings).
"""
from urllib.parse import urlencode

from fastapi.responses import RedirectResponse


def redirect_with_query(url: str, status_code: int = 303, fragment: str = "", **params: str) -> RedirectResponse:
    query = urlencode({k: v for k, v in params.items() if v})
    full_url = f"{url}?{query}" if query else url
    if fragment:
        full_url = f"{full_url}#{fragment}"
    return RedirectResponse(url=full_url, status_code=status_code)
