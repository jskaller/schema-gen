
from __future__ import annotations
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
import json

from app.models import Run

async def record_run(session: AsyncSession, result: dict):
    """Persist a run into the database, serializing complex fields."""
    def _safe(val):
        if val is None:
            return None
        if isinstance(val, (str, int, float)):
            return val
        try:
            return json.dumps(val)
        except Exception:
            return str(val)

    run = Run(
        created_at=datetime.utcnow(),
        url=result.get("url"),
        title=result.get("subject") or result.get("topic"),
        topic=result.get("topic"),
        subject=result.get("subject"),
        audience=_safe(result.get("audience")),
        address=_safe(result.get("address")),
        phone=_safe(result.get("phone")),
        score_overall=result.get("overall"),
        valid=bool(result.get("valid")),
        jsonld=_safe(result.get("jsonld")),
        details=_safe(result.get("details")),
        validation_errors=_safe(result.get("validation_errors")),
        comparisons=_safe(result.get("comparisons")),
        comparison_notes=_safe(result.get("comparison_notes")),
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run

async def list_runs(session: AsyncSession, q: str | None = None, limit: int = 100):
    stmt = select(Run).order_by(Run.created_at.desc()).limit(limit)
    if q:
        stmt = stmt.filter(Run.url.contains(q))
    res = await session.execute(stmt)
    return res.scalars().all()

async def get_run(session: AsyncSession, run_id: int):
    res = await session.execute(select(Run).where(Run.id == run_id))
    return res.scalars().first()
