"""
Sichtbarkeits-/Ausleih-Berechtigung für Nutzer (Studierende etc.), entkoppelt
von der Abteilungs-Zugehörigkeit des Gegenstands.

Ein Worker mit zugewiesener Gruppe sieht/reserviert Gegenstände aus GENAU den
Abteilungen, auf die die Gruppe Zugriff hat - unabhängig von worker.department_id.
Ohne Gruppe fällt es auf die eigene department_id zurück (Rückwärtskompatibilität
für Mitarbeiter-Datensätze, die noch keiner Gruppe zugeordnet wurden).
"""
import uuid

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.group import GroupDepartmentAccess
from app.models.worker import Worker


async def get_visible_department_ids(session: AsyncSession, worker: Worker | None) -> list[uuid.UUID]:
    if worker is None:
        return []

    if worker.group_id:
        result = await session.exec(
            select(GroupDepartmentAccess.department_id).where(GroupDepartmentAccess.group_id == worker.group_id)
        )
        ids = list(result.all())
        if ids:
            return ids
        # Gruppe existiert, hat aber (noch) keine Abteilung freigeschaltet ->
        # bewusst NICHTS sichtbar, nicht heimlich auf die Heimat-Abteilung
        # zurückfallen (sonst merkt niemand, dass die Gruppen-Konfiguration fehlt).
        return []

    return [worker.department_id]
