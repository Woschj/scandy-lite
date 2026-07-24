# Scandy-Lite Erstinstallation (Windows/PowerShell).
#
# Macht aus einem frischen "git clone" eine laufende Instanz:
#   1. Prueft Docker/Docker Compose
#   2. Erzeugt .env mit zufaelligen Secrets, falls noch keine existiert
#      (idempotent - ein erneuter Lauf veraendert eine bestehende .env NICHT)
#   3. Baut und startet den Stack
#   4. Wartet, bis die App tatsaechlich antwortet
#   5. Zeigt Zugangs-URL + Admin-Zugangsdaten an
#
# Nutzung (PowerShell):
#   .\install.ps1
#
# Falls PowerShell das Ausfuehren von Skripten blockiert (ExecutionPolicy),
# einmalig fuer die aktuelle Sitzung erlauben:
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

$ErrorActionPreference = "Stop"

# Absoluter Pfad zum Skript-Ordner - WICHTIG: nicht (Get-Location) verwenden,
# das haengt davon ab, aus welchem Ordner das Skript gestartet wurde.
# $PSScriptRoot ist immer der Ordner, in dem DIESES Skript liegt.
Set-Location $PSScriptRoot

Write-Host "=== Scandy-Lite Installation ===" -ForegroundColor Cyan
Write-Host ""

# --- 1. Voraussetzungen ----------------------------------------------------
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "Docker wurde nicht gefunden. Installation: https://docs.docker.com/get-docker/"
    exit 1
}
docker compose version *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Error "'docker compose' (Compose V2) ist nicht verfuegbar. Docker Desktop aktualisieren."
    exit 1
}

# --- 2. .env erzeugen (nur falls noch keine existiert) ---------------------
$envPath = Join-Path $PSScriptRoot ".env"

if (Test-Path $envPath) {
    Write-Host ".env existiert bereits - wird unveraendert weiterverwendet."
} else {
    Write-Host "Erzeuge .env mit zufaellig generierten Zugangsdaten..."

    # .NET-eigener Zufallsgenerator statt openssl (auf Windows nicht immer
    # vorhanden) - liefert denselben Effekt: kryptografisch sichere,
    # zufaellige Hex-Strings.
    function New-RandomHex([int]$bytes) {
        $buffer = New-Object byte[] $bytes
        [System.Security.Cryptography.RandomNumberGenerator]::Fill($buffer)
        return ([System.BitConverter]::ToString($buffer) -replace '-', '').ToLower()
    }

    $secretKey = New-RandomHex 32
    $postgresPassword = New-RandomHex 24
    $adminPassword = New-RandomHex 8
    $timestamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")

    $envContent = @"
# Automatisch von install.ps1 generiert am $timestamp
# Zufaellige, sichere Werte - siehe INSTALL.md fuer die Bedeutung der
# einzelnen Variablen. ADMIN_PASSWORD nach dem ersten erfolgreichen Login
# idealerweise aus dieser Datei entfernen (liegt aktuell im Klartext).
SECRET_KEY=$secretKey
POSTGRES_USER=scandy
POSTGRES_PASSWORD=$postgresPassword
POSTGRES_DB=scandy_lite
ACCESS_TOKEN_EXPIRE_MINUTES=720
SESSION_COOKIE_SECURE=false
ADMIN_USERNAME=admin
ADMIN_PASSWORD=$adminPassword
DEFAULT_DEPARTMENT_CODE=werkstatt
DEFAULT_DEPARTMENT_NAME=Werkstatt
APP_PORT=8000
APP_HTTPS_PORT=8443
"@

    # WICHTIG: explizit BOM-freies UTF8 schreiben (nicht Set-Content
    # -Encoding utf8, das fuegt in Windows PowerShell 5.1 unsichtbar ein BOM
    # ein - genau das hat scandy-lite schon einmal mit "exec format error"
    # lahmgelegt, weil ein Shell-Skript dadurch seine Shebang-Zeile verlor.
    # .env-Dateien werden zwar nicht ausgefuehrt, aber lieber konsistent
    # denselben sicheren Weg nehmen.
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($envPath, $envContent + "`n", $utf8NoBom)

    Write-Host ".env erzeugt."
}

# .env fuer die Werte unten einlesen (funktioniert unabhaengig davon, ob sie
# gerade neu erzeugt oder schon vorhanden war)
$envValues = @{}
Get-Content $envPath | ForEach-Object {
    if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
        $envValues[$matches[1]] = $matches[2]
    }
}

# --- 3. Bauen und starten ---------------------------------------------------
Write-Host ""
Write-Host "Baue und starte Container (kann beim allerersten Mal 1-2 Minuten dauern)..."
docker compose up -d --build
if ($LASTEXITCODE -ne 0) {
    Write-Error "docker compose up ist fehlgeschlagen - siehe Ausgabe oben."
    exit 1
}

# --- 4. Auf tatsaechlich antwortende App warten -----------------------------
Write-Host ""
Write-Host "Warte auf App-Start..."

$appPort = if ($envValues.ContainsKey("APP_PORT")) { $envValues["APP_PORT"] } else { "8000" }
$healthUrl = "http://localhost:$appPort/health"
$attempts = 0
$maxAttempts = 60
$healthy = $false

while ($attempts -lt $maxAttempts) {
    try {
        $response = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 3
        if ($response.StatusCode -eq 200) {
            $healthy = $true
            break
        }
    } catch {
        # Noch nicht bereit - normal waehrend des Starts, einfach weiter warten
    }
    $attempts++
    Start-Sleep -Seconds 2
}

if (-not $healthy) {
    Write-Host ""
    Write-Error "App antwortet nach 2 Minuten immer noch nicht. Logs pruefen mit: docker compose logs app"
    exit 1
}

# --- 5. Zusammenfassung ------------------------------------------------------
$adminUsername = if ($envValues.ContainsKey("ADMIN_USERNAME")) { $envValues["ADMIN_USERNAME"] } else { "admin" }
$adminPasswordDisplay = $envValues["ADMIN_PASSWORD"]
$httpsPort = if ($envValues.ContainsKey("APP_HTTPS_PORT")) { $envValues["APP_HTTPS_PORT"] } else { "8443" }

Write-Host ""
Write-Host "=== Fertig! ===" -ForegroundColor Green
Write-Host ""
Write-Host "App erreichbar unter:  http://localhost:$appPort"
Write-Host "Login:                 $adminUsername / $adminPasswordDisplay"
Write-Host ""
Write-Host "Fuer Kamera-Scan (benoetigt HTTPS): https://localhost:$httpsPort"
Write-Host "(zeigt eine Zertifikatswarnung - selbstsigniert, einmalig pro Geraet bestaetigen)"
Write-Host ""
Write-Host "Zugangsdaten stehen auch in .env - ADMIN_PASSWORD danach am besten dort entfernen"
Write-Host "(liegt aktuell im Klartext, wird beim naechsten Start nicht erneut gebraucht -"
Write-Host "das Admin-Konto existiert dann schon)."
