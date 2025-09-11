from __future__ import annotations
from fastapi import APIRouter, Request, Depends
from starlette.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_session
from app.services.settings import update_settings

router = APIRouter()

@router.post("/extract")
async def save_extract(request: Request, session: AsyncSession = Depends(get_session)):
    form = await request.form()
    cfg = {
        "shadow": bool(form.get("shadow")),
        "inLanguage": bool(form.get("inLanguage")),
        "canonical": bool(form.get("canonical")),
        "dateModified": bool(form.get("dateModified")),
    }
    await update_settings(session, extract_config=cfg)
    return RedirectResponse(url="/admin", status_code=303)
