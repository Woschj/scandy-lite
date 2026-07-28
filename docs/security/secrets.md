# Secrets

## Grundregel

Keine Zugangsdaten im Repo - weder im Code noch in Beispiel-Configs mit
echten Werten. `.env`, `migration_passwords.txt`, `secrets/*.txt` sind
gitignored (siehe `.gitignore`). `.env.example` enthält nur Platzhalter/
Defaults, nie echte Secrets.

## Woher Secrets kommen

Zwei unterstützte Wege, je nach Deployment:

1. **Gewöhnliche Umgebungsvariablen** (`SECRET_KEY`, `POSTGRES_PASSWORD`,
   `ADMIN_PASSWORD`, ...) - Standardfall für Docker Compose/Portainer.
2. **Docker/Swarm-Secrets** (`*_FILE`-Konvention, z. B.
   `SECRET_KEY_FILE=/run/secrets/scandy_secret_key`) - `docker/entrypoint.sh`
   löst diese automatisch auf (`resolve_secret()`), der Rest der App
   unterscheidet nicht zwischen beiden Wegen. Siehe `compose.secrets.yaml`
   und `secrets/README.md`.

Neue Secrets (z. B. für eine neue Integration) sollten beide Wege
unterstützen, nicht nur den einfacheren - sonst ist die Docker-Secrets-Doku
nach einer Weile inkonsistent mit dem tatsächlichen Code.

## Fail-Fast statt stiller Unsicherheit

Die App startet in Produktion (`ENV=production`) **gar nicht erst**, wenn:

- `SECRET_KEY` fehlt, der Default-Platzhalterwert ist, oder kürzer als
  32 Zeichen ist (ein unsicherer Schlüssel würde Sessions/CSRF-Schutz/
  gespeicherte SMTP-Passwörter angreifbar machen).
- `DATABASE_URL` noch das unsichere Standard-Passwort enthält.

Das ist bewusst kein "Log-Warnung und trotzdem starten" - ein
übersehener Default-Wert darf nicht im Betrieb landen. Neue sicherheits-
relevante Pflicht-Konfiguration sollte demselben Muster folgen
(`app/core/config.py`), nicht nur eine Warnung loggen.

## Session-Cookie

`httponly=True`, `samesite="lax"` fest gesetzt (`app/core/security.py`);
`secure` folgt `SESSION_COOKIE_SECURE` (env-gesteuert, weil dieses Tool
sowohl über reines HTTP im internen Netz als auch über HTTPS - für
Kamera-Zugriff nötig - erreichbar sein muss, siehe
`docs/architecture/frontend.md`).

## Bilder-Uploads

Dateiname = Entity-UUID (`<item-id>.jpg`), **nie** der vom Client
gesendete Dateiname - verhindert Path-Traversal/Namenskollisionen ohne
zusätzliche Prüfung. Jedes Bild wird serverseitig neu dekodiert/reskaliert
und als JPEG neu kodiert (Pillow) statt die Originaldatei roh
durchzureichen - kein potenziell präpariertes Fremdformat landet 1:1 auf
der Platte.
