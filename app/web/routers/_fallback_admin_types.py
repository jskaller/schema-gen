
from __future__ import annotations
from fastapi import APIRouter, Request, Depends
from starlette.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
import json
from app.db import get_session
from app.services.settings import get_settings, update_settings

templates = Jinja2Templates(directory="app/web/templates")
router = APIRouter()

@router.get("/types", response_class=HTMLResponse)
async def types_page(request: Request, session: AsyncSession = Depends(get_session)):
    s = await get_settings(session)
    mapping = s.page_type_map or {}
    return templates.TemplateResponse("admin_types.html", {
        "request": request,
        "mapping": mapping,
        "page_type_map": json.dumps(mapping, indent=2)
    })

@router.post("/types/save")
async def types_save(request: Request, session: AsyncSession = Depends(get_session)):
    form = await request.form()
    raw = form.get("page_type_map") or form.get("mapping_json") or "{}"
    try:
        data = json.loads(raw)
    except Exception as e:
        return templates.TemplateResponse("admin_types.html", {
            "request": request,
            "mapping": {},
            "error": f"Invalid JSON: {e}",
            "page_type_map": raw,
        }, status_code=400)
    await update_settings(session, page_type_map=data)
    return RedirectResponse(url="/admin/types", status_code=303)

@router.get("/types.json")
async def types_json(session: AsyncSession = Depends(get_session)):
    s = await get_settings(session)
    return JSONResponse(s.page_type_map or {})
