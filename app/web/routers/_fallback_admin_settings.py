from __future__ import annotations
from fastapi import APIRouter, Request, Depends
from starlette.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_session
from app.services.settings import update_settings, get_settings

router = APIRouter()

def _build_provider_config(form) -> dict:
    pc = {}
    def put(path: str, val: str | None):
        if val is None:
            return
        top, sub = path.split(".", 1)
        pc.setdefault(top, {})[sub] = (val or "").strip()
    if "ollama.host" in form:
        put("ollama.host", form.get("ollama.host"))
    if "gemini.api_key" in form:
        put("gemini.api_key", form.get("gemini.api_key"))
    if "openai.api_key" in form:
        put("openai.api_key", form.get("openai.api_key"))
    return pc

@router.post("/save")
async def save_settings(request: Request, session: AsyncSession = Depends(get_session)):
    form = await request.form()
    provider = (form.get("provider") or "").strip() or None
    provider_model = (form.get("provider_model") or "").strip() or None  # <-- plain string
    pc = _build_provider_config(form)

    # Persist provider & model (string)
    await update_settings(session, provider=provider, provider_model=provider_model)

    # Merge provider config under extract_config["_provider"]
    s = await get_settings(session)
    if hasattr(s, "model_dump"):
        extract = (s.model_dump().get("extract_config") or {})
    elif hasattr(s, "dict"):
        extract = (s.dict().get("extract_config") or {})
    elif isinstance(s, dict):
        extract = s.get("extract_config") or {}
    else:
        extract = getattr(s, "extract_config", {}) or {}
    if not isinstance(extract, dict):
        extract = {}
    extract["_provider"] = pc
    await update_settings(session, extract_config=extract)

    return RedirectResponse(url="/admin", status_code=303)
