from __future__ import annotations
from typing import Optional, Dict, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.settings_models import Settings

async def get_settings(session: AsyncSession) -> Settings:
    res = await session.execute(select(Settings).limit(1))
    s = res.scalars().first()
    if s is None:
        s = Settings()
        session.add(s)
        await session.commit()
        await session.refresh(s)
    return s

async def update_settings(
    session: AsyncSession,
    provider: Optional[str] = None,
    provider_model: Optional[str] = None,
    page_type: Optional[str] = None,
    page_type_map: Optional[Dict[str, dict]] = None,
    required: Optional[List[str]] = None,
    recommended: Optional[List[str]] = None,
) -> Settings:
    s = await get_settings(session)
    if provider is not None:
        s.provider = provider
    if provider_model is not None:
        s.provider_model = provider_model
    if page_type is not None:
        s.page_type = page_type
    if page_type_map is not None:
        s.page_type_map = page_type_map
    if required is not None:
        s.required_fields = required
    if recommended is not None:
        s.recommended_fields = recommended
    session.add(s)
    await session.commit()
    await session.refresh(s)
    return s