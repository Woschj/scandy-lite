# Listen &amp; Tabellen

Scandy-Lite nutzt keine klassische `<table>`-Datentabelle für die
Hauptlisten (Items/Consumables/Users) - stattdessen Karten-/Zeilenlisten
(`.item-grid` mit Kachel- oder Kompaktansicht, `.settings-list`/
`.settings-row` für Verwaltungslisten). Grund: die Kern-Nutzung ist mobil
(PWA), eine breite Tabelle mit vielen Spalten funktioniert auf schmalen
Viewports schlecht - Karten/Zeilen mit klarer Hierarchie (Name zuerst,
Details sekundär) lassen sich responsiv umbrechen, eine Tabelle nicht ohne
horizontales Scrollen oder Spalten-Ausblenden.

## Aktueller Stand

- **Suche:** serverseitig per Query-Parameter (`?q=...`), kein
  clientseitiges Filtern großer Listen im Browser.
- **Filter:** Status/Kategorie/Standort als eigenes Filter-Sheet (Alpine.js
  für Auf-/Zuklappen, Absenden bleibt ein normaler GET-Formular-Submit,
  `filter-active-dot` zeigt aktive Filter optisch an, siehe
  `app/templates/items/list.html`).
- **Kachel-/Listenansicht:** per Toggle umschaltbar (`view-toggle.js`,
  `.item-grid.view-list`-Modifier), Präferenz nicht persistiert.
- **Bulk-Aktionen:** **nicht implementiert.** Jede Aktion (Löschen,
  Bearbeiten, Bild ändern) wirkt auf genau einen Datensatz. Vor dem
  Einführen von Mehrfachauswahl/Bulk-Aktionen: prüfen, ob sich das mit dem
  bestehenden Karten-/Zeilen-Layout verträgt oder ob es einen eigenen,
  bewusst einfachen "Auswahlmodus" braucht - keine stillschweigende
  Komplexitätserhöhung der Hauptliste.

## Neue Listen

Neue Übersichtsseiten sollten sich an `app/templates/items/list.html`
orientieren (Suche + Filter-Sheet + Kachel/Liste-Toggle), statt ein neues
Listen-Pattern zu erfinden - Konsistenz zwischen Items/Consumables/Users
ist der aktuelle Stand, keine zufällige Übereinstimmung.
