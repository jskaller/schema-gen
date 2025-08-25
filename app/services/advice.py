
from __future__ import annotations
from typing import List, Dict, Any

HINTS = {
    "telephone": "Add a phone number on the page or provide it in the form.",
    "address": "Add a postal address on the page or provide it in the form.",
    "sameAs": "Link to official profiles (e.g., GMB, Wikipedia, LinkedIn) via sameAs.",
    "description": "Provide a concise, human-readable summary of the page.",
    "medicalSpecialty": "Include a clear specialty keyword (e.g., cardiology).",
    "breadcrumb": "Add a BreadcrumbList in the page markup to help navigation.",
}

def _flatten_keys(d: Any, prefix="") -> set:
    keys = set()
    if isinstance(d, dict):
        for k, v in d.items():
            full = f"{prefix}.{k}" if prefix else k
            keys.add(full)
            keys |= _flatten_keys(v, full)
    elif isinstance(d, list):
        for i, v in enumerate(d):
            keys |= _flatten_keys(v, prefix)
    return keys

def advise(jsonld: Dict[str, Any], required: List[str], recommended: List[str]) -> List[str]:
    present = _flatten_keys(jsonld)
    messages: List[str] = []
    for k in required:
        if k not in present:
            msg = HINTS.get(k, f"Missing required field: {k}")
            messages.append(msg)
    for k in recommended:
        if k not in present:
            msg = HINTS.get(k, f"Consider adding: {k}")
            messages.append(msg)
    return messages[:12]
