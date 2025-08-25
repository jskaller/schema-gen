
from __future__ import annotations
import asyncio
import hashlib
import json
from typing import Optional, Dict, Any
import httpx

_CACHE: Dict[str, Dict[str, Any]] = {}

async def geocode_postal_address(addr: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Best-effort geocoding using OpenStreetMap Nominatim (no key required).
    Returns {'latitude': ..., 'longitude': ...} on success, else None.
    Polite: includes a UA and small timeout, caches by normalized string.
    """
    if not isinstance(addr, dict):
        return None
    parts = [
        addr.get("streetAddress"),
        addr.get("addressLocality") or addr.get("city"),
        addr.get("addressRegion") or addr.get("region"),
        addr.get("postalCode"),
        addr.get("addressCountry") or addr.get("country") or "US",
    ]
    q = ", ".join([p for p in parts if p])
    if not q.strip():
        return None

    key = hashlib.sha256(q.strip().lower().encode("utf-8")).hexdigest()
    if key in _CACHE:
        return _CACHE[key]

    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": q, "format": "json", "limit": 1, "addressdetails": 0}
    headers = {"User-Agent": "schema-gen/1.0 (https://example.org)"}

    try:
        async with httpx.AsyncClient(headers=headers, timeout=10) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            data = r.json()
            if isinstance(data, list) and data:
                first = data[0]
                lat, lon = first.get("lat"), first.get("lon")
                if lat and lon:
                    result = {"latitude": float(lat), "longitude": float(lon)}
                    _CACHE[key] = result
                    return result
    except Exception:
        return None
    return None
