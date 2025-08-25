
from __future__ import annotations
from typing import Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.settings import get_settings, update_settings

DEFAULT_MAP = {
    "Hospital": {"primary": "Hospital", "secondary": []},
    "MedicalClinic": {"primary": "MedicalClinic", "secondary": []},
    "Physician": {"primary": "Physician", "secondary": []},
}

async def get_map(session: AsyncSession) -> Dict[str, Dict[str, Any]]:
    s = await get_settings(session)
    return s.page_type_map or DEFAULT_MAP

async def set_map(session: AsyncSession, mapping: Dict[str, Dict[str, Any]]):
    s = await get_settings(session)
    s.page_type_map = mapping
    await update_settings(session, s.provider, s.page_type, s.required_fields, s.recommended_fields, s.provider_model)
    return s.page_type_map

async def upsert_type(session: AsyncSession, label: str, primary: str, secondaries: list[str]):
    m = await get_map(session)
    m[label] = {"primary": primary, "secondary": secondaries or []}
    await set_map(session, m)
    return m

async def delete_type(session: AsyncSession, label: str):
    m = await get_map(session)
    if label in m:
        del m[label]
        await set_map(session, m)
    return m
