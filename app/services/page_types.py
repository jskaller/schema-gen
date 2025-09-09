# app/services/page_types.py
from __future__ import annotations
from typing import Dict, List, Optional

from app.services.settings import get_settings, update_settings

def _norm_label(s: str | None) -> str:
    return (s or "").strip()

def ci_lookup(mapping: Dict[str, dict], label: str | None) -> Optional[dict]:
    if not mapping or not label:
        return None
    target = _norm_label(label).lower()
    for k, v in mapping.items():
        if _norm_label(k).lower() == target:
            return v
    return None

async def get_map(session) -> Dict[str, dict]:
    s = await get_settings(session)
    return dict(s.page_type_map or {})

async def _save_map(session, new_map: Dict[str, dict]) -> None:
    # Match update_settings positional signature used in app.main admin_post:
    # update_settings(session, provider, page_type, req, rec, provider_model, ptm)
    s = await get_settings(session)
    provider = getattr(s, "provider", None) or "dummy"
    page_type = getattr(s, "page_type", None) or "Hospital"
    req = getattr(s, "required_fields", None)
    rec = getattr(s, "recommended_fields", None)
    provider_model = getattr(s, "provider_model", None)
    ptm = new_map
    await update_settings(session, provider, page_type, req, rec, provider_model, ptm)

async def upsert_type(session, label: str, primary: str, secondary: List[str] | None) -> None:
    m = await get_map(session)
    m[_norm_label(label)] = {
        "primary": _norm_label(primary),
        "secondary": [_norm_label(x) for x in (secondary or []) if _norm_label(x)],
    }
    await _save_map(session, m)

async def delete_type(session, label: str) -> bool:
    m = await get_map(session)
    key = None
    target = _norm_label(label).lower()
    for k in m.keys():
        if _norm_label(k).lower() == target:
            key = k
            break
    if key is None:
        return False
    m.pop(key, None)
    await _save_map(session, m)
    return True
