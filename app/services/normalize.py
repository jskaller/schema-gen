
from __future__ import annotations
from typing import Any, Dict
from datetime import datetime, timezone

def _first_str(x):
    if isinstance(x, list) and x:
        return str(x[0])
    if isinstance(x, (str, int, float)):
        return str(x)
    return None

def normalize_jsonld(obj: Dict[str, Any], primary_type: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
    # Base copy
    obj = dict(obj or {})

    # Context & primary type
    obj["@context"] = "https://schema.org"
    obj["@type"] = primary_type

    # dateModified -> always a string
    dm = obj.get("dateModified")
    if not isinstance(dm, str) or not dm.strip():
        obj["dateModified"] = datetime.now(timezone.utc).isoformat()

    # Ensure url field is present (root node should carry canonical URL)
    if not obj.get("url") and inputs.get("url"):
        obj["url"] = inputs["url"]

    # Audience normalization -> object
    aud = obj.get("audience")
    if isinstance(aud, list):
        cand = None
        for it in aud:
            if isinstance(it, dict):
                cand = it.get("audienceType") or it.get("name")
                if cand: break
            elif isinstance(it, str) and it.strip():
                cand = it.strip(); break
        if cand:
            obj["audience"] = {"@type": "Audience", "audienceType": cand}
        else:
            obj.pop("audience", None)
    elif isinstance(aud, str):
        obj["audience"] = {"@type": "Audience", "audienceType": aud}
    elif isinstance(aud, dict):
        if "audienceType" not in aud and "name" in aud:
            aud["audienceType"] = aud.pop("name")
        aud.setdefault("@type", "Audience")
        obj["audience"] = aud

    # Telephone
    tel = _first_str(obj.get("telephone"))
    if tel:
        obj["telephone"] = tel
    elif inputs.get("phone"):
        obj["telephone"] = inputs["phone"]

    # Address
    addr = obj.get("address")
    if isinstance(addr, str) and addr.strip():
        obj["address"] = {"@type":"PostalAddress","streetAddress":addr.strip()}
    elif isinstance(addr, dict):
        addr = dict(addr)
        addr.setdefault("@type", "PostalAddress")
        obj["address"] = addr
    elif inputs.get("address"):
        obj["address"] = {"@type":"PostalAddress","streetAddress": inputs["address"]}

    # Inject geo if provided (lat/long) -> expects dict like {"latitude":..,"longitude":..}
    if inputs.get("geo") and isinstance(inputs["geo"], dict) and inputs["geo"].get("latitude") and inputs["geo"].get("longitude"):
        obj["geo"] = {"@type": "GeoCoordinates", "latitude": inputs["geo"]["latitude"], "longitude": inputs["geo"]["longitude"]}

    # sameAs -> array
    sameas = obj.get("sameAs")
    if isinstance(sameas, str):
        obj["sameAs"] = [sameas]
    elif isinstance(sameas, list):
        obj["sameAs"] = [str(s) for s in sameas if isinstance(s, (str, int, float)) and str(s).strip()]

    # name fallback
    if not obj.get("name") and inputs.get("subject"):
        obj["name"] = inputs["subject"]

    # medicalSpecialty from topic if missing
    if primary_type in ("Hospital","MedicalClinic","Physician","MedicalOrganization"):
        if not obj.get("medicalSpecialty") and inputs.get("topic"):
            obj["medicalSpecialty"] = inputs["topic"]

    return obj

    # ----- enforce primary type -----
    # No matter what the model returned, the root node in our pipeline represents the configured
    # primary type. Avoid leaking custom labels like "Medical Specialty Page".
    obj["@type"] = primary_type

