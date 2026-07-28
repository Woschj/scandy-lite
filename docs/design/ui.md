# UI / Design-System

## Leitidee

"Werkstatt-Inventaranhänger" (Asset-Tag) als durchgängiges visuelles Motiv
- Karten mit Perforationskante und Barcode-Streifen-Optik, siehe
`.tag-card` in `app/static/css/app.css`. Zieht sich durch Login, Dashboard,
Item-Karten, Mitarbeiterausweise (`app/templates/badge.html`).

## Typografie &amp; Farben

Trebuchet MS als Systemfont (siehe `docs/architecture/frontend.md` für die
Begründung - kein externer Font-Import). Farben/Abstände ausschließlich
über CSS Custom Properties in `:root` (`--brand`, `--ink`, `--space-*`,
...) - keine Hex-Werte verstreut im Stylesheet, damit sich das Farbschema
an einer Stelle ändern lässt.

## Dark Mode

**Nicht implementiert.** `CLAUDE.md`s langfristige Vision nennt
Dark-Mode-Fähigkeit als Ziel; das ist aktuell kein Auftrag, siehe
`docs/architecture/discovery.md` für die gleiche Einordnung bei anderen
Vision-Punkten. Falls das umgesetzt wird: über eine zweite Custom-
Property-Ebene (`@media (prefers-color-scheme: dark)` + optionalem
manuellen Umschalter), nicht über ein zweites, paralleles CSS-File.

## Responsive-Strategie

Ein Breakpoint schaltet zwischen Top-Nav (Desktop) und Bottom-Tab-Bar
(Mobil) um - siehe `docs/architecture/frontend.md`. Touch-Targets
mindestens 44px hoch. Eigene Media Query für Handy-Querformat (schmalere
Nav/Tab-Bar, damit die Kamera-Vorschau beim Scannen genug Platz behält) -
bewusst nicht blockiert (früher gab es einen "Bitte Gerät drehen"-Zwang,
inzwischen durch aktive Unterstützung ersetzt, siehe `CHANGELOG.md`).

## Icons

Inline-SVG (kein Icon-Font, kein externes Icon-Set als Abhängigkeit) -
`stroke="currentColor"`, damit Icons automatisch die Textfarbe des
umgebenden Elements übernehmen (z. B. aktiver Tab-Bar-Zustand).

## Neue UI-Bausteine

Vor einem neuen visuellen Muster: existiert schon etwas Ähnliches
(`.tag-card`, `.settings-row`, `.item-card`, `.chip`)? Wiederverwenden
statt eine Variante mit demselben Zweck, aber eigenem CSS, hinzuzufügen -
jede zusätzliche Variante ist eine weitere Stelle, die bei künftigen
Design-Anpassungen mitgepflegt werden muss.
