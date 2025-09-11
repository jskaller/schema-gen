from __future__ import annotations
from fastapi import APIRouter, Request, Depends
from starlette.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_session
from app.services.settings import get_settings

templates = Jinja2Templates(directory="app/web/templates")
router = APIRouter()

@router.get("", response_class=HTMLResponse)
async def admin_index(request: Request, session: AsyncSession = Depends(get_session)):
    settings = await get_settings(session)
    return templates.TemplateResponse("admin.html", {"request": request, "settings": settings})

# Alias /admin/ -> /admin
@router.get("/", response_class=HTMLResponse)
async def admin_index_slash(request: Request, session: AsyncSession = Depends(get_session)):
    settings = await get_settings(session)
    return templates.TemplateResponse("admin.html", {"request": request, "settings": settings})
