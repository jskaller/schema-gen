
from __future__ import annotations
from typing import List

def to_friendly_messages(errors: List[str], primary_type: str) -> List[str]:
    friendly: List[str] = []
    for e in errors or []:
        low = e.lower()
        if "@type" in e and "expected" in low and primary_type.lower() in low:
            friendly.append(f"The root '@type' must be '{primary_type}'. The app will set this automatically based on your Page Type selection.")
            continue
        if "audience" in low and "not of type 'object'" in low:
            friendly.append("Field 'audience' must be an object like {'@type':'Audience','audienceType':'patient'}. We'll try to fix shapes coming from models.")
            continue
        if "required property" in low and "'name'" in low:
            friendly.append("Missing 'name'. Provide a clear subject/title for this page, or add it to the page content.")
            continue
        if "address" in low and "object" in low:
            friendly.append("Address should be an object of type PostalAddress. Example: {'@type':'PostalAddress','streetAddress':'...'}")
            continue
        if "sameas" in low and "array" in low:
            friendly.append("sameAs should be an array of URLs, e.g., ['https://example.com/profile'].")
            continue
        # generic fallback
        friendly.append(e)
    return friendly[:12]
