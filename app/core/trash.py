"""
Papierkorb: soft-gelöschte Gegenstände/Verbrauchsmaterial/Benutzer
(deleted_at IS NOT NULL) wiederherstellen oder endgültig löschen.

Endgültiges Löschen ("purge") darf die Ausleih-/Entnahme-/Reservierungs-
Historie nicht zerreißen: abgeschlossene (nicht mehr offene) Historien-
Zeilen behalten Name/Barcode als Text-Schnappschuss, die Fremdschlüssel-
Spalte wird auf NULL gesetzt (siehe app/models/lending.py etc.). OFFENE
Ausleihen/Reservierungen sind aktive Geschäftsvorgänge, keine reine
Historie - die blockieren das Löschen bewusst, statt sie stillschweigend
"verschwinden" zu lassen.

purge_*/restore_*-Funktionen committen NICHT selbst (Aufrufer committet),
gleiches Prinzip wie app.core.custom_fields.save_values_for_item.
"""
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.common import utcnow
from app.models.consumable import Consumable, ConsumableUsage
from app.models.consumable_reservation import ConsumableReservation
from app.models.custom_field import CustomFieldDefinition, CustomFieldValue
from app.models.department import Department
from app.models.item import Item
from app.models.lending import Lending
from app.models.preset import Category, Location
from app.models.reservation import Reservation
from app.models.user import User
from app.models.user_department_role import UserDepartmentRole


async def get_trash_entries(session: AsyncSession) -> tuple[list[Item], list[Consumable], list[User]]:
    items = (
        await session.exec(
            select(Item).where(Item.deleted_at.is_not(None)).options(selectinload(Item.department)).order_by(Item.name)
        )
    ).all()
    consumables = (
        await session.exec(
            select(Consumable).where(Consumable.deleted_at.is_not(None)).options(selectinload(Consumable.department)).order_by(Consumable.name)
        )
    ).all()
    users = (
        await session.exec(
            select(User).where(User.deleted_at.is_not(None)).options(selectinload(User.department)).order_by(User.last_name)
        )
    ).all()
    return items, consumables, users


async def restore_item(session: AsyncSession, item: Item) -> str | None:
    conflict = await session.exec(select(Item).where(Item.barcode == item.barcode, Item.deleted_at.is_(None)))
    if conflict.first():
        return f"Barcode '{item.barcode}' ist inzwischen neu vergeben - erst dort ändern, bevor wiederhergestellt werden kann."
    item.deleted_at = None
    session.add(item)
    return None


async def restore_consumable(session: AsyncSession, consumable: Consumable) -> str | None:
    conflict = await session.exec(select(Consumable).where(Consumable.barcode == consumable.barcode, Consumable.deleted_at.is_(None)))
    if conflict.first():
        return f"Barcode '{consumable.barcode}' ist inzwischen neu vergeben - erst dort ändern, bevor wiederhergestellt werden kann."
    consumable.deleted_at = None
    session.add(consumable)
    return None


async def restore_user(session: AsyncSession, user: User) -> str | None:
    if user.barcode:
        conflict = await session.exec(select(User).where(User.barcode == user.barcode, User.deleted_at.is_(None)))
        if conflict.first():
            return f"Barcode '{user.barcode}' ist inzwischen neu vergeben - erst dort ändern, bevor wiederhergestellt werden kann."
    user.deleted_at = None
    session.add(user)
    return None


async def purge_item(session: AsyncSession, item: Item, *, force: bool = False) -> str | None:
    open_lending = (await session.exec(select(Lending).where(Lending.item_id == item.id, Lending.returned_at.is_(None)))).first()
    if open_lending:
        if not force:
            return f"'{item.name}' hat noch eine offene Ausleihe - erst zurückgeben."
        open_lending.returned_at = utcnow()
        session.add(open_lending)
    open_reservation = (
        await session.exec(
            select(Reservation).where(Reservation.item_id == item.id, Reservation.fulfilled_at.is_(None), Reservation.cancelled_at.is_(None))
        )
    ).first()
    if open_reservation:
        if not force:
            return f"'{item.name}' hat noch eine offene Reservierung - erst stornieren oder abholen lassen."
        open_reservation.cancelled_at = utcnow()
        session.add(open_reservation)

    for lending in (await session.exec(select(Lending).where(Lending.item_id == item.id))).all():
        lending.item_name_snapshot = item.name
        lending.item_barcode_snapshot = item.barcode
        lending.item_id = None
        session.add(lending)

    for reservation in (await session.exec(select(Reservation).where(Reservation.item_id == item.id))).all():
        reservation.item_name_snapshot = item.name
        reservation.item_barcode_snapshot = item.barcode
        reservation.item_id = None
        session.add(reservation)

    for value in (await session.exec(select(CustomFieldValue).where(CustomFieldValue.item_id == item.id))).all():
        await session.delete(value)

    await session.delete(item)
    return None


async def purge_consumable(session: AsyncSession, consumable: Consumable, *, force: bool = False) -> str | None:
    # Anders als bei Gegenständen (max. 1 offene Reservierung, strukturell
    # erzwungen) kann Verbrauchsmaterial mehrere gleichzeitig offene
    # Vormerkungen verschiedener Personen haben - bei force müssen ALLE
    # geschlossen werden, nicht nur die erste gefundene.
    open_reservations = (
        await session.exec(
            select(ConsumableReservation).where(
                ConsumableReservation.consumable_id == consumable.id,
                ConsumableReservation.fulfilled_at.is_(None),
                ConsumableReservation.cancelled_at.is_(None),
            )
        )
    ).all()
    if open_reservations:
        if not force:
            return f"'{consumable.name}' hat noch eine offene Vormerkung - erst stornieren oder abholen lassen."
        for open_reservation in open_reservations:
            open_reservation.cancelled_at = utcnow()
            session.add(open_reservation)

    for usage in (await session.exec(select(ConsumableUsage).where(ConsumableUsage.consumable_id == consumable.id))).all():
        usage.consumable_name_snapshot = consumable.name
        usage.consumable_id = None
        session.add(usage)

    for reservation in (await session.exec(select(ConsumableReservation).where(ConsumableReservation.consumable_id == consumable.id))).all():
        reservation.consumable_name_snapshot = consumable.name
        reservation.consumable_barcode_snapshot = consumable.barcode
        reservation.consumable_id = None
        session.add(reservation)

    await session.delete(consumable)
    return None


async def purge_user(session: AsyncSession, user: User, *, force: bool = False) -> str | None:
    # Eine Person kann mehrere Gegenstände gleichzeitig ausgeliehen/
    # reserviert haben - bei force müssen ALLE geschlossen werden.
    open_lendings = (await session.exec(select(Lending).where(Lending.worker_id == user.id, Lending.returned_at.is_(None)))).all()
    if open_lendings:
        if not force:
            return f"'{user.full_name}' hat noch eine offene Ausleihe - erst zurückgeben."
        for open_lending in open_lendings:
            open_lending.returned_at = utcnow()
            session.add(open_lending)
    open_reservations = (
        await session.exec(
            select(Reservation).where(Reservation.worker_id == user.id, Reservation.fulfilled_at.is_(None), Reservation.cancelled_at.is_(None))
        )
    ).all()
    if open_reservations:
        if not force:
            return f"'{user.full_name}' hat noch eine offene Reservierung - erst stornieren oder abholen lassen."
        for open_reservation in open_reservations:
            open_reservation.cancelled_at = utcnow()
            session.add(open_reservation)
    open_cons_reservations = (
        await session.exec(
            select(ConsumableReservation).where(
                ConsumableReservation.worker_id == user.id,
                ConsumableReservation.fulfilled_at.is_(None),
                ConsumableReservation.cancelled_at.is_(None),
            )
        )
    ).all()
    if open_cons_reservations:
        if not force:
            return f"'{user.full_name}' hat noch eine offene Material-Vormerkung - erst stornieren oder abholen lassen."
        for open_cons_reservation in open_cons_reservations:
            open_cons_reservation.cancelled_at = utcnow()
            session.add(open_cons_reservation)

    for lending in (await session.exec(select(Lending).where(Lending.worker_id == user.id))).all():
        lending.worker_name_snapshot = user.full_name
        lending.worker_id = None
        session.add(lending)

    for usage in (await session.exec(select(ConsumableUsage).where(ConsumableUsage.worker_id == user.id))).all():
        usage.worker_name_snapshot = user.full_name
        usage.worker_id = None
        session.add(usage)

    for reservation in (await session.exec(select(Reservation).where(Reservation.worker_id == user.id))).all():
        reservation.worker_name_snapshot = user.full_name
        reservation.worker_id = None
        session.add(reservation)

    for cons_reservation in (await session.exec(select(ConsumableReservation).where(ConsumableReservation.worker_id == user.id))).all():
        cons_reservation.worker_name_snapshot = user.full_name
        cons_reservation.worker_id = None
        session.add(cons_reservation)

    # Zugriffsrollen haben keinen Snapshot-Mechanismus (reine Rechte, keine
    # Historie) - gehen mit, sonst verwaiste Einträge (gleiches Prinzip wie
    # frueher in admin_settings.delete_user).
    for entry in (await session.exec(select(UserDepartmentRole).where(UserDepartmentRole.user_id == user.id))).all():
        await session.delete(entry)

    await session.delete(user)
    return None


def _sample_names(rows: list, name_fn) -> str:
    """Konkrete Namen statt nur "es gibt welche" - sonst muss der Admin selbst
    erst suchen gehen, WAS eigentlich zurückgegeben/storniert werden muss.
    limit(4) statt 3 beim Aufrufer: eine vierte Zeile signalisiert "es gibt
    noch mehr", ohne eine exakte Gesamtzahl per zusätzlicher COUNT-Abfrage
    ermitteln zu müssen."""
    names = ", ".join(name_fn(r) for r in rows[:3])
    if len(rows) > 3:
        names += ", …"
    return names


async def _close_open_or_block(
    session: AsyncSession,
    model,
    *,
    where: list,
    close_field: str,
    force: bool,
    name_fn,
    message_label: str,
    message_action: str,
    subject_name: str,
    eager_load=None,
) -> str | None:
    """Für Abteilungs-/Lending-/Reservierungs-artige "offene Vorgänge blockieren,
    außer bei force" Prüfungen: bei force=True alle passenden Zeilen automatisch
    abschließen (close_field = jetzt), sonst bis zu 4 zur Fehlermeldung laden und
    abbrechen, falls welche existieren.

    WICHTIG: im force-Zweig bewusst OHNE eager_load laden - der Aufrufer löscht
    im Anschluss ggf. die referenzierten Zeilen (z.B. purge_item/purge_consumable
    in purge_department) aus der Session. Wäre die Beziehung hier schon eager
    geladen, hielte diese Zeile eine dann gelöschte ORM-Instanz fest - ein
    späteres session.add() darauf kaskadiert auf das tote Objekt und wirft
    InvalidRequestError ("Instance has been deleted"). Der Name wird nur für
    die Fehlermeldung im NICHT-force-Zweig gebraucht, dort ist eager_load
    unkritisch, weil dort ohnehin nichts gelöscht wird."""
    if force:
        rows = (await session.exec(select(model).where(*where))).all()
        for row in rows:
            setattr(row, close_field, utcnow())
            session.add(row)
        return None

    stmt = select(model).where(*where).limit(4)
    if eager_load is not None:
        stmt = stmt.options(selectinload(eager_load))
    rows = (await session.exec(stmt)).all()
    if not rows:
        return None
    names = _sample_names(rows, name_fn)
    return f"'{subject_name}' hat noch {message_label}: {names} - {message_action}"


async def purge_department(session: AsyncSession, department: Department, *, force: bool = False) -> str | None:
    """Löscht eine Abteilung KASKADIEREND statt (wie früher) bei jeder noch
    referenzierenden Zeile zu blockieren - Gegenstände/Verbrauchsmaterial/
    Benutzer der Abteilung werden über die bestehenden purge_item/
    purge_consumable/purge_user mitgelöscht (die ihrerseits schon Name/
    Barcode in die Historie snapshotten), Kategorien/Standorte/Zugriffs-
    Zuweisungen direkt (reine Verwaltungsdaten, keine Historie). Nur
    OFFENE Ausleihen/Reservierungen/Material-Vormerkungen sind aktive
    Geschäftsvorgänge und blockieren normalerweise - mit force=True werden
    sie stattdessen automatisch abgeschlossen (returned_at/cancelled_at =
    jetzt), z.B. zum Aufräumen von Testdaten/Fehleingaben, ohne jede Zeile
    erst händisch suchen und einzeln zurückgeben/stornieren zu müssen. Historie
    wird dabei NIE gelöscht, sondern als Text-
    Schnappschuss erhalten (department_name_snapshot, siehe
    app/models/lending.py etc.) - force ändert daran nichts, es entfällt
    nur die Vorbedingung "muss vorher schon abgeschlossen sein"."""
    dept_id = department.id

    error = await _close_open_or_block(
        session, Lending,
        where=[Lending.department_id == dept_id, Lending.returned_at.is_(None)],
        close_field="returned_at", force=force,
        name_fn=lambda l: l.item.name if l.item else (l.item_name_snapshot or "?"),
        message_label="offene Ausleihen", message_action="erst zurückgeben.",
        subject_name=department.name, eager_load=Lending.item,
    )
    if error:
        return error

    error = await _close_open_or_block(
        session, Reservation,
        where=[Reservation.department_id == dept_id, Reservation.fulfilled_at.is_(None), Reservation.cancelled_at.is_(None)],
        close_field="cancelled_at", force=force,
        name_fn=lambda r: r.item.name if r.item else (r.item_name_snapshot or "?"),
        message_label="offene Reservierungen", message_action="erst stornieren oder abholen lassen.",
        subject_name=department.name, eager_load=Reservation.item,
    )
    if error:
        return error

    error = await _close_open_or_block(
        session, ConsumableReservation,
        where=[
            ConsumableReservation.department_id == dept_id,
            ConsumableReservation.fulfilled_at.is_(None),
            ConsumableReservation.cancelled_at.is_(None),
        ],
        close_field="cancelled_at", force=force,
        name_fn=lambda r: r.consumable.name if r.consumable else (r.consumable_name_snapshot or "?"),
        message_label="offene Material-Vormerkungen", message_action="erst stornieren oder abholen lassen.",
        subject_name=department.name, eager_load=ConsumableReservation.consumable,
    )
    if error:
        return error

    for item in (await session.exec(select(Item).where(Item.department_id == dept_id))).all():
        error = await purge_item(session, item, force=force)
        if error:
            return error

    for consumable in (await session.exec(select(Consumable).where(Consumable.department_id == dept_id))).all():
        error = await purge_consumable(session, consumable, force=force)
        if error:
            return error

    for member in (await session.exec(select(User).where(User.department_id == dept_id))).all():
        error = await purge_user(session, member, force=force)
        if error:
            return error

    for category in (await session.exec(select(Category).where(Category.department_id == dept_id))).all():
        for field in (await session.exec(select(CustomFieldDefinition).where(CustomFieldDefinition.category_id == category.id))).all():
            for value in (await session.exec(select(CustomFieldValue).where(CustomFieldValue.field_id == field.id))).all():
                await session.delete(value)
            await session.delete(field)
        await session.delete(category)

    for location in (await session.exec(select(Location).where(Location.department_id == dept_id))).all():
        await session.delete(location)

    for role in (await session.exec(select(UserDepartmentRole).where(UserDepartmentRole.department_id == dept_id))).all():
        await session.delete(role)

    # Verbleibende Historien-Zeilen sind an dieser Stelle garantiert
    # abgeschlossen (offene wurden oben bereits blockiert) - Name als Text
    # erhalten, department_id auf NULL.
    for lending in (await session.exec(select(Lending).where(Lending.department_id == dept_id))).all():
        lending.department_name_snapshot = department.name
        lending.department_id = None
        session.add(lending)

    for reservation in (await session.exec(select(Reservation).where(Reservation.department_id == dept_id))).all():
        reservation.department_name_snapshot = department.name
        reservation.department_id = None
        session.add(reservation)

    for usage in (await session.exec(select(ConsumableUsage).where(ConsumableUsage.department_id == dept_id))).all():
        usage.department_name_snapshot = department.name
        usage.department_id = None
        session.add(usage)

    for cons_reservation in (await session.exec(select(ConsumableReservation).where(ConsumableReservation.department_id == dept_id))).all():
        cons_reservation.department_name_snapshot = department.name
        cons_reservation.department_id = None
        session.add(cons_reservation)

    await session.delete(department)
    return None
