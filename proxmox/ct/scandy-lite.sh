#!/usr/bin/env bash
# Scandy-Lite - Proxmox VE LXC-Installer (eigenes Skript im Projekt-Repo,
# KEIN offizieller community-scripts-Eintrag).
#
# Bewusst OHNE misc/build.func: dessen build_container() lädt das
# App-Installationsskript hart-codiert aus dem offiziellen
# community-scripts/ProxmoxVE-Repo (install/${app}-install.sh) - das würde
# für unser eigenes proxmox/install/scandy-lite-install.sh ins Leere laufen
# (404), weil es dort nicht liegt und nicht liegen kann. Stattdessen wird
# der Container hier direkt per `pct create` angelegt und die App-Installation
# per `pct exec` angestoßen. Die generischen, app-unabhängigen Helper
# (misc/install.func -> darüber misc/tools.func: setup_postgresql,
# create_self_signed_cert, msg_info/msg_ok, ...) werden innerhalb des
# Containers trotzdem wiederverwendet, siehe
# proxmox/install/scandy-lite-install.sh.
#
# Aufruf auf dem Proxmox-Host (als root):
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/Woschj/scandy-lite/master/proxmox/ct/scandy-lite.sh)"
#
# Erneuter Aufruf mit der Container-ID einer bestehenden Installation
# aktualisiert diese stattdessen (git pull gegen master + Migrationen +
# Dienst-Neustart) - siehe INSTALL.md.

set -Eeuo pipefail

APP="Scandy-Lite"
INSTALL_SCRIPT_URL="https://raw.githubusercontent.com/Woschj/scandy-lite/master/proxmox/install/scandy-lite-install.sh"

if [[ $EUID -ne 0 ]]; then
  echo "FEHLER: Bitte als root auf dem Proxmox-Host ausführen." >&2
  exit 1
fi
if ! command -v pct >/dev/null 2>&1; then
  echo "FEHLER: 'pct' wurde nicht gefunden - dieses Skript läuft nur auf einem Proxmox-VE-Host." >&2
  exit 1
fi

echo "=== ${APP} - Proxmox VE LXC-Installer ==="
echo ""
read -r -p "Container-ID einer bestehenden ${APP}-Installation zum Aktualisieren (leer = neu installieren): " EXISTING_CTID

# --- Update-Pfad: gegen einen bereits laufenden Container -----------------
if [[ -n "$EXISTING_CTID" ]]; then
  if ! pct status "$EXISTING_CTID" >/dev/null 2>&1; then
    echo "FEHLER: Container ${EXISTING_CTID} existiert nicht." >&2
    exit 1
  fi
  echo "Prüfe auf Updates in Container ${EXISTING_CTID}..."
  pct exec "$EXISTING_CTID" -- bash -c '
    set -Eeuo pipefail
    if [[ ! -d /opt/scandy-lite ]]; then
      echo "FEHLER: Keine Scandy-Lite-Installation in diesem Container gefunden." >&2
      exit 1
    fi
    cd /opt/scandy-lite
    git fetch -q origin master
    LOCAL_COMMIT=$(git rev-parse HEAD)
    REMOTE_COMMIT=$(git rev-parse origin/master)
    if [[ "$LOCAL_COMMIT" == "$REMOTE_COMMIT" ]]; then
      echo "Bereits aktuell (${LOCAL_COMMIT:0:7})."
      exit 0
    fi
    echo "Update verfügbar: ${LOCAL_COMMIT:0:7} -> ${REMOTE_COMMIT:0:7}"
    systemctl stop scandy-lite scandy-lite-https
    git reset -q --hard origin/master
    venv/bin/pip install -q -r requirements.txt
    set -a
    . /opt/scandy-lite/.env
    set +a
    venv/bin/alembic upgrade head
    systemctl start scandy-lite scandy-lite-https
    echo "Update abgeschlossen."
  '
  exit 0
fi

# --- Neuinstallation --------------------------------------------------------
DEFAULT_CTID="$(pvesh get /cluster/nextid 2>/dev/null || echo 100)"
read -r -p "Container-ID [${DEFAULT_CTID}]: " CTID
CTID="${CTID:-$DEFAULT_CTID}"
read -r -p "Hostname [scandy-lite]: " CT_HOSTNAME
CT_HOSTNAME="${CT_HOSTNAME:-scandy-lite}"
read -r -p "CPU-Kerne [2]: " CORES
CORES="${CORES:-2}"
read -r -p "RAM in MB [1024]: " RAM_MB
RAM_MB="${RAM_MB:-1024}"
read -r -p "Diskgröße in GB [6]: " DISK_GB
DISK_GB="${DISK_GB:-6}"
read -r -p "Storage für Rootfs [local-lvm]: " STORAGE
STORAGE="${STORAGE:-local-lvm}"
read -r -p "Storage für Templates [local]: " TEMPLATE_STORAGE
TEMPLATE_STORAGE="${TEMPLATE_STORAGE:-local}"
read -r -p "Netzwerk-Bridge [vmbr0]: " BRIDGE
BRIDGE="${BRIDGE:-vmbr0}"

ROOT_PASSWORD="$(openssl rand -hex 12)"

echo ""
echo "Suche aktuelles Debian-12-Template..."
TEMPLATE="$(pveam available --section system 2>/dev/null | awk '/debian-12-standard/ {print $2}' | sort -V | tail -n1)"
if [[ -z "$TEMPLATE" ]]; then
  echo "FEHLER: Kein Debian-12-Template gefunden (ggf. erst 'pveam update' ausführen)." >&2
  exit 1
fi
if ! pveam list "$TEMPLATE_STORAGE" 2>/dev/null | grep -q "$TEMPLATE"; then
  echo "Lade Template ${TEMPLATE}..."
  pveam update >/dev/null
  pveam download "$TEMPLATE_STORAGE" "$TEMPLATE"
fi

echo "Erstelle Container ${CTID} (${CT_HOSTNAME})..."
pct create "$CTID" "${TEMPLATE_STORAGE}:vztmpl/${TEMPLATE}" \
  --hostname "$CT_HOSTNAME" \
  --cores "$CORES" \
  --memory "$RAM_MB" \
  --swap 512 \
  --rootfs "${STORAGE}:${DISK_GB}" \
  --net0 "name=eth0,bridge=${BRIDGE},ip=dhcp,ip6=dhcp" \
  --unprivileged 1 \
  --onboot 1 \
  --password "$ROOT_PASSWORD"

pct start "$CTID"

echo "Warte auf Netzwerk und installiere Grundpakete (curl, git)..."
ATTEMPTS=0
until pct exec "$CTID" -- bash -c "apt-get update -qq && apt-get install -y -qq curl ca-certificates git" >/dev/null 2>&1; do
  ATTEMPTS=$((ATTEMPTS + 1))
  if [[ "$ATTEMPTS" -ge 15 ]]; then
    echo "FEHLER: Grundpakete konnten nach mehreren Versuchen nicht installiert werden (Netzwerk-Problem im Container?)." >&2
    exit 1
  fi
  sleep 4
done

echo "Installiere ${APP} im Container (kann einige Minuten dauern)..."
pct exec "$CTID" -- bash -c "curl -fsSL '${INSTALL_SCRIPT_URL}' -o /root/scandy-lite-install.sh && bash /root/scandy-lite-install.sh"

IP="$(pct exec "$CTID" -- hostname -I | awk '{print $1}')"

echo ""
echo "=== Fertig! ==="
echo "HTTP  (Hardware-Scanner/Tastatur):                 http://${IP}:8000"
echo "HTTPS (Kamera-Scan, selbstsigniertes Zertifikat):  https://${IP}:8443"
echo ""
echo "Admin-Zugangsdaten: pct exec ${CTID} -- cat /root/scandy-lite.creds"
echo "Root-Passwort des Containers (Konsole/SSH): ${ROOT_PASSWORD}"
echo ""
echo "Update später: dieses Skript erneut ausführen und Container-ID ${CTID} angeben."
