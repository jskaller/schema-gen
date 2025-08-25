
from __future__ import annotations
from typing import List, Dict, Any, Tuple, Optional
import csv
import io

EXPECTED = [
    "url", "topic", "subject", "audience", "address", "phone",
    "compare_existing", "competitor1", "competitor2"
]

SYNONYMS = {
    "url": ["url", "page", "page_url", "link", "target"],
    "topic": ["topic", "keyword", "keywords", "medicalSpecialty"],
    "subject": ["subject", "name", "title", "entity"],
    "audience": ["audience", "audienceType", "intended_audience"],
    "address": ["address", "street", "streetAddress"],
    "phone": ["phone", "telephone", "tel"],
    "compare_existing": ["compare_existing", "compare", "onpage", "existing"],
    "competitor1": ["competitor1", "competitor", "competitor_1", "competitor_a"],
    "competitor2": ["competitor2", "competitor_2", "competitor_b"],
}

def _normalize_header(h: str) -> str:
    return (h or "").strip().lower().replace(" ", "_")

def _guess_key(header: str) -> Optional[str]:
    h = _normalize_header(header)
    for k, names in SYNONYMS.items():
        if h in [ _normalize_header(n) for n in names ]:
            return k
    return None

def map_headers(headers: List[str]) -> Dict[int, str]:
    mapping: Dict[int, str] = {}
    used = set()
    for idx, h in enumerate(headers):
        key = _guess_key(h)
        if key and key not in used:
            mapping[idx] = key
            used.add(key)
    return mapping

def parse_csv(content: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Parse CSV text and return list of rows with normalized keys.
    Returns (rows, warnings)
    """
    warnings: List[str] = []
    reader = csv.reader(io.StringIO(content))
    rows = list(reader)
    if not rows:
        return [], ["CSV appears empty."]
    headers = rows[0]
    mapping = map_headers(headers)
    if "url" not in mapping.values():
        warnings.append("No 'url' column detected — make sure your header includes something like 'url' or 'page_url'.")
    out: List[Dict[str, Any]] = []
    for r in rows[1:]:
        item: Dict[str, Any] = {k: "" for k in EXPECTED}
        for i, cell in enumerate(r):
            key = mapping.get(i)
            if key:
                item[key] = cell.strip()
        if any(v for v in item.values()):  # non-empty row
            out.append(item)
    return out, warnings
