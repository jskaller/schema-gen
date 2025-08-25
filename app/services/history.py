
from __future__ import annotations
from typing import Optional, Dict, Any, List
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Run

async def record_run(session: AsyncSession, payload: Dict[str, Any]) -> Run:
    run = Run(
        url=payload["url"],
        title=payload.get("title"),
        topic=payload.get("topic"),
        subject=payload.get("subject"),
        audience=payload.get("audience"),
        address=payload.get("address"),
        phone=payload.get("phone"),
        score_overall=payload.get("overall"),
        valid=payload.get("valid"),
        jsonld=payload.get("jsonld") or {},
        details=payload.get("details") or {},
        validation_errors=payload.get("validation_errors") or [],
        comparisons=payload.get("comparisons") or [],
        comparison_notes=payload.get("comparison_notes") or [],
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run

async def list_runs(session: AsyncSession, q: Optional[str] = None, limit: int = 100) -> List[Run]:
    stmt = select(Run).order_by(desc(Run.created_at)).limit(limit)
    if q:
        like = f"%{q}%"
        stmt = select(Run).where(Run.url.like(like)).order_by(desc(Run.created_at)).limit(limit)
    res = await session.execute(stmt)
    return list(res.scalars().all())

async def get_run(session: AsyncSession, run_id: int) -> Optional[Run]:
    res = await session.get(Run, run_id)
    return res
