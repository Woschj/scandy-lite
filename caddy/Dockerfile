# Eigenes, minimales Image statt Caddyfile per Runtime-Bind-Mount reinzureichen.
# Grund: Docker-Bind-Mounts auf eine einzelne Datei sind fehleranfällig, sobald
# der Host-Pfad aus irgendeinem Grund (z.B. Windows-Kopiervorgang beim manuellen
# Einspielen) als Verzeichnis statt Datei existiert - genau das ist hier passiert
# ("not a directory" Mount-Fehler). Da Portainer den App-Container ohnehin
# zuverlässig aus dem Repo baut, nutzen wir denselben Mechanismus für Caddy.
FROM caddy:2-alpine
COPY Caddyfile /etc/caddy/Caddyfile
