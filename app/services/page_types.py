# app/services/page_types.py
from __future__ import annotations
from typing import Dict, List, Optional, Tuple
from app.services.settings import get_settings, update_settings

def _norm(s: str | None) -> str:
    return (s or "").strip()

def _lc(s: str | None) -> str:
    return _norm(s).lower()

# Map common aliases to canonical Schema.org classes
SCHEMA_CANON = {
    "website": "WebSite",
    "web site": "WebSite",
    "webpage": "WebPage",
    "web page": "WebPage",
    "medicalorganization": "MedicalOrganization",
    "medical organization": "MedicalOrganization",
    "medicalclinic": "MedicalClinic",
    "medical clinic": "MedicalClinic",
    "collectionpage": "CollectionPage",
    "collection page": "CollectionPage",
    "breadcrumblist": "BreadcrumbList",
    "logo": "Logo",  # handled specially in graph assembly
    "jobposting": "JobPosting",
    "medicalservice": "MedicalService",
    "medicalspecialty": "MedicalSpecialty",
    "hospital": "Hospital",
}

def coerce_schema_type(label: str) -> str:
    key = _lc(label)
    return SCHEMA_CANON.get(key, label)

async def get_map(session) -> Dict[str, dict]:
    s = await get_settings(session)
    return s.page_type_map or {}

def _ci_lookup(mapping: Dict[str, dict], label: str | None) -> Optional[Tuple[str, dict]]:
    if not mapping or not label:
        return None
    tgt = _lc(label)
    for k, v in mapping.items():
        if _lc(k) == tgt:
            return (k, v)
    return None

async def upsert_type(session, label: str, primary: str, secondary: List[str]) -> Dict[str, dict]:
    label = _norm(label)
    primary = coerce_schema_type(primary)
    secondary = [coerce_schema_type(s) for s in secondary or []]
    s = await get_settings(session)
    m = dict(s.page_type_map or {})
    # replace by case-insensitive match
    found = _ci_lookup(m, label)
    key = found[0] if found else label
    m[key] = {"primary": primary, "secondary": secondary}
    await update_settings(session, page_type_map=m)
    return m

async def delete_type(session, label: str) -> bool:
    s = await get_settings(session)
    m = dict(s.page_type_map or {})
    tgt = _lc(label)
    key = None
    for k in list(m.keys()):
        if _lc(k) == tgt:
            key = k
            break
    if key is None:
        return False
    m.pop(key, None)
    await update_settings(session, page_type_map=m)
    return True

async def resolve_for_label(session, label: str | None) -> Tuple[str | None, List[str]]:
    """Return (primary, secondary) for a given page_type label using CI mapping."""
    m = await get_map(session)
    found = _ci_lookup(m, label or "")
    if not found:
        return None, []
    cfg = found[1] or {}
    p = cfg.get("primary")
    s = cfg.get("secondary") or []
    return p, s