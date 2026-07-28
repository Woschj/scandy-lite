# Roadmap

**Scope-Hinweis:** diese Roadmap beschreibt den Ausbau von Scandy-Lite
INNERHALB seines aktuellen Zwecks (Ausleihe-/Ausgabe-Verwaltung für
Werkzeuge und Verbrauchsmaterial). Sie ist keine Liste der langfristigen
Vision aus `CLAUDE.md` ("Speziell für Scandy-Lite") - Punkte wie
Discovery oder ein Plugin-System sind bewusst NICHT hier drin, siehe
`docs/architecture/discovery.md` und `docs/architecture/plugin-system.md`
für die Einordnung.

## Umgesetzt

Siehe `README.md` ("Projektstatus") und `CHANGELOG.md` für den
vollständigen, laufend gepflegten Stand. Kurzfassung: Datenmodell,
Auth + Abteilungs-Rollenmodell, CRUD für Gegenstände/Material/Mitarbeiter,
Quickscan (Ausleihe/Rückgabe/Entnahme), Sammel-Abholung für Reservierungen,
Warenkorb-Reservierungsworkflow, Historie, Bild-Upload, Papierkorb mit
Wiederherstellung, Scandy2-Legacy-Migration (Web + CLI), OIDC-SSO
(Authentik), PWA mit Service Worker, native Proxmox-LXC-Installation +
In-App-Update, Docker/Portainer-Deployment.

## Bekannt offen

Siehe `docs/roadmap/technical-debt.md` für technische Schulden und die
"Was noch offen ist"-Abschnitte in `README.md`/
`PROJECT_STATUS_FOR_CLAUDE_CODE.md` für fachlich offene Punkte (Stand
laufend aktuell halten, nicht hier duplizieren und dadurch doppelt
pflegen müssen).

## Neue Roadmap-Punkte aufnehmen

Bevor ein neuer Punkt hier landet: passt er in den aktuellen Scope
(Ausleihe/Ausgabe-Verwaltung)? Wenn er eher zur langfristigen
`CLAUDE.md`-Vision gehört (z. B. "Lizenzmanagement", "Netzwerk-
dokumentation"), gehört er dorthin bzw. in eine eigene Diskussion mit dem
Projektverantwortlichen, nicht stillschweigend in die aktive Roadmap.
