# Discovery

**Nicht Teil von Scandy-Lite - bewusst außerhalb des Scopes.**

Es gibt keine Netzwerk-/Geräte-Discovery (Windows/Linux/SNMP-Agenten oder
Ähnliches) und keine Pläne, das anzubinden. Scandy-Lite verwaltet Gegenstände
und Verbrauchsmaterial, die manuell angelegt werden (einzeln oder per CSV-
Import/Scandy2-Migration, siehe `README.md`) - kein automatisiertes
Erfassen von IT-Ausstattung im Netzwerk.

Diese Datei existiert, damit ein AI-Agent, der `CLAUDE.md`s langfristige
Vision liest, nicht versehentlich eine Discovery-Funktion als "fehlendes,
nachzuholendes Feature" missversteht und von sich aus zu bauen beginnt. Die
Vision in `CLAUDE.md` beschreibt eine mögliche langfristige Richtung für
das übergeordnete Projekt, **keinen aktuellen Auftrag** - der Scope der App
bleibt auf das begrenzt, was heute existiert (Ausleihe-/Ausgabe-Verwaltung
für Werkzeuge und Verbrauchsmaterial), bis explizit anders entschieden wird.

Falls Discovery irgendwann tatsächlich gebaut werden soll: erst mit dem
Projektverantwortlichen klären, ob und wie das zum bestehenden
Datenmodell (`Item`/`Consumable`, abteilungsgescoped) passt, bevor Code
entsteht.
