
from __future__ import annotations
from typing import Any, Dict, List, Optional

def _as_object(v):
    if isinstance(v, list):
        return v[0] if v else None
    return v

def normalize_jsonld(data: Dict[str, Any], *, primary_type: str, fallback_phone: Optional[str]=None, fallback_address: Optional[str]=None) -> Dict[str, Any]:
    if not isinstance(data, dict):
        return {"@context":"https://schema.org","@type":primary_type}

    # Ensure @context
    if "@context" not in data:
        data["@context"] = "https://schema.org"

    # If it's a @graph, try to make the first node also consistent but keep root for export
    # For now, enforce root node's @type to primary_type
    t = data.get("@type")
    if isinstance(t, list):
        t = t[0] if t else None
    if not t or (isinstance(t, str) and t.lower() != primary_type.lower()):
        data["@type"] = primary_type

    # Normalize audience -> object { @type: "Audience", audienceType: "..." }
    aud = data.get("audience")
    if aud:
        aud_obj = _as_object(aud)
        if isinstance(aud_obj, dict):
            # ensure @type Audience
            if "@type" not in aud_obj:
                aud_obj["@type"] = "Audience"
            # prefer audienceType over name
            if "audienceType" not in aud_obj and "name" in aud_obj:
                aud_obj["audienceType"] = aud_obj.pop("name")
            data["audience"] = aud_obj
        elif isinstance(aud_obj, str):
            data["audience"] = {"@type":"Audience","audienceType": aud_obj}
        else:
            # drop invalid shapes
            data.pop("audience", None)

    # Telephone
    if "telephone" in data and isinstance(data["telephone"], list):
        data["telephone"] = data["telephone"][0]
    if "telephone" not in data and fallback_phone:
        data["telephone"] = fallback_phone

    # Address normalize
    addr = data.get("address")
    if isinstance(addr, str):
        data["address"] = {"@type":"PostalAddress","streetAddress": addr}
    elif isinstance(addr, dict):
        if "@type" not in addr:
            addr["@type"] = "PostalAddress"
        data["address"] = addr
    elif not addr and fallback_address:
        data["address"] = {"@type":"PostalAddress","streetAddress": fallback_address}

    # sameAs -> array
    same = data.get("sameAs")
    if isinstance(same, str):
        data["sameAs"] = [same]
    elif isinstance(same, list):
        # ensure strings only
        data["sameAs"] = [s for s in same if isinstance(s, str)]

    return data
