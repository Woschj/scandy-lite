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


async def purge_item(session: AsyncSession, item: Item) -> str | None:
    open_lending = await session.exec(select(Lending).where(Lending.item_id == item.id, Lending.returned_at.is_(None)))
    if open_lending.first():
        return f"'{item.name}' hat noch eine offene Ausleihe - erst zurückgeben."
    open_reservation = await session.exec(
        select(Reservation).where(Reservation.item_id == item.id, Reservation.fulfilled_at.is_(None), Reservation.cancelled_at.is_(None))
    )
    if open_reservation.first():
        return f"'{item.name}' hat noch eine offene Reservierung - erst stornieren oder abholen lassen."

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


async def purge_consumable(session: AsyncSession, consumable: Consumable) -> str | None:
    open_reservation = await session.exec(
        select(ConsumableReservation).where(
            ConsumableReservation.consumable_id == consumable.id,
            ConsumableReservation.fulfilled_at.is_(None),
            ConsumableReservation.cancelled_at.is_(None),
        )
    )
    if open_reservation.first():
        return f"'{consumable.name}' hat noch eine offene Vormerkung - erst stornieren oder abholen lassen."

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


async def purge_user(session: AsyncSession, user: User) -> str | None:
    open_lending = await session.exec(select(Lending).where(Lending.worker_id == user.id, Lending.returned_at.is_(None)))
    if open_lending.first():
        return f"'{user.full_name}' hat noch eine offene Ausleihe - erst zurückgeben."
    open_reservation = await session.exec(
        select(Reservation).where(Reservation.worker_id == user.id, Reservation.fulfilled_at.is_(None), Reservation.cancelled_at.is_(None))
    )
    if open_reservation.first():
        return f"'{user.full_name}' hat noch eine offene Reservierung - erst stornieren oder abholen lassen."
    open_cons_reservation = await session.exec(
        select(ConsumableReservation).where(
            ConsumableReservation.worker_id == user.id,
            ConsumableReservation.fulfilled_at.is_(None),
            ConsumableReservation.cancelled_at.is_(None),
        )
    )
    if open_cons_reservation.first():
        return f"'{user.full_name}' hat noch eine offene Material-Vormerkung - erst stornieren oder abholen lassen."

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


async def purge_department(session: AsyncSession, department: Department) -> str | None:
    """Löscht eine Abteilung KASKADIEREND statt (wie früher) bei jeder noch
    referenzierenden Zeile zu blockieren - Gegenstände/Verbrauchsmaterial/
    Benutzer der Abteilung werden über die bestehenden purge_item/
    purge_consumable/purge_user mitgelöscht (die ihrerseits schon Name/
    Barcode in die Historie snapshotten), Kategorien/Standorte/Zugriffs-
    Zuweisungen direkt (reine Verwaltungsdaten, keine Historie). Nur
    OFFENE Ausleihen/Reservierungen/Material-Vormerkungen sind aktive
    Geschäftsvorgänge und blockieren weiterhin - reine (abgeschlossene)
    Historie wird nie gelöscht, sondern als Text-Schnappschuss erhalten
    (department_name_snapshot, siehe app/models/lending.py etc.)."""
    dept_id = department.id

    open_lending = await session.exec(select(Lending).where(Lending.department_id == dept_id, Lending.returned_at.is_(None)))
    if open_lending.first():
        return f"'{department.name}' hat noch offene Ausleihen - erst zurückgeben."
    open_reservation = await session.exec(
        select(Reservation).where(Reservation.department_id == dept_id, Reservation.fulfilled_at.is_(None), Reservation.cancelled_at.is_(None))
    )
    if open_reservation.first():
        return f"'{department.name}' hat noch offene Reservierungen - erst stornieren oder abholen lassen."
    open_cons_reservation = await session.exec(
        select(ConsumableReservation).where(
            ConsumableReservation.department_id == dept_id,
            ConsumableReservation.fulfilled_at.is_(None),
            ConsumableReservation.cancelled_at.is_(None),
        )
    )
    if open_cons_reservation.first():
        return f"'{department.name}' hat noch offene Material-Vormerkungen - erst stornieren oder abholen lassen."

    for item in (await session.exec(select(Item).where(Item.department_id == dept_id))).all():
        error = await purge_item(session, item)
        if error:
            return error

    for consumable in (await session.exec(select(Consumable).where(Consumable.department_id == dept_id))).all():
        error = await purge_consumable(session, consumable)
        if error:
            return error

    for member in (await session.exec(select(User).where(User.department_id == dept_id))).all():
        error = await purge_user(session, member)
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
