#!/usr/bin/env bash

# Scandy-Lite - eigenes Installer-Skript im Projekt-Repo, geschrieben im Stil
# der community-scripts-Konvention (ct/*.sh + install/*-install.sh), nutzt
# deren geteilte Helper-Funktionen (setup_postgresql, setup_postgresql_db,
# create_self_signed_cert, msg_info/msg_ok, ...) aus misc/tools.func +
# misc/install.func. KEIN offizieller community-scripts-Eintrag - läuft nur
# gegen dieses Repo (https://github.com/Woschj/scandy-lite).
#
# Läuft innerhalb der frisch erstellten LXC (per `pct exec` aufgerufen von
# proxmox/ct/scandy-lite.sh). Lädt misc/install.func selbst nach - anders
# als bei einem offiziellen community-scripts-Eintrag steht FUNCTIONS_FILE_PATH
# hier NICHT schon vorbereitet zur Verfügung (das würde build_container()
# übernehmen, die wir bewusst nicht nutzen - siehe ct/scandy-lite.sh).
# misc/install.func lädt intern (über update_os) automatisch noch
# misc/tools.func nach, das ist derselbe Ablauf wie in jedem offiziellen
# install/*-install.sh.

source <(curl -fsSL https://raw.githubusercontent.com/community-scripts/ProxmoxVE/main/misc/install.func)
color
verb_ip6
catch_errors
setting_up_container
network_check
update_os

msg_info "Installing Dependencies"
$STD apt-get install -y git python3 python3-venv python3-pip
msg_ok "Installed Dependencies"

PG_VERSION="16" setup_postgresql
PG_DB_NAME="scandy_lite" PG_DB_USER="scandy" setup_postgresql_db

msg_info "Cloning Scandy-Lite"
git clone -q --branch master https://github.com/Woschj/scandy-lite.git /opt/scandy-lite
msg_ok "Cloned Scandy-Lite"

msg_info "Setting up Python environment (kann etwas dauern)"
cd /opt/scandy-lite
python3 -m venv venv
$STD venv/bin/pip install --upgrade pip
$STD venv/bin/pip install -r requirements.txt
mkdir -p uploads
msg_ok "Setup Python environment"

msg_info "Creating self-signed certificate (für Kamera-Scan über HTTPS)"
create_self_signed_cert "scandy-lite"
msg_ok "Created self-signed certificate"

msg_info "Configuring Scandy-Lite"
SECRET_KEY="$(openssl rand -hex 32)"
ADMIN_PASSWORD="$(openssl rand -hex 8)"
cat <<EOF >/opt/scandy-lite/.env
ENV=production
APP_NAME=Scandy-Lite
SECRET_KEY=$SECRET_KEY
DATABASE_URL=postgresql+asyncpg://${PG_DB_USER}:${PG_DB_PASS}@localhost:5432/${PG_DB_NAME}
DATABASE_URL_SYNC=postgresql+psycopg2://${PG_DB_USER}:${PG_DB_PASS}@localhost:5432/${PG_DB_NAME}
ACCESS_TOKEN_EXPIRE_MINUTES=720
# Bewusst false, wie im Docker-Compose-Setup: HTTP (Port 8000, für
# Hardware-Scanner/Tastatur) und HTTPS (Port 8443, für Kamera-Scan) laufen
# parallel gegen dieselbe Datenbank - ein "Secure"-Cookie würde den
# HTTP-Zugang sonst stillschweigend kaputt machen (siehe INSTALL.md).
SESSION_COOKIE_SECURE=false
DEFAULT_DEPARTMENT_CODE=werkstatt
EOF
set -a
. /opt/scandy-lite/.env
set +a
msg_ok "Configured Scandy-Lite"

msg_info "Applying database migrations"
$STD /opt/scandy-lite/venv/bin/alembic upgrade head
msg_ok "Applied database migrations"

msg_info "Creating admin user"
$STD /opt/scandy-lite/venv/bin/python -m scripts.seed_admin \
  --username admin \
  --password "$ADMIN_PASSWORD" \
  --department-code werkstatt \
  --department-name Werkstatt
msg_ok "Created admin user"

cat <<EOF >/root/scandy-lite.creds
Scandy-Lite Admin-Zugangsdaten
===============================
URL (HTTP, Hardware-Scanner/Tastatur):  http://<container-ip>:8000
URL (HTTPS, für Kamera-Scan):           https://<container-ip>:8443

Benutzername: admin
Passwort:     $ADMIN_PASSWORD

Passwort danach über die Benutzerverwaltung ändern und diese Datei löschen
(rm /root/scandy-lite.creds).
EOF
chmod 600 /root/scandy-lite.creds

msg_info "Creating Services"
cat <<EOF >/etc/systemd/system/scandy-lite.service
[Unit]
Description=Scandy-Lite (HTTP)
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
WorkingDirectory=/opt/scandy-lite
ExecStart=/opt/scandy-lite/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Zweiter, unabhängiger uvicorn-Prozess auf einem zweiten Port mit
# TLS-Terminierung direkt über uvicorns eingebautes --ssl-keyfile/--ssl-certfile
# - ersetzt den separaten Caddy-Container aus dem Docker-Setup (dort war
# Caddy ausschließlich für dieses eine selbstsignierte Zertifikat zuständig,
# sonst keine Reverse-Proxy-Funktion nötig).
cat <<EOF >/etc/systemd/system/scandy-lite-https.service
[Unit]
Description=Scandy-Lite (HTTPS, für Kamera-Scan)
After=network.target postgresql.service scandy-lite.service
Requires=postgresql.service

[Service]
Type=simple
WorkingDirectory=/opt/scandy-lite
ExecStart=/opt/scandy-lite/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8443 --ssl-keyfile /etc/ssl/scandy-lite/scandy-lite.key --ssl-certfile /etc/ssl/scandy-lite/scandy-lite.crt
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
systemctl enable -q --now scandy-lite scandy-lite-https
msg_ok "Created Services"

motd_ssh
customize
cleanup_lxc
