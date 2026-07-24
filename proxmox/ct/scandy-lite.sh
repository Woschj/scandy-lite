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
# Abfragen laufen über `whiptail` (Menüs/vorausgefüllte Felder statt
# Freitext-Tippen) - Storage- und Netzwerk-Bridge-Auswahl wird direkt aus
# `pvesm status`/`ip link` gespeist, damit dort keine Tippfehler mehr
# möglich sind. Ist `whiptail` nicht verfügbar (und lässt sich nicht
# nachinstallieren), fällt das Skript auf einfache Texteingaben zurück.
#
# Aufruf auf dem Proxmox-Host (als root):
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/Woschj/scandy-lite/master/proxmox/ct/scandy-lite.sh)"
#
# Erneuter Aufruf aktualisiert stattdessen eine bestehende Installation
# (git pull gegen master + Migrationen + Dienst-Neustart) - siehe INSTALL.md.

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

if ! command -v whiptail >/dev/null 2>&1; then
  apt-get update -qq >/dev/null 2>&1 || true
  apt-get install -y -qq whiptail >/dev/null 2>&1 || true
fi
HAVE_WHIPTAIL=0
command -v whiptail >/dev/null 2>&1 && HAVE_WHIPTAIL=1

# --- kleine Helfer für Menü-/Eingabe-Dialoge mit Text-Fallback -------------
# Jede Funktion gibt den gewählten Wert auf stdout aus, Abbruch (ESC/Cancel)
# beendet das Skript.

wt_menu() {
  # wt_menu <Titel> <Text> <fallback-prompt> <fallback-default> <tag> <desc> [<tag> <desc> ...]
  local title="$1" text="$2" fb_prompt="$3" fb_default="$4"
  shift 4
  if [[ "$HAVE_WHIPTAIL" -eq 1 && $# -gt 0 ]]; then
    local height=$((8 + $#/2))
    [[ $height -gt 24 ]] && height=24
    whiptail --title "$title" --menu "$text" "$height" 70 $(($#/2)) "$@" 3>&1 1>&2 2>&3
    return $?
  fi
  echo "$text" >&2
  while [[ $# -gt 0 ]]; do
    echo "  - $1: $2" >&2
    shift 2
  done
  read -r -p "$fb_prompt [$fb_default]: " reply
  echo "${reply:-$fb_default}"
}

wt_input() {
  # wt_input <Titel> <Text> <default>
  local title="$1" text="$2" default="$3"
  if [[ "$HAVE_WHIPTAIL" -eq 1 ]]; then
    whiptail --title "$title" --inputbox "$text" 10 70 "$default" 3>&1 1>&2 2>&3
    return $?
  fi
  read -r -p "$text [$default]: " reply
  echo "${reply:-$default}"
}

wt_yesno() {
  # wt_yesno <Titel> <Text> <yes-label> <no-label>  -> exit 0 = ja
  local title="$1" text="$2" yes_label="$3" no_label="$4"
  if [[ "$HAVE_WHIPTAIL" -eq 1 ]]; then
    whiptail --title "$title" --yesno "$text" 20 72 --yes-button "$yes_label" --no-button "$no_label"
    return $?
  fi
  read -r -p "$text ($yes_label/$no_label) [${yes_label}]: " reply
  [[ -z "$reply" || "${reply,,}" == "${yes_label,,}" ]]
}

echo "=== ${APP} - Proxmox VE LXC-Installer ==="

# --- Modus wählen: Neuinstallation oder Update -----------------------------
MODE="$(wt_menu "${APP} Installer" "Was möchtest du tun?" \
  "Modus (install/update)" "install" \
  install "Neue Installation" \
  update  "Bestehende Installation aktualisieren")"

# --- Update-Pfad: gegen einen bereits laufenden Container -----------------
if [[ "$MODE" == "update" ]]; then
  MENU_ITEMS=()
  while read -r ctid status rest; do
    [[ -z "$ctid" ]] && continue
    MENU_ITEMS+=("$ctid" "$rest ($status)")
  done < <(pct list | tail -n +2)

  if [[ "${#MENU_ITEMS[@]}" -eq 0 ]]; then
    echo "FEHLER: Keine LXC-Container auf diesem Host gefunden." >&2
    exit 1
  fi
  EXISTING_CTID="$(wt_menu "${APP} aktualisieren" "Welcher Container soll aktualisiert werden?" \
    "Container-ID" "" "${MENU_ITEMS[@]}")"
  if [[ -z "$EXISTING_CTID" ]]; then
    echo "Abgebrochen." >&2
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
DEFAULT_CT_HOSTNAME="scandy-lite"
DEFAULT_CORES="2"
# 2048 MB statt 1024 MB: apt-get dist-upgrade beim Einrichten des Containers
# (misc/install.func::update_os) braucht spürbar mehr Speicher als der
# laufende Betrieb - mit 1024 MB kam es beim Testen zu starkem Swapping und
# einer entsprechend langsamen Installation.
DEFAULT_RAM_MB="2048"
# 16 statt 6 GB: bei Thin-Provisioning (Standard bei local-lvm) ist das nur
# eine Obergrenze, kein reservierter Platz - kostet also nichts, gibt aber
# genug Puffer für Datenbank + Uploads (Item-/Consumable-Bilder), falls das
# Inventar deutlich wächst. Spaeter jederzeit erweiterbar per
# `pct resize <CTID> rootfs +10G`, auch ohne Thin-Provisioning.
DEFAULT_DISK_GB="16"
DEFAULT_SWAP_MB="1024"

# Storage-Listen getrennt nach Verwendungszweck einlesen: Rootfs braucht
# Content-Typ "rootdir" (z.B. local-lvm), Templates brauchen "vztmpl" (z.B.
# local) - "local" unterstützt in den meisten Standard-Setups NUR vztmpl/
# iso/backup, kein rootdir. Eine gemeinsame, ungefilterte Liste (frühere
# Version dieses Skripts) konnte daher "local" als Rootfs-Storage vorschlagen
# und pct create ließ das mit "storage 'local' does not support container
# directories" scheitern.
STORAGE_MENU=()
while read -r name type rest; do
  [[ -z "$name" || "$name" == "Name" ]] && continue
  STORAGE_MENU+=("$name" "Typ: $type")
done < <(pvesm status --content rootdir 2>/dev/null | tail -n +2)
if [[ "${#STORAGE_MENU[@]}" -eq 0 ]]; then
  # Fallback fuer aeltere pvesm-Versionen ohne --content-Filter
  while read -r name type rest; do
    [[ -z "$name" || "$name" == "Name" ]] && continue
    STORAGE_MENU+=("$name" "Typ: $type")
  done < <(pvesm status 2>/dev/null | tail -n +2)
fi
if [[ "${#STORAGE_MENU[@]}" -eq 0 ]]; then
  STORAGE_MENU=("local-lvm" "Typ: unbekannt")
fi

TEMPLATE_STORAGE_MENU=()
while read -r name type rest; do
  [[ -z "$name" || "$name" == "Name" ]] && continue
  TEMPLATE_STORAGE_MENU+=("$name" "Typ: $type")
done < <(pvesm status --content vztmpl 2>/dev/null | tail -n +2)
if [[ "${#TEMPLATE_STORAGE_MENU[@]}" -eq 0 ]]; then
  TEMPLATE_STORAGE_MENU=("local" "Typ: unbekannt")
fi

# Bridge-Liste einmal einlesen
BRIDGE_MENU=()
while read -r br; do
  [[ -z "$br" ]] && continue
  BRIDGE_MENU+=("$br" "Netzwerk-Bridge")
done < <(ip -o link show type bridge 2>/dev/null | awk -F': ' '{print $2}')
if [[ "${#BRIDGE_MENU[@]}" -eq 0 ]]; then
  BRIDGE_MENU=("vmbr0" "Netzwerk-Bridge")
fi

DEFAULT_STORAGE="${STORAGE_MENU[0]}"
DEFAULT_TEMPLATE_STORAGE="${TEMPLATE_STORAGE_MENU[0]}"
DEFAULT_BRIDGE="${BRIDGE_MENU[0]}"

if wt_yesno "${APP} Installer" \
  "Standard-Einstellungen verwenden?\n\nContainer-ID:      ${DEFAULT_CTID}\nHostname:           ${DEFAULT_CT_HOSTNAME}\nCPU-Kerne:          ${DEFAULT_CORES}\nRAM:                ${DEFAULT_RAM_MB} MB\nSwap:               ${DEFAULT_SWAP_MB} MB\nDisk:               ${DEFAULT_DISK_GB} GB\nStorage (Rootfs):   ${DEFAULT_STORAGE}\nStorage (Template): ${DEFAULT_TEMPLATE_STORAGE}\nNetzwerk-Bridge:    ${DEFAULT_BRIDGE}\n\n'Erweitert' öffnet je ein Auswahlfeld pro Einstellung." \
  "Standard" "Erweitert"; then
  CTID="$DEFAULT_CTID"
  CT_HOSTNAME="$DEFAULT_CT_HOSTNAME"
  CORES="$DEFAULT_CORES"
  RAM_MB="$DEFAULT_RAM_MB"
  SWAP_MB="$DEFAULT_SWAP_MB"
  DISK_GB="$DEFAULT_DISK_GB"
  STORAGE="$DEFAULT_STORAGE"
  TEMPLATE_STORAGE="$DEFAULT_TEMPLATE_STORAGE"
  BRIDGE="$DEFAULT_BRIDGE"
else
  CTID="$(wt_input "${APP} Installer" "Container-ID (frei wählbar, muss unbenutzt sein):" "$DEFAULT_CTID")"
  CT_HOSTNAME="$(wt_input "${APP} Installer" "Hostname:" "$DEFAULT_CT_HOSTNAME")"
  CORES="$(wt_input "${APP} Installer" "CPU-Kerne:" "$DEFAULT_CORES")"
  RAM_MB="$(wt_input "${APP} Installer" "RAM in MB:" "$DEFAULT_RAM_MB")"
  SWAP_MB="$(wt_input "${APP} Installer" "Swap in MB:" "$DEFAULT_SWAP_MB")"
  DISK_GB="$(wt_input "${APP} Installer" "Diskgröße in GB:" "$DEFAULT_DISK_GB")"
  STORAGE="$(wt_menu "${APP} Installer" "Storage für den Container (Rootfs):" \
    "Storage (Rootfs)" "$DEFAULT_STORAGE" "${STORAGE_MENU[@]}")"
  TEMPLATE_STORAGE="$(wt_menu "${APP} Installer" "Storage für das Debian-Template:" \
    "Storage (Template)" "$DEFAULT_TEMPLATE_STORAGE" "${TEMPLATE_STORAGE_MENU[@]}")"
  BRIDGE="$(wt_menu "${APP} Installer" "Netzwerk-Bridge:" \
    "Bridge" "$DEFAULT_BRIDGE" "${BRIDGE_MENU[@]}")"
fi

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
  --swap "$SWAP_MB" \
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
echo "Update später: dieses Skript erneut ausführen und im Menü 'Aktualisieren' wählen."
