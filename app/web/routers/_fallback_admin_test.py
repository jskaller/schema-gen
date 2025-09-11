from __future__ import annotations
from typing import Dict, Any
from fastapi import APIRouter, Depends, Form
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_session
from app.services.settings import get_settings
import httpx, time

router = APIRouter()

def _model_dump(obj: Any) -> dict:
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict"):
        return obj.dict()
    if isinstance(obj, dict):
        return obj
    return {}

async def _test_ollama(host: str) -> Dict[str, Any]:
    url = f"{host.rstrip('/')}/api/tags"
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(url)
            ok = r.status_code == 200
            data = r.json() if ok else {"status_code": r.status_code, "text": r.text[:200]}
    except Exception as e:
        return {"ok": False, "latency_ms": int((time.perf_counter()-t0)*1000), "error": str(e), "url": url}
    return {"ok": True, "latency_ms": int((time.perf_counter()-t0)*1000), "models_found": len(data.get("models", [])), "url": url}

async def _test_keyed(key: str) -> Dict[str, Any]:
    ok = bool(key and len(key) > 10)
    return {"ok": ok, "detail": ("key present" if ok else "missing/too short")}

@router.post("/test")
async def test_settings(provider: str = Form("ollama"), session: AsyncSession = Depends(get_session)):
    s = await get_settings(session)
    sd = _model_dump(s)
    pc = sd.get("provider_config") or {}
    if not pc:
        ex = sd.get("extract_config") or {}
        if isinstance(ex, dict):
            pc = ex.get("_provider") or {}

    results: Dict[str, Any] = {"provider": provider, "checks": {}, "config_source": ("provider_config" if sd.get("provider_config") else "extract_config._provider" if pc else "none")}

    if provider == "ollama":
        host = (pc.get("ollama") or {}).get("host") or "http://localhost:11434"
        results["checks"]["ollama"] = await _test_ollama(host)
    elif provider == "gemini":
        key = (pc.get("gemini") or {}).get("api_key") or ""
        results["checks"]["gemini"] = await _test_keyed(key)
    elif provider == "openai":
        key = (pc.get("openai") or {}).get("api_key") or ""
        results["checks"]["openai"] = await _test_keyed(key)

    results["ok"] = bool(results["checks"].get(provider, {}).get("ok"))
    return results
