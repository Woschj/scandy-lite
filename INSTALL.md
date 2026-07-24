# Scandy-Lite — Installationsanleitung

Zwei unterstützte Wege: **Proxmox VE als natives LXC** (empfohlen für einen
dauerhaften Server-Betrieb, kein Docker nötig) oder **Docker/Portainer**
(läuft auf jedem Docker-Host, auch innerhalb einer LXC).

## Proxmox VE (LXC, empfohlen)

Ein eigenes, an die community-scripts-Konvention angelehntes Skript
(`proxmox/`-Ordner in diesem Repo) erstellt eine frische Debian-LXC per
`pct create` (bewusst ohne deren `build.func` - siehe Kommentar am Kopf von
`proxmox/ct/scandy-lite.sh`) und installiert darin alles nativ: Python,
PostgreSQL, die App selbst als systemd-Dienst - **kein Docker, kein
Portainer**.

**Auf der Proxmox-Host-Shell** (Datacenter → Node → Shell, als root):

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/Woschj/scandy-lite/master/proxmox/ct/scandy-lite.sh)"
```

Das Skript fragt zuerst nach einer bestehenden Container-ID (leer lassen für
eine Neuinstallation, siehe "Updates einspielen" unten), dann interaktiv
Container-ID/Hostname/CPU/RAM/Disk/Storage/Netzwerk-Bridge ab (Defaults: 2
Kerne, 1 GB RAM, 6 GB Disk, `local-lvm`/`local`/`vmbr0` - für den üblichen
Werkstatt-Betrieb reichlich, einfach Enter drücken um zu übernehmen). Danach
erstellt es die LXC automatisch und führt darin aus:

1. PostgreSQL installieren + Datenbank/User anlegen (zufälliges Passwort)
2. Repo nach `/opt/scandy-lite` klonen (Branch `master`), venv + Abhängigkeiten
3. Selbstsigniertes TLS-Zertifikat erzeugen (für Kamera-Scan nötig, siehe unten)
4. `.env` mit generiertem `SECRET_KEY` + DB-Zugangsdaten schreiben
5. Alembic-Migrationen anwenden, ersten Admin-User anlegen
6. Zwei systemd-Dienste starten: `scandy-lite` (HTTP, Port 8000) und
   `scandy-lite-https` (HTTPS, Port 8443, per uvicorns eingebautem
   `--ssl-keyfile`/`--ssl-certfile` - kein separater Reverse-Proxy nötig)

Am Ende zeigt das Skript die Container-IP sowie die beiden URLs an:

- **HTTP** (`http://<IP>:8000`) - für Hardware-Scanner/Tastatur-Eingabe
- **HTTPS** (`https://<IP>:8443`) - nötig für den Kamera-Scan (Browser
  verweigern Kamerazugriff über reines HTTP außer auf `localhost`); zeigt
  eine Zertifikatswarnung (selbstsigniert) - einmalig pro Gerät "Erweitert →
  Trotzdem fortfahren" bestätigen

Admin-Zugangsdaten (`admin` + generiertes Passwort) stehen in
`/root/scandy-lite.creds` **innerhalb der Container** (`pct exec <ID> --
cat /root/scandy-lite.creds` auf dem Proxmox-Host, danach dort löschen). Das
generierte Root-Passwort des Containers selbst (für Konsole/`pct enter`)
zeigt das Skript direkt am Ende einmalig an - notieren, es wird sonst
nirgends gespeichert.

### Updates einspielen (LXC)

Dasselbe One-Liner-Kommando erneut auf dem Proxmox-Host ausführen und bei der
Frage nach einer bestehenden Container-ID die ID der laufenden
Scandy-Lite-Installation eingeben (z.B. `pct list` zeigt sie an). Das Skript
vergleicht dann den lokalen Stand im Container per `git fetch` gegen
`origin/master`, spielt bei Bedarf neue Abhängigkeiten + Migrationen ein und
startet die Dienste neu. Ohne Änderungen auf `master` meldet es "Bereits
aktuell" und tut sonst nichts.

### Backup & Restore (LXC)

```bash
# Im Container (pct enter <ID>):
sudo -u postgres pg_dump scandy_lite | gzip > scandy_lite_$(date +%F).sql.gz
tar czf uploads_$(date +%F).tar.gz -C /opt/scandy-lite uploads
```

Restore: Dienste stoppen (`systemctl stop scandy-lite scandy-lite-https`),
dann `gunzip -c <backup>.sql.gz | sudo -u postgres psql scandy_lite`, danach
Dienste wieder starten. Am einfachsten zusätzlich über Proxmox selbst
sichern: reguläre **LXC-Backups** (Datacenter → Backup) sichern Datenbank
und Uploads gemeinsam, ohne manuelles Skripting.

### Fehlerbehebung (LXC)

| Symptom | Ursache | Lösung |
|---|---|---|
| Dienst startet nicht | Logs prüfen | `journalctl -u scandy-lite -n 50` bzw. `-u scandy-lite-https` |
| Kamera-Button zeigt "benötigt HTTPS" | Zugriff über Port 8000 (HTTP) statt 8443 | über `https://<IP>:8443` aufrufen |
| Login-Loop | siehe Docker-Abschnitt unten - gleiche Ursache/Lösung, `.env` liegt hier unter `/opt/scandy-lite/.env` |

## Alternative: Docker/Portainer

Für alle, die schon einen Docker-Host betreiben (egal ob eigener Server,
Synology/QNAP oder eine generische, nicht-Proxmox-LXC) oder Portainer als
UI bevorzugen.

### Kurzstart (lokal, ohne Portainer)

Für einen schnellen lokalen Test oder eine Installation ohne Portainer reicht:

```bash
git clone <repo-url> && cd scandy-lite
./install.sh          # Linux/Mac
# oder: .\install.ps1   # Windows (PowerShell)
```

Erzeugt automatisch eine `.env` mit sicheren, zufällig generierten Werten
(`SECRET_KEY`, `POSTGRES_PASSWORD`, `ADMIN_PASSWORD`), baut und startet den
Stack, wartet auf den ersten erfolgreichen Health-Check und zeigt danach
URL + Admin-Zugangsdaten an. Erneutes Ausführen ist gefahrlos (eine bereits
vorhandene `.env` wird nicht überschrieben).

Der Rest dieses Abschnitts beschreibt den **Portainer-Weg** (empfohlen für
einen dauerhaften Server-Betrieb per Docker) im Detail.

### Voraussetzungen

- Portainer läuft bereits auf eurem Docker-Host (Proxmox-LXC o. ä.)
- Das `scandy-lite`-Repo ist auf GitHub gepusht (Branch: `master`)
- Der Docker-Host hat Internetzugriff (zum Bauen des Images: PyPI-Pakete;
  zum Ziehen von `postgres:16-alpine` und `caddy:2-alpine`)

### 1. Stack in Portainer anlegen

**Stacks → Add stack**

| Feld | Wert |
|---|---|
| Name | z. B. `scandylite` |
| Build method | **Repository** |
| Repository URL | euer GitHub-Repo, z. B. `https://github.com/Woschj/scandy-lite.git` |
| Repository reference | `refs/heads/master` (**wichtig** - nicht `main`, sonst "reference not found") |
| Compose path | `compose.yaml` |

### 2. Umgebungsvariablen setzen

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

### 3. Erststart abwarten

Der App-Container macht beim ersten Start automatisch:
1. Warten, bis Postgres bereit ist
2. Alembic-Migrationen anwenden (Datenbank-Schema aufbauen)
3. Admin-User + Default-Abteilung anlegen (aus `ADMIN_USERNAME`/`ADMIN_PASSWORD`)
4. App starten

Das kann beim allerersten Mal 1-2 Minuten dauern (Dependencies installieren
beim Image-Build). Container-Logs (`scandylite-app-1 → Logs`) zeigen den
Fortschritt.

### 4. Aufrufen

- **Normal (HTTP, Hardware-Scanner/Tastatur):** `http://<server-ip>:<APP_PORT>`
  z. B. `http://192.168.178.78:8010`
- **Für Kamera-Scan (HTTPS nötig):** `https://<server-ip>:<APP_HTTPS_PORT>`
  z. B. `https://192.168.178.78:8443`
  → Browser zeigt eine Zertifikatswarnung (selbstsigniert, kein Let's Encrypt)
  → **einmalig pro Gerät**: "Erweitert" → "Trotzdem fortfahren"
  → danach normal nutzbar, inkl. Kamera-Button auf `/scan`

Beide Zugänge funktionieren parallel und teilen sich dieselbe Datenbank -
kein Unterschied in den Daten, nur ob Kamera-Scan verfügbar ist.

### 5. Einloggen

Mit `ADMIN_USERNAME`/`ADMIN_PASSWORD` unter `/auth/login` anmelden.

**Danach:** `ADMIN_PASSWORD` in Portainer wieder leeren und den Stack neu
deployen (Passwort steht sonst dauerhaft im Klartext in der Stack-Konfiguration).
Das Admin-Konto bleibt bestehen, es wird nur nicht erneut angelegt/überschrieben.

### Optional: SSO-Login über Authentik

Zusätzlich zum lokalen Login lässt sich ein "Mit Authentik anmelden"-Button
aktivieren - siehe [SSO_AUTHENTIK.md](SSO_AUTHENTIK.md) für die komplette
Einrichtung (Authentik-Seite + drei Umgebungsvariablen hier). Ohne diese
Variablen bleibt das Feature einfach aus, keine Pflicht.

### Backup & Restore

Alle Daten (Gegenstände, Verbrauchsmaterial, Historie, Benutzer) liegen in
der Postgres-Datenbank im `scandy_lite_db_data`-Volume - hochgeladene Bilder
zusätzlich im `uploads`-Volume (siehe `compose.yaml`). Kein
automatisches Backup ist eingerichtet; für ein produktiv genutztes
Ausleihsystem sollte mindestens eines der beiden folgenden Verfahren
regelmäßig (z.B. täglich per Cron auf dem Host) laufen.

**Backup (Datenbank):**

```bash
# Container-Name über die Portainer-UI (Stacks → scandylite → Container)
# oder per `docker ps` ermitteln - je nach Compose-Projektname z.B.
# "scandylite-db-1", NICHT einfach "db".
docker exec <db-container> pg_dump -U scandy scandy_lite | gzip > scandy_lite_$(date +%F).sql.gz
```

`scandy`/`scandy_lite` sind die Compose-Defaults - bei eigenem
`POSTGRES_USER`/`POSTGRES_DB` entsprechend anpassen. Alte Backups selbst
rotieren (z.B. `find . -name '*.sql.gz' -mtime +30 -delete`).

**Backup (Bilder):** `/uploads`-Volume regelmäßig sichern, z.B.
`docker run --rm -v scandy_lite_uploads:/data -v $(pwd):/backup alpine tar czf /backup/uploads_$(date +%F).tar.gz -C /data .`
(Volume-Name ggf. an den tatsächlichen Compose-Projektnamen anpassen, siehe
`docker volume ls`).

**Restore (Datenbank):** Stack stoppen (verhindert Schreibzugriffe während
der Wiederherstellung), dann:

```bash
gunzip -c scandy_lite_2026-07-21.sql.gz | docker exec -i <db-container> psql -U scandy -d scandy_lite
```

Restore einmal auf einer Testumgebung durchspielen, statt sich erst im
Ernstfall darauf zu verlassen, dass das Backup tatsächlich funktioniert.

### Updates einspielen

Nach jedem `git push` auf `master`:

**Stacks → scandylite → Editor → Update the stack**, dabei **"Re-pull
image"**/**Rebuild** aktivieren (Portainer muss das Repo neu klonen und das
Image neu bauen, sonst läuft der alte Code weiter). Migrationen laufen beim
Neustart automatisch mit - kein manueller Schritt nötig.

### Fehlerbehebung

| Symptom | Wahrscheinliche Ursache | Lösung |
|---|---|---|
| "reference not found" beim Deploy | Repository reference falsch/leer | `refs/heads/master` explizit eintragen |
| "port is already allocated" | Port doppelt belegt | `APP_PORT`/`APP_HTTPS_PORT` ändern |
| Login-Loop (immer zurück zu `/auth/login`) | `SESSION_COOKIE_SECURE=true` bei reinem HTTP-Zugriff | auf `false` setzen |
| Container "unhealthy", App reagiert nicht/langsam | Meist Host-Ressourcen-Engpass (I/O, CPU), kein App-Bug | `cat /proc/pressure/io` auf dem Host prüfen |
| Kamera-Button zeigt "benötigt HTTPS" | Zugriff über `APP_PORT` (HTTP) statt `APP_HTTPS_PORT` | über `https://...:8443` aufrufen |
| App-Container startet gar nicht, Log zeigt "SECRET_KEY ist nicht sicher gesetzt" | `SECRET_KEY` fehlt oder ist noch der Standardwert | echten Wert setzen (`openssl rand -hex 32`), Stack neu deployen - **Absicht**, kein Bug: ein vergessener Schlüssel würde sonst Logins/CSRF-Schutz/gespeicherte SMTP-Passwörter angreifbar machen |
| App-Container startet gar nicht, Log zeigt "DATABASE_URL enthält noch das unsichere Standard-Passwort" | `POSTGRES_PASSWORD` fehlt oder ist noch `change_me_immediately` | echtes Passwort in der `.env` setzen, Stack neu deployen - **Absicht**, kein Bug: ein vergessenes Passwort würde die Datenbank sonst für jeden mit Netzwerkzugriff offenlassen |

### Fortgeschritten: Docker/Swarm-Secrets statt Umgebungsvariablen

Für den normalen Portainer-Einzelserver-Betrieb sind die Umgebungsvariablen
oben völlig ausreichend. Wer stattdessen echte Docker-Secrets nutzen möchte
(z.B. unter Docker Swarm, oder weil ein Secrets-Manager schon Dateien statt
Umgebungsvariablen ausliefert): siehe `compose.secrets.yaml` und
`secrets/README.md` im Repo. Kurzfassung:

```bash
openssl rand -hex 32 > secrets/secret_key.txt
openssl rand -hex 24 > secrets/postgres_password.txt
openssl rand -hex 12 > secrets/admin_password.txt
docker compose -f compose.yaml -f compose.secrets.yaml up -d --build
```

`docker/entrypoint.sh` löst die `*_FILE`-Variablen automatisch auf - der
Rest der App merkt keinen Unterschied zur gewöhnlichen Umgebungsvariable.

## CI

Jeder Push/Pull-Request auf `master` läuft automatisch durch
`.github/workflows/ci.yml`: die komplette Testsuite (`pytest`, gegen SQLite,
kein externer Service nötig) plus ein Docker-Build-Check (stellt sicher,
dass das Image überhaupt baubar bleibt). Linting (`ruff check .`) läuft
bewusst nicht in CI, siehe `ruff.toml` - nur als lokales Werkzeug gedacht.
