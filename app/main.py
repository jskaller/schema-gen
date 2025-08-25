
from fastapi import FastAPI, Request, Form, UploadFile, File, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.datastructures import URL

import json
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import init_db, get_session
from app.services.settings import get_settings, update_settings
from app.services.providers import list_ollama_models
from app.services.ai import get_provider, GenerationInputs
from app.services.schemas import load_schema, defaults_for, AVAILABLE_PAGE_TYPES

app = FastAPI(title="Schema Gen", version="1.3.0")
templates = Jinja2Templates(directory="app/web/templates")

@app.on_event("startup")
async def _startup():
    await init_db()

@app.get("/admin", response_class=HTMLResponse)
async def admin_get(request: Request, session: AsyncSession = Depends(get_session), ok: str | None = None):
    s = await get_settings(session)
    models = await list_ollama_models()
    return templates.TemplateResponse("admin.html", {
        "request": request, "settings": s, "ok": ok, "ollama_models": models, "page_types": AVAILABLE_PAGE_TYPES
    })

@app.post("/admin", response_class=HTMLResponse)
async def admin_post(
    request: Request,
    provider: str = Form("dummy"),
    provider_model: str = Form(""),
    page_type: str = Form("Hospital"),
    required_fields: str = Form(""),
    recommended_fields: str = Form(""),
    use_defaults: str = Form(None),
    session: AsyncSession = Depends(get_session),
):
    try:
        if use_defaults:
            defs = defaults_for(page_type)
            req, rec = defs["required"], defs["recommended"]
        else:
            req = json.loads(required_fields) if required_fields.strip() else None
            rec = json.loads(recommended_fields) if recommended_fields.strip() else None
    except Exception as e:
        s = await get_settings(session)
        models = await list_ollama_models()
        return templates.TemplateResponse("admin.html", {"request": request, "settings": s, "error": str(e), "ollama_models": models, "page_types": AVAILABLE_PAGE_TYPES})
    await update_settings(session, provider, page_type, req, rec, provider_model or None)
    return RedirectResponse(url="/admin?ok=1", status_code=303)

@app.post("/admin/test", response_class=HTMLResponse)
async def admin_test(request: Request, session: AsyncSession = Depends(get_session)):
    s = await get_settings(session)
    provider = get_provider(s.provider, model=s.provider_model)
    sample_inputs = GenerationInputs(url="http://example.org", cleaned_text="Example text", page_type=s.page_type)
    result = await provider.generate_jsonld(sample_inputs)
    models = await list_ollama_models()
    return templates.TemplateResponse("admin.html", {
        "request": request, "settings": s, "test_result": result, "ollama_models": models, "page_types": AVAILABLE_PAGE_TYPES
    })
