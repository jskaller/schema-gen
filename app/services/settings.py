
from __future__ import annotations
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from app.settings_models import Settings

DEFAULT_REQUIRED = ["@context","@type","name","url"]
DEFAULT_RECOMMENDED = ["description","telephone","address","audience","dateModified","sameAs","medicalSpecialty"]

async def _ensure_provider_model_column(session: AsyncSession):
    # Add column if missing (SQLite only). Ignore errors.
    try:
        res = await session.execute(text("PRAGMA table_info(settings)"))
        cols = [row[1] for row in res.fetchall()]
        if "provider_model" not in cols:
            await session.execute(text("ALTER TABLE settings ADD COLUMN provider_model VARCHAR"))
            await session.commit()
    except Exception:
        pass

async def get_settings(session: AsyncSession) -> Settings:
    await _ensure_provider_model_column(session)
    res = await session.execute(select(Settings).limit(1))
    s = res.scalars().first()
    if not s:
        s = Settings()
        session.add(s)
        await session.commit()
        await session.refresh(s)
    return s

async def update_settings(session: AsyncSession, provider: str, page_type: str, required: list | None, recommended: list | None, provider_model: str | None = None) -> Settings:
    s = await get_settings(session)
    if provider:
        s.provider = provider
    if provider_model is not None:
        s.provider_model = provider_model or None
    if page_type:
        s.page_type = page_type
    if required is not None:
        s.required_fields = required
    if recommended is not None:
        s.recommended_fields = recommended
    session.add(s)
    await session.commit()
    await session.refresh(s)
    return s
