from __future__ import annotations
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_session
from app.services.settings import get_settings
import httpx

router = APIRouter()

PRESETS: Dict[str, List[str]] = {
    "ollama": [
        "llama3.1:8b-instruct-q4_1",
        "llama3.1:70b-instruct",
        "qwen2.5:7b-instruct",
        "mistral-nemo:12b-instruct",
    ],
    "gemini": ["gemini-1.5-flash", "gemini-1.5-pro"],
    "openai": ["gpt-4o", "gpt-4o-mini"],
}

def _model_dump(obj: Any) -> dict:
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict"):
        return obj.dict()
    if isinstance(obj, dict):
        return obj
    return {}

@router.get("/models")
async def list_models(provider: str = Query("ollama"), session: AsyncSession = Depends(get_session)):
    s = await get_settings(session)
    sd = _model_dump(s)
    pc = sd.get("provider_config") or {}
    if not pc:
        ex = sd.get("extract_config") or {}
        if isinstance(ex, dict):
            pc = ex.get("_provider") or {}

    models: List[str] = []
    if provider == "ollama":
        host = (pc.get("ollama") or {}).get("host") or "http://localhost:11434"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{host.rstrip('/')}/api/tags")
                r.raise_for_status()
                data = r.json()
                models = [m.get("name") for m in data.get("models", []) if m.get("name")]
        except Exception as e:
            return {"provider": provider, "models": PRESETS["ollama"], "error": str(e), "host": host}
    elif provider == "gemini":
        models = PRESETS["gemini"]
    elif provider == "openai":
        models = PRESETS["openai"]
    else:
        return {"error": f"unknown provider {provider}"}

    return {"provider": provider, "models": models}
