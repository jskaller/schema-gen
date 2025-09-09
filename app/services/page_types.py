# app/services/page_types.py
"""
Page-type mapping utilities (case-insensitive) with legacy/awaitable admin API.

Functions expected by app.main (awaited and sometimes passed a DB session):
    - get_map(session?) -> dict
    - upsert_type(session?, label, schema_type) -> None
    - delete_type(session?, label) -> bool

Also provides:
    - resolve_schema_type(page_type_raw) -> Optional[str]

Implementation notes
- Keys are stored lowercased for case-insensitive lookups and updates.
- Values should be valid Schema.org types (e.g., 'MedicalService', 'CollectionPage').
- Functions are defined as async and accept optional leading `session` to match older call sites.
"""

from __future__ import annotations
from typing import Dict, Optional

# Default bootstrap map — keys must be lowercase
_PAGE_TYPE_MAP: Dict[str, str] = {
    # Adjust via admin UI as needed
    "meac homepage": "MedicalOrganization",
    "meac medical specialty page": "MedicalService",
    "meac careers page": "CollectionPage",
}

def _norm(key: str) -> str:
    return (key or "").strip().lower()

def resolve_schema_type(page_type_raw: str) -> Optional[str]:
    """Case-insensitive lookup for a CSV/admin-provided page_type label."""
    if not page_type_raw:
        return None
    return _PAGE_TYPE_MAP.get(_norm(page_type_raw))

# --- Awaitable, arg-flexible admin API ---

async def get_map(*args, **kwargs) -> Dict[str, str]:
    """Return a copy of the page-type map. Accepts optional (ignored) session."""
    return dict(_PAGE_TYPE_MAP)

async def upsert_type(*args, **kwargs) -> None:
    """Insert/update mapping. Supports signatures:
        upsert_type(label, schema_type)
        upsert_type(session, label, schema_type)
    """
    label = schema_type = None
    if len(args) == 2:
        label, schema_type = args
    elif len(args) >= 3:
        # First arg is likely a DB session; ignore it for in-memory map
        _, label, schema_type = args[:3]
    else:
        # Named args support
        label = kwargs.get("label")
        schema_type = kwargs.get("schema_type")
    if not label or not schema_type:
        return
    _PAGE_TYPE_MAP[_norm(label)] = str(schema_type).strip()

async def delete_type(*args, **kwargs) -> bool:
    """Delete a mapping. Supports signatures:
        delete_type(label)
        delete_type(session, label)
    Returns True if removed.
    """
    label = None
    if len(args) == 1:
        (label,) = args
    elif len(args) >= 2:
        # First arg is likely a DB session; ignore it
        _, label = args[:2]
    else:
        label = kwargs.get("label")
    if not label:
        return False
    return _PAGE_TYPE_MAP.pop(_norm(label), None) is not None
