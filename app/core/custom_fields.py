"""
Admin-definierbare Zusatzfelder pro Kategorie (app.models.custom_field) -
Laufzeit-Logik zum Laden/Speichern, getrennt von den Routen
(app/routers/items.py, app/routers/admin_settings.py), damit beide dieselbe
Zuordnungs-/Validierungslogik nutzen.

Item.category bleibt ein freies Textfeld (siehe app/models/preset.py) - die
Zuordnung "welche Zusatzfelder gelten für diesen Gegenstand" läuft deshalb
immer über Category.name == item.category (+ department), nicht über eine
feste Fremdschlüsselbeziehung am Item selbst.
"""
from starlette.datastructures import FormData
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.custom_field import CustomFieldDefinition, CustomFieldValue
from app.models.common import CustomFieldType
from app.models.item import Item
from app.models.preset import Category


def field_form_key(field_id) -> str:
    return f"custom_field_{field_id}"


async def get_definitions_by_category(session: AsyncSession, department_id) -> dict[str, list[CustomFieldDefinition]]:
    """Alle Felddefinitionen einer Abteilung, gruppiert nach Kategorie-Name -
    für die Formular-Anzeige (items/form.html blendet die passende Gruppe
    Alpine-reaktiv ein, siehe dort)."""
    categories_result = await session.exec(
        select(Category).where(Category.department_id == department_id).order_by(Category.name)
    )
    categories = categories_result.all()
    if not categories:
        return {}
    category_ids = [c.id for c in categories]
    name_by_id = {c.id: c.name for c in categories}

    definitions_result = await session.exec(
        select(CustomFieldDefinition)
        .where(CustomFieldDefinition.category_id.in_(category_ids))
        .order_by(CustomFieldDefinition.name)
    )
    grouped: dict[str, list[CustomFieldDefinition]] = {}
    for definition in definitions_result.all():
        category_name = name_by_id[definition.category_id]
        grouped.setdefault(category_name, []).append(definition)
    return grouped


async def get_definitions_by_department_and_category(
    session: AsyncSession, department_ids: list
) -> dict[str, dict[str, list[CustomFieldDefinition]]]:
    """Wie get_definitions_by_category, aber für mehrere Abteilungen auf
    einmal - fürs Anlegen-Formular, wo neben der Kategorie auch die
    Abteilung selbst erst im Formular gewählt wird (siehe items/form.html:
    Alpine blendet die zu Abteilung UND Kategorie passende Gruppe ein).

    Bewusst 2 Abfragen statt einer pro Abteilung (N+1) - relevant, sobald
    eine Installation viele Abteilungen hat, da dieser Aufruf bei jedem
    Aufruf von 'Neuer Gegenstand' läuft."""
    if not department_ids:
        return {}
    categories_result = await session.exec(
        select(Category).where(Category.department_id.in_(department_ids)).order_by(Category.name)
    )
    categories = categories_result.all()
    if not categories:
        return {str(d): {} for d in department_ids}
    category_ids = [c.id for c in categories]
    category_by_id = {c.id: c for c in categories}

    definitions_result = await session.exec(
        select(CustomFieldDefinition)
        .where(CustomFieldDefinition.category_id.in_(category_ids))
        .order_by(CustomFieldDefinition.name)
    )
    grouped: dict[str, dict[str, list[CustomFieldDefinition]]] = {str(d): {} for d in department_ids}
    for definition in definitions_result.all():
        category = category_by_id[definition.category_id]
        grouped[str(category.department_id)].setdefault(category.name, []).append(definition)
    return grouped


async def get_definitions_for_item(session: AsyncSession, item: Item) -> list[CustomFieldDefinition]:
    """Nur die Definitionen, die tatsächlich zur aktuellen Kategorie DIESES
    Gegenstands passen (für Detailseite + zum Validieren beim Speichern)."""
    if not item.category:
        return []
    category_result = await session.exec(
        select(Category).where(Category.department_id == item.department_id, Category.name == item.category)
    )
    category = category_result.first()
    if not category:
        return []
    result = await session.exec(
        select(CustomFieldDefinition)
        .where(CustomFieldDefinition.category_id == category.id)
        .order_by(CustomFieldDefinition.name)
    )
    return result.all()


async def get_values_for_item(session: AsyncSession, item_id) -> dict:
    result = await session.exec(select(CustomFieldValue).where(CustomFieldValue.item_id == item_id))
    return {v.field_id: v.value for v in result.all()}


def _validate(definition: CustomFieldDefinition, raw_value: str) -> str | None:
    """Gibt eine Fehlermeldung zurück, oder None wenn der Wert gültig ist."""
    if definition.field_type == CustomFieldType.NUMBER:
        try:
            float(raw_value.replace(",", "."))
        except ValueError:
            return f"'{definition.name}': Zahl erwartet."
    elif definition.field_type == CustomFieldType.DATE:
        import re
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", raw_value):
            return f"'{definition.name}': Datum im Format JJJJ-MM-TT erwartet."
    elif definition.field_type == CustomFieldType.SELECT:
        options = [o.strip() for o in (definition.options or "").split(",") if o.strip()]
        if raw_value not in options:
            return f"'{definition.name}': ungültige Auswahl."
    return None


async def save_values_for_item(session: AsyncSession, item: Item, form_data: FormData) -> list[str]:
    """Liest custom_field_<id> aus den POST-Formulardaten für alle zur
    aktuellen Kategorie passenden Definitionen, validiert je nach Typ und
    upsertet/löscht die Werte. Gibt eine Liste von Fehlermeldungen zurück
    (leer = alles gespeichert) - Aufrufer entscheidet, ob bei Fehlern
    trotzdem committet wird (hier: nicht, siehe items.py update_item)."""
    definitions = await get_definitions_for_item(session, item)
    if not definitions:
        return []

    existing = await session.exec(select(CustomFieldValue).where(CustomFieldValue.item_id == item.id))
    existing_by_field = {v.field_id: v for v in existing.all()}

    errors: list[str] = []
    for definition in definitions:
        raw_value = (form_data.get(field_form_key(definition.id)) or "").strip()
        row = existing_by_field.get(definition.id)

        if not raw_value:
            if row:
                await session.delete(row)
            continue

        error = _validate(definition, raw_value)
        if error:
            errors.append(error)
            continue

        if row:
            row.value = raw_value
            session.add(row)
        else:
            session.add(CustomFieldValue(item_id=item.id, field_id=definition.id, value=raw_value))

    return errors
