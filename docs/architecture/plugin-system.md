# Plugin-System

**Nicht implementiert - bewusst außerhalb des aktuellen Scopes.**

Es gibt keine Plugin-/Extension-API, keine Runtime-Erweiterungspunkte, kein
Hook-System. Erweiterungen des Funktionsumfangs passieren als normale
Code-Änderungen im Hauptrepo (mit Tests, Review, Migration bei Bedarf) -
nicht über nachladbare Module.

Diese Datei existiert aus demselben Grund wie
`docs/architecture/discovery.md`: `CLAUDE.md`s "Projektvision & aktueller
Scope"-Abschnitt nennt ein Plugin-System als mögliches langfristiges Ziel
für das übergeordnete Projekt. Das ist **keine Aufforderung, jetzt eines zu
bauen**.
Solange nicht explizit anders entschieden wird, gilt: keine neue
Abstraktionsschicht "für später" einführen, die aktuell nichts tut außer
Komplexität hinzuzufügen (siehe `CLAUDE.md` "Was vermieden werden soll" -
keine unnötige Komplexität, kein Over-Engineering für hypothetische
zukünftige Anforderungen).

Falls ein Plugin-System irgendwann tatsächlich beauftragt wird: zuerst
klären, welche konkreten Erweiterungspunkte gebraucht werden (welche
Plugins soll es geben, was müssen sie tun können), dann erst die dafür
nötige minimale API entwerfen - nicht umgekehrt.
