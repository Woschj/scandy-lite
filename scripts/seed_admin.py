"""
Bootstrap-Skript: legt (falls nicht vorhanden) eine Default-Abteilung und
einen ersten Admin-User an. Idempotent - kann gefahrlos mehrfach laufen.

Nutzung:
    python -m scripts.seed_admin --username admin --password ****** --department-code werkstatt --department-name Werkstatt
"""
import argparse
import asyncio

from sqlmodel import select

from app.core.database import async_session_maker
from app.core.security import hash_password
from app.models.common import UserRole
from app.models.department import Department
from app.models.user import User


async def seed(username: str, password: str, department_code: str, department_name: str) -> None:
    async with async_session_maker() as session:
        result = await session.exec(select(Department).where(Department.code == department_code))
        department = result.first()
        if not department:
            department = Department(code=department_code, name=department_name)
            session.add(department)
            await session.commit()
            await session.refresh(department)
            print(f"Abteilung angelegt: {department.name} ({department.code})")
        else:
            print(f"Abteilung existiert bereits: {department.name} ({department.code})")

        result = await session.exec(select(User).where(User.username == username))
        user = result.first()
        if user:
            print(f"User '{username}' existiert bereits - kein Passwort überschrieben.")
            return

        user = User(
            username=username,
            role=UserRole.ADMIN,
            hashed_password=hash_password(password),
            department_id=department.id,
        )
        session.add(user)
        await session.commit()
        print(f"Admin-User '{username}' angelegt.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ersten Admin-User + Default-Abteilung anlegen")
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--department-code", default="werkstatt")
    parser.add_argument("--department-name", default="Werkstatt")
    args = parser.parse_args()

    asyncio.run(seed(args.username, args.password, args.department_code, args.department_name))


if __name__ == "__main__":
    main()
