
from __future__ import annotations
from typing import List, Dict, Any
from bs4 import BeautifulSoup
import json

def extract_onpage_jsonld(html: str) -> List[Dict[str, Any]]:
    """
    Return a list of JSON-LD dicts found in <script type="application/ld+json"> tags.
    Handles arrays and single objects; ignores parse failures.
    """
    soup = BeautifulSoup(html, "lxml")
    out: List[Dict[str, Any]] = []
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            payload = json.loads(tag.string or tag.text or "")
        except Exception:
            continue
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict):
                    out.append(item)
        elif isinstance(payload, dict):
            out.append(payload)
    return out
