# Authentifizierung &amp; Autorisierung

## Auth-Quellen

`User.auth_source` (Enum) unterscheidet, woher ein Konto verwaltet wird:

- **`local`** - lokales Passwort, bcrypt-gehasht (`app/core/security.py`).
  Der Normalfall.
- **`sso`** - OpenID Connect, aktuell implementiert und getestet gegen
  Authentik (siehe `SSO_AUTHENTIK.md`). Router: `app/routers/oidc.py`,
  Logik: `app/core/oidc.py`. Nur aktiv, wenn `OIDC_ISSUER`/`OIDC_CLIENT_ID`/
  `OIDC_CLIENT_SECRET` gesetzt sind - ohne diese drei Variablen ist die
  Login-Seite rein lokal, keine Codeverzweigung sichtbar.
- **`ldap`** - Enum-Wert existiert im Datenmodell, **es gibt aber keinen
  LDAP-Connector-Code**. Bevor LDAP wirklich angebunden wird: als eigenen,
  neuen Auth-Provider analog zu `app/core/oidc.py` bauen, der `User`-
  Datensätze mit `auth_source="ldap"` erzeugt/synct - kein Umbau des
  bestehenden Schemas nötig, das war der Grund für den Enum-Wert.

Erstanmeldung über SSO für eine bislang unbekannte Person legt automatisch
ein Konto an, aber **gesperrt** (`approved_at IS NULL`) - ein Admin schaltet
es frei und legt dabei Abteilung + Rolle fest. Verhindert, dass ein
funktionierender Identity-Provider allein schon Zugriff gewährt.

## Sessions

Cookie-basiert, kein JWT im Browser (PyJWT wird ausschließlich für
zeitlich begrenzte, einmal verwendbare Passwort-Reset-/Willkommens-Tokens
genutzt, siehe `app/core/password_reset.py` - Ablaufzeit `TOKEN_LIFETIME`,
Hash statt Klartext in der DB via `app/core/crypto.py::hash_token`).
`SECRET_KEY` signiert die Session; siehe `docs/security/secrets.md` für die
Fail-Fast-Regel in Produktion.

## Rollenmodell

Kein Gruppen-Konzept. Zwei Ebenen:

- **`User.is_admin`** - globales Flag, voller Zugriff überall, kein
  Abteilungs-Eintrag nötig.
- **`UserDepartmentRole`** - Rolle (`mitarbeiter`/`nutzer`) direkt pro
  Abteilung. Eine Person kann in mehreren Abteilungen unterschiedliche
  Rollen haben. **Mitarbeiter**: verwalten (anlegen/bearbeiten/löschen),
  scannen, Historie einsehen - spezifisch für die jeweilige Abteilung.
  **Nutzer**: ansehen + reservieren/vormerken.

Zugriffsprüfung zentral in `app/core/access.py`
(`is_staff_in_department`, `get_visible_department_ids`) - neue Router
rufen diese Helfer auf, statt Rollenlogik erneut zu implementieren.

## Rate-Limiting

Einfaches In-Memory-Sliding-Window pro IP (`app/routers/auth.py`,
`collections.deque`), getrennte, unterschiedlich strenge Buckets für
Login-Fehlversuche und "Passwort vergessen"-Anfragen. Kein Redis/externer
Store nötig für ein internes Tool dieser Größenordnung - falls das Projekt
horizontal skaliert werden soll (mehrere App-Instanzen), muss das auf einen
gemeinsamen Store umziehen, sonst zählt jede Instanz für sich.

## CSRF

Eigener Token (nicht von einem Framework mitgeliefert), siehe
`docs/security/owasp.md`.
