# Scandy-Lite — Installationsanleitung (Portainer)

Diese Anleitung deckt den kompletten Weg ab: vom leeren GitHub-Repo bis zur
laufenden App inkl. HTTPS für den Kamera-Scan.

## Voraussetzungen

- Portainer läuft bereits auf eurem Docker-Host (Proxmox-LXC o. ä.)
- Das `scandy-lite`-Repo ist auf GitHub gepusht (Branch: `master`)
- Der Docker-Host hat Internetzugriff (zum Bauen des Images: PyPI-Pakete;
  zum Ziehen von `postgres:16-alpine` und `caddy:2-alpine`)

## 1. Stack in Portainer anlegen

**Stacks → Add stack**

| Feld | Wert |
|---|---|
| Name | z. B. `scandylite` |
| Build method | **Repository** |
| Repository URL | euer GitHub-Repo, z. B. `https://github.com/Woschj/scandy-lite.git` |
| Repository reference | `refs/heads/master` (**wichtig** - nicht `main`, sonst "reference not found") |
| Compose path | `docker-compose.yml` |

## 2. Umgebungsvariablen setzen

Im gleichen Formular unter "Environment variables":

| Variable | Beschreibung | Empfehlung |
|---|---|---|
| `APP_PORT` | HTTP-Port (Hardware-Scanner/Tastatur funktionieren hierüber) | frei wählbar, z. B. `8010` |
| `APP_HTTPS_PORT` | HTTPS-Port über Caddy (nötig für Kamera-Scan) | frei wählbar, z. B. `8443` |
| `POSTGRES_USER` | Datenbank-User | `scandy` |
| `POSTGRES_PASSWORD` | Datenbank-Passwort | **echtes Passwort setzen** |
| `POSTGRES_DB` | Datenbankname | `scandy_lite` |
| `SECRET_KEY` | Signierschlüssel für Login-Sessions | **setzen!** z. B. mit `openssl rand -hex 32` erzeugen - die App startet ohne einen echten Wert absichtlich nicht (siehe Fehlerbehebung unten) |
| `SESSION_COOKIE_SECURE` | Cookie nur über HTTPS | `false` lassen (funktioniert für HTTP **und** HTTPS gleichzeitig) |
| `ADMIN_USERNAME` | Login-Name des ersten Admins | z. B. `admin` |
| `ADMIN_PASSWORD` | Passwort dazu | **sicheres Passwort**, nach dem ersten Deploy wieder leeren |
| `DEFAULT_DEPARTMENT_CODE` | Kurzcode der ersten Abteilung | z. B. `werkstatt` |
| `DEFAULT_DEPARTMENT_NAME` | Anzeigename | z. B. `Werkstatt` |

**Deploy the stack** klicken. Portainer klont das Repo, baut das App-Image und
startet drei Container: `db` (Postgres), `app` (FastAPI), `caddy` (HTTPS-Proxy).

## 3. Erststart abwarten

Der App-Container macht beim ersten Start automatisch:
1. Warten, bis Postgres bereit ist
2. Alembic-Migrationen anwenden (Datenbank-Schema aufbauen)
3. Admin-User + Default-Abteilung anlegen (aus `ADMIN_USERNAME`/`ADMIN_PASSWORD`)
4. App starten

Das kann beim allerersten Mal 1-2 Minuten dauern (Dependencies installieren
beim Image-Build). Container-Logs (`scandylite-app-1 → Logs`) zeigen den
Fortschritt.

## 4. Aufrufen

- **Normal (HTTP, Hardware-Scanner/Tastatur):** `http://<server-ip>:<APP_PORT>`
  z. B. `http://192.168.178.78:8010`
- **Für Kamera-Scan (HTTPS nötig):** `https://<server-ip>:<APP_HTTPS_PORT>`
  z. B. `https://192.168.178.78:8443`
  → Browser zeigt eine Zertifikatswarnung (selbstsigniert, kein Let's Encrypt)
  → **einmalig pro Gerät**: "Erweitert" → "Trotzdem fortfahren"
  → danach normal nutzbar, inkl. Kamera-Button auf `/scan`

Beide Zugänge funktionieren parallel und teilen sich dieselbe Datenbank -
kein Unterschied in den Daten, nur ob Kamera-Scan verfügbar ist.

## 5. Einloggen

Mit `ADMIN_USERNAME`/`ADMIN_PASSWORD` unter `/auth/login` anmelden.

**Danach:** `ADMIN_PASSWORD` in Portainer wieder leeren und den Stack neu
deployen (Passwort steht sonst dauerhaft im Klartext in der Stack-Konfiguration).
Das Admin-Konto bleibt bestehen, es wird nur nicht erneut angelegt/überschrieben.

## Updates einspielen

Nach jedem `git push` auf `master`:

**Stacks → scandylite → Editor → Update the stack**, dabei **"Re-pull
image"**/**Rebuild** aktivieren (Portainer muss das Repo neu klonen und das
Image neu bauen, sonst läuft der alte Code weiter). Migrationen laufen beim
Neustart automatisch mit - kein manueller Schritt nötig.

## Fehlerbehebung

| Symptom | Wahrscheinliche Ursache | Lösung |
|---|---|---|
| "reference not found" beim Deploy | Repository reference falsch/leer | `refs/heads/master` explizit eintragen |
| "port is already allocated" | Port doppelt belegt | `APP_PORT`/`APP_HTTPS_PORT` ändern |
| Login-Loop (immer zurück zu `/auth/login`) | `SESSION_COOKIE_SECURE=true` bei reinem HTTP-Zugriff | auf `false` setzen |
| Container "unhealthy", App reagiert nicht/langsam | Meist Host-Ressourcen-Engpass (I/O, CPU), kein App-Bug | `cat /proc/pressure/io` auf dem Host prüfen |
| Kamera-Button zeigt "benötigt HTTPS" | Zugriff über `APP_PORT` (HTTP) statt `APP_HTTPS_PORT` | über `https://...:8443` aufrufen |
| App-Container startet gar nicht, Log zeigt "SECRET_KEY ist nicht sicher gesetzt" | `SECRET_KEY` fehlt oder ist noch der Standardwert | echten Wert setzen (`openssl rand -hex 32`), Stack neu deployen - **Absicht**, kein Bug: ein vergessener Schlüssel würde sonst Logins/CSRF-Schutz/gespeicherte SMTP-Passwörter angreifbar machen |
