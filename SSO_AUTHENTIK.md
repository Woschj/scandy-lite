# Scandy-Lite — SSO-Login über Authentik einrichten

Optionales Feature (siehe [CHANGELOG.md](CHANGELOG.md) 0.12.0): ein
zusätzlicher "Mit Authentik anmelden"-Button neben dem normalen Login.
Standardmäßig aus - erst aktiv, wenn die drei `OIDC_*`-Variablen gesetzt
sind (siehe Schritt 2 unten).

Ablauf danach: erster Login einer neuen Person legt automatisch ein Konto
an, aber **gesperrt** - ein Admin muss es unter "Ausstehende Konten" (Hinweis
auf der Übersicht) erst freischalten (Abteilung + Rolle festlegen).

## Voraussetzungen

- Ein laufender Authentik-Server, von Scandy-Lite aus erreichbar (die App
  ruft Authentik serverseitig auf, nicht nur der Browser)
- Scandy-Lite läuft bereits über HTTPS (Kamera-Scan braucht das ohnehin
  schon, siehe [INSTALL.md](INSTALL.md) Abschnitt 4) - Authentik akzeptiert
  bei einer Confidential-Client-Anwendung i.d.R. keine reinen HTTP-Redirects

## 1. Provider in Authentik anlegen

**Applications → Providers → Create**

| Feld | Wert |
|---|---|
| Provider-Typ | **OAuth2/OpenID Provider** |
| Name | z. B. `Scandy-Lite` |
| Authorization flow | eine der vorhandenen Consent-Flows (z. B. `default-provider-authorization-explicit-consent`) |
| Client type | **Confidential** (Scandy-Lite kann ein Secret sicher serverseitig halten - **nicht** "Public" wählen) |
| Redirect URIs/Origins (Strict) | `https://<eure-scandy-lite-domain>/auth/oidc/callback` **exakt so, inkl. Pfad** |
| Scopes | die vier Standard-Mappings reichen: `openid`, `email`, `profile` (+ optional `offline_access`, wird nicht gebraucht) |
| Signing Key | einen vorhandenen Zertifikatsschlüssel auswählen (Pflichtfeld) |

Speichern. Authentik zeigt danach **Client ID** und **Client Secret** an
(auf der Provider-Detailseite bzw. beim Öffnen zum Bearbeiten sichtbar) -
beide gleich notieren, das Secret wird nicht nochmal im Klartext angezeigt.

## 2. Application anlegen und verknüpfen

**Applications → Applications → Create**

| Feld | Wert |
|---|---|
| Name | z. B. `Scandy-Lite` |
| Slug | z. B. `scandy-lite` (landet in der Issuer-URL, siehe Schritt 3) |
| Provider | den in Schritt 1 angelegten Provider auswählen |
| Launch URL (optional) | `https://<eure-scandy-lite-domain>/` |

Speichern. Falls in eurem Authentik-Setup Zugriff über Gruppen/Policies
gesteuert wird: unter der Application die passenden Nutzer/Gruppen
freigeben, sonst bekommen sie beim Login "Access denied", bevor sie
überhaupt bei Scandy-Lite ankommen.

## 3. Issuer-URL finden

Auf der Provider-Detailseite (Schritt 1) steht ein Link/Feld **"OpenID
Configuration URL"**, meist in der Form:

```
https://<authentik-host>/application/o/<slug>/.well-known/openid-configuration
```

Für Scandy-Lite braucht ihr davon nur den Teil **vor** `.well-known/...`,
also:

```
https://<authentik-host>/application/o/<slug>/
```

(`<slug>` ist der Application-Slug aus Schritt 2.)

## 4. Scandy-Lite konfigurieren

Drei Umgebungsvariablen setzen (Portainer: Stack-Editor → Environment
variables, siehe [INSTALL.md](INSTALL.md) Abschnitt 2 für den generellen
Ablauf) - `docker-compose.yml` reicht diese bereits durch:

| Variable | Wert |
|---|---|
| `OIDC_ISSUER` | die URL aus Schritt 3, **mit** abschließendem `/` |
| `OIDC_CLIENT_ID` | aus Schritt 1 |
| `OIDC_CLIENT_SECRET` | aus Schritt 1 |
| `OIDC_PROVIDER_NAME` | optional, Beschriftung des Buttons, z. B. `Authentik` (Default: `SSO`) |

Stack neu deployen. Auf `/auth/login` erscheint danach unter dem normalen
Formular ein zusätzlicher Button "Mit \<OIDC_PROVIDER_NAME\> anmelden".

## 5. Testen

1. Ausloggen (oder privates Fenster), `/auth/login` öffnen, auf den neuen
   Button klicken
2. Bei Authentik anmelden (+ ggf. Consent bestätigen)
3. Zurück bei Scandy-Lite: Seite "Fast geschafft - wartet auf
   Freischaltung" sollte erscheinen (**erster** Login einer neuen Person)
4. Als Admin einloggen (lokal, oder ein bereits freigeschaltetes Konto),
   auf der Übersicht erscheint jetzt der Hinweis "1 Konto wartet auf
   Freischaltung" → "Jetzt prüfen"
5. Abteilung (+ optional Rolle) wählen, "Freischalten" klicken
6. Die Person kann sich jetzt erneut über den Authentik-Button anmelden und
   kommt direkt durch

## Fehlerbehebung

| Symptom | Wahrscheinliche Ursache | Lösung |
|---|---|---|
| Button "Mit ... anmelden" erscheint nicht | `OIDC_ISSUER`/`OIDC_CLIENT_ID`/`OIDC_CLIENT_SECRET` nicht (vollständig) gesetzt | alle drei prüfen, Stack neu deployen |
| Nach Klick auf den Button: Fehlerseite bei Authentik ("invalid redirect_uri" o. ä.) | Redirect-URI in Authentik weicht ab | in Authentik exakt `https://<domain>/auth/oidc/callback` eintragen (Schema, Domain, Pfad müssen exakt passen) |
| Nach Authentik-Login zurück bei Scandy-Lite: "SSO-Anmeldung fehlgeschlagen" | `OIDC_ISSUER` falsch/unerreichbar, `OIDC_CLIENT_SECRET` falsch, oder Authentik nutzt ein selbstsigniertes Zertifikat, das der App-Container nicht vertraut | Werte prüfen; bei selbstsigniertem Zertifikat auf Authentik-Seite ein von der Umgebung vertrauenswürdiges Zertifikat verwenden (z. B. via Caddy/Let's Encrypt) |
| Bei Authentik: "Access denied" vor der Weiterleitung | Nutzer/Gruppe hat in Authentik keinen Zugriff auf die Application | unter der Application in Authentik den Zugriff freigeben (siehe Schritt 2) |
| Konto bleibt dauerhaft auf "wartet auf Freischaltung" | Noch niemand hat es freigeschaltet | als Admin unter "Ausstehende Konten" (Link auf der Übersicht) freischalten |
| Neues Konto landet in der falschen/keiner Abteilung | Beim Freischalten wird die Abteilung bewusst erst dort festgelegt, nicht automatisch aus Authentik übernommen | beim Freischalten die richtige Abteilung wählen - danach wie gewohnt über "Zugriff" korrigierbar |
