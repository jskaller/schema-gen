from __future__ import annotations
from typing import Optional, Dict, List, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError
from app.settings_models import Settings
import json

MIGRATION_DEFAULT_EXTRACT = {
    "shadow": True,
    "inLanguage": True,
    "canonical": True,
    "dateModified": True,
    "telephone": False,
    "logo": False,
    "sameAs": False,
    "address": False,
}

async def _ensure_settings_schema(session: AsyncSession) -> None:
    """Ensure the 'extract_config' column exists on the settings table (SQLite).
    Safe to call repeatedly; no-op if column already present.
    """
    try:
        res = await session.execute(text("PRAGMA table_info('settings')"))
        cols = [row[1] for row in res.fetchall()]  # row[1] is 'name'
        if 'extract_config' not in cols:
            # Add column as TEXT (JSON); set default config on existing rows
            await session.execute(text("ALTER TABLE settings ADD COLUMN extract_config TEXT"))
            await session.execute(
                text("UPDATE settings SET extract_config = :cfg WHERE extract_config IS NULL"),
                { "cfg": json.dumps(MIGRATION_DEFAULT_EXTRACT) }
            )
            await session.commit()
    except Exception:
        # PRAGMA may fail on non-sqlite or odd states; ignore so app can continue
        await session.rollback()

async def get_settings(session: AsyncSession) -> Settings:
    # Try normal path first; on schema error, run migration and retry
    try:
        res = await session.execute(select(Settings).limit(1))
        s = res.scalars().first()
    except OperationalError:
        await _ensure_settings_schema(session)
        res = await session.execute(select(Settings).limit(1))
        s = res.scalars().first()

    if s is None:
        s = Settings()
        session.add(s)
        await session.commit()
        await session.refresh(s)

        # If DB had no row, ensure extract_config has defaults
        if not getattr(s, 'extract_config', None):
            s.extract_config = dict(MIGRATION_DEFAULT_EXTRACT)
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
    extract_config: Optional[Dict[str, Any]] = None,
) -> Settings:
    # Ensure schema before update
    await _ensure_settings_schema(session)

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
    if extract_config is not None:
        s.extract_config = extract_config
    session.add(s)
    await session.commit()
    await session.refresh(s)
    return s