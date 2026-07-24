# Secrets für compose.secrets.yaml

Hier erwartet `compose.secrets.yaml` drei Dateien mit dem jeweiligen Wert als
reinem Text (keine Anführungszeichen, kein `KEY=`-Prefix - nur der Wert
selbst, wie ihn auch die App am Ende sieht):

```bash
openssl rand -hex 32 > secrets/secret_key.txt
openssl rand -hex 24 > secrets/postgres_password.txt
openssl rand -hex 12 > secrets/admin_password.txt
```

Diese drei Dateien werden von Git ignoriert (siehe `.gitignore`) - landen nie
im Repo. Nur für Nutzer von `compose.secrets.yaml` relevant, siehe die
Kommentare dort. Für den normalen Portainer-Betrieb ohne Swarm bleibt der
Weg über Umgebungsvariablen in `compose.yaml` einfacher (siehe INSTALL.md).
