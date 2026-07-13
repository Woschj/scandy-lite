"""
Regressionstests für echte Custom Fields (app.core.custom_fields,
app.routers.admin_settings, app.routers.items): admin-definierbare
Zusatzfelder pro Kategorie, nur für Gegenstände (siehe migrations_legacy/
README.md - im alten Scandy2 vorhanden, hier gezielt nachgeholt).
"""
import pytest_asyncio
from sqlmodel import select

from app.core.security import hash_password
from app.models.common import UserRole
from app.models.custom_field import CustomFieldDefinition
from app.models.item import Item
from app.models.preset import Category
from app.models.user import User
from app.models.user_department_role import UserDepartmentRole
from tests.conftest import csrf_value, login


@pytest_asyncio.fixture
async def admin_client(client, session_maker):
    async with session_maker() as session:
        admin = User(username="admin", is_admin=True, hashed_password=hash_password("adminpass123"))
        session.add(admin)
        await session.commit()
    await login(client, "admin", "adminpass123")
    return client


@pytest_asyncio.fixture
async def laptops_category(session_maker, seed_data):
    async with session_maker() as session:
        category = Category(name="Laptops", department_id=seed_data["department_id"])
        session.add(category)
        await session.commit()
        await session.refresh(category)
        return category


async def _create_field(admin_client, category_id, *, name="MAC-Adresse", field_type="text", options="", visible_to_all=True):
    resp = await admin_client.post(
        "/admin/custom-fields/new",
        data={
            "category_id": str(category_id),
            "name": name,
            "field_type": field_type,
            "options": options,
            "visible_to_all": "true" if visible_to_all else "",
            "csrf_token": csrf_value(admin_client),
        },
    )
    assert resp.status_code == 303
    return resp


async def _create_item(admin_client, department_id, *, barcode="LAPTOP-1", category="Laptops"):
    resp = await admin_client.post(
        "/items/new",
        data={
            "department_id": str(department_id),
            "barcode": barcode,
            "name": "ThinkPad",
            "category": category,
            "location": "",
            "notes": "",
            "csrf_token": csrf_value(admin_client),
        },
    )
    assert resp.status_code == 303
    return resp


async def test_custom_field_value_appears_on_detail_page(admin_client, session_maker, seed_data, laptops_category):
    await _create_field(admin_client, laptops_category.id, visible_to_all=True)
    await _create_item(admin_client, seed_data["department_id"])

    async with session_maker() as session:
        item = (await session.exec(select(Item).where(Item.barcode == "LAPTOP-1"))).first()
        field = (await session.exec(select(CustomFieldDefinition).where(CustomFieldDefinition.category_id == laptops_category.id))).first()

    edit_resp = await admin_client.post(
        f"/items/{item.id}/edit",
        data={
            "barcode": "LAPTOP-1",
            "name": "ThinkPad",
            "category": "Laptops",
            "location": "",
            "notes": "",
            "status": "verfuegbar",
            f"custom_field_{field.id}": "AA:BB:CC:DD:EE:FF",
            "csrf_token": csrf_value(admin_client),
        },
    )
    assert edit_resp.status_code == 303

    detail_resp = await admin_client.get(f"/items/{item.id}")
    assert detail_resp.status_code == 200
    assert "AA:BB:CC:DD:EE:FF" in detail_resp.text


async def test_field_not_visible_to_all_is_hidden_from_external_user(admin_client, session_maker, seed_data, laptops_category):
    await _create_field(admin_client, laptops_category.id, visible_to_all=False)
    await _create_item(admin_client, seed_data["department_id"])

    async with session_maker() as session:
        item = (await session.exec(select(Item).where(Item.barcode == "LAPTOP-1"))).first()
        field = (await session.exec(select(CustomFieldDefinition).where(CustomFieldDefinition.category_id == laptops_category.id))).first()

        external_user = User(username="external", is_admin=False, hashed_password=hash_password("externalpass123"))
        session.add(external_user)
        await session.commit()
        await session.refresh(external_user)
        session.add(UserDepartmentRole(user_id=external_user.id, department_id=seed_data["department_id"], role=UserRole.NUTZER))
        await session.commit()

    await admin_client.post(
        f"/items/{item.id}/edit",
        data={
            "barcode": "LAPTOP-1",
            "name": "ThinkPad",
            "category": "Laptops",
            "location": "",
            "notes": "",
            "status": "verfuegbar",
            f"custom_field_{field.id}": "AA:BB:CC:DD:EE:FF",
            "csrf_token": csrf_value(admin_client),
        },
    )

    # Als Admin/Mitarbeiter (can_manage) sichtbar
    admin_detail = await admin_client.get(f"/items/{item.id}")
    assert "AA:BB:CC:DD:EE:FF" in admin_detail.text

    # Derselbe Client, jetzt als externer Nutzer (nur Nutzer-Rolle) eingeloggt
    # (login() überschreibt einfach das Session-Cookie) - NICHT sichtbar
    await login(admin_client, "external", "externalpass123")
    external_detail = await admin_client.get(f"/items/{item.id}")
    assert external_detail.status_code == 200
    assert "AA:BB:CC:DD:EE:FF" not in external_detail.text


async def test_category_with_custom_fields_cannot_be_deleted(admin_client, laptops_category):
    await _create_field(admin_client, laptops_category.id)

    resp = await admin_client.post(
        f"/admin/categories/{laptops_category.id}/delete",
        data={"csrf_token": csrf_value(admin_client)},
    )
    assert resp.status_code == 303
    assert "error=" in resp.headers["location"]


async def test_new_and_edit_item_forms_render_without_error(admin_client, session_maker, seed_data, laptops_category):
    """Rendert tatsächlich (nicht nur POST) - deckt Template-/Filter-Fehler ab
    (z.B. das Alpine-x-data-JSON in items/form.html), die ein reiner POST-Test
    nicht bemerkt hätte, weil GET-Formulare vorher nie gerendert wurden."""
    await _create_field(admin_client, laptops_category.id)

    new_resp = await admin_client.get("/items/new")
    assert new_resp.status_code == 200

    await _create_item(admin_client, seed_data["department_id"])
    async with session_maker() as session:
        item = (await session.exec(select(Item).where(Item.barcode == "LAPTOP-1"))).first()

    edit_resp = await admin_client.get(f"/items/{item.id}/edit")
    assert edit_resp.status_code == 200
    assert "MAC-Adresse" in edit_resp.text


async def test_number_field_rejects_non_numeric_value(admin_client, session_maker, seed_data, laptops_category):
    await _create_field(admin_client, laptops_category.id, name="RAM (GB)", field_type="number")
    await _create_item(admin_client, seed_data["department_id"])

    async with session_maker() as session:
        item = (await session.exec(select(Item).where(Item.barcode == "LAPTOP-1"))).first()
        field = (await session.exec(select(CustomFieldDefinition).where(CustomFieldDefinition.category_id == laptops_category.id))).first()

    resp = await admin_client.post(
        f"/items/{item.id}/edit",
        data={
            "barcode": "LAPTOP-1",
            "name": "ThinkPad",
            "category": "Laptops",
            "location": "",
            "notes": "",
            "status": "verfuegbar",
            f"custom_field_{field.id}": "nicht-numerisch",
            "csrf_token": csrf_value(admin_client),
        },
    )
    assert resp.status_code == 400
    assert "Zahl erwartet" in resp.text
