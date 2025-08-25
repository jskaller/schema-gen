
from __future__ import annotations
from typing import Dict, Any, List, Tuple

def summarize_scores(name: str, data: Dict[str, Any], score_fn, required: List[str], recommended: List[str]) -> Dict[str, Any]:
    score, details = score_fn(data, required, recommended)
    return {"name": name, "score": score, "subscores": details["subscores"], "recommendations": details["recommendations"]}

def pick_primary_by_type(items: List[Dict[str, Any]], preferred_type: str) -> Dict[str, Any] | None:
    for d in items:
        if isinstance(d, dict) and d.get("@type") == preferred_type:
            return d
    # fall back to the first dict if no exact type match
    return items[0] if items else None
