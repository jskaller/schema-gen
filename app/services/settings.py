
from __future__ import annotations
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.settings_models import Settings

DEFAULT_REQUIRED = ["@context","@type","name","url"]
DEFAULT_RECOMMENDED = ["description","telephone","address","audience","dateModified","sameAs","medicalSpecialty"]

async def get_settings(session: AsyncSession) -> Settings:
    res = await session.execute(select(Settings).limit(1))
    s = res.scalars().first()
    if not s:
        s = Settings()
        session.add(s)
        await session.commit()
        await session.refresh(s)
    return s

async def update_settings(session: AsyncSession, provider: str, page_type: str, required: list, recommended: list) -> Settings:
    s = await get_settings(session)
    s.provider = provider or s.provider
    s.page_type = page_type or s.page_type
    s.required_fields = required or s.required_fields
    s.recommended_fields = recommended or s.recommended_fields
    session.add(s)
    await session.commit()
    await session.refresh(s)
    return s
