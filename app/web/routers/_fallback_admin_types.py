from __future__ import annotations
from typing import Dict, Any, List
from fastapi import APIRouter, Request, Depends, Form
from fastapi.templating import Jinja2Templates
from starlette.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_session
from app.services.settings import get_settings
from app.services.page_types import get_map, upsert_type, delete_type

templates = Jinja2Templates(directory="app/web/templates")
router = APIRouter()

@router.get("/types", response_class=HTMLResponse)
async def admin_types_page(request: Request, session: AsyncSession = Depends(get_session)):
    settings = await get_settings(session)
    mapping = await get_map(session)
    # mapping is a Dict[str, Dict[str, Any]]
    return templates.TemplateResponse("admin_types.html", {"request": request, "settings": settings, "mapping": mapping})

@router.post("/types/upsert", response_class=HTMLResponse)
async def admin_types_upsert(request: Request,
                             label: str = Form(...),
                             primary: str = Form(...),
                             secondary: str = Form(""),
                             session: AsyncSession = Depends(get_session)):
    secondaries = [s.strip() for s in (secondary or "").split(",") if s.strip()]
    await upsert_type(session, label, primary, secondaries)
    return RedirectResponse(url="/admin/types", status_code=303)

@router.post("/types/delete", response_class=HTMLResponse)
async def admin_types_delete(request: Request,
                             label: str = Form(...),
                             session: AsyncSession = Depends(get_session)):
    await delete_type(session, label)
    return RedirectResponse(url="/admin/types", status_code=303)
