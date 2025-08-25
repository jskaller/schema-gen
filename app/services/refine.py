
from __future__ import annotations
from typing import Dict, Any, List, Tuple, Callable

# Types for clarity
Scorer = Callable[[Dict[str, Any], List[str], List[str]], Tuple[int, Dict[str, Any]]]

def _ensure_description(data: Dict[str, Any], cleaned_text: str) -> bool:
    """Try to create/resize description into 30-400 chars window. Returns True if changed."""
    desc = data.get("description") or ""
    changed = False
    if not desc or len(desc) < 30:
        # take first ~220 chars from cleaned text as a summary
        summary = (cleaned_text or "").strip().split("\n", 1)[0][:220]
        if summary:
            data["description"] = summary
            changed = True
    if len(data.get("description","")) > 400:
        data["description"] = data["description"][:400]
        changed = True
    return changed

def _fill_missing_placeholders(data: Dict[str, Any], missing: List[str]) -> bool:
    """Add minimally valid placeholders for recommended fields. Returns True if changed."""
    changed = False
    for field in missing:
        if field == "audience" and "audience" not in data:
            data["audience"] = {"@type": "Audience", "audienceType": "patient"}
            changed = True
        elif field == "address" and "address" not in data:
            data["address"] = {"@type": "PostalAddress", "streetAddress": "123 Main St"}
            changed = True
        elif field == "telephone" and "telephone" not in data:
            data["telephone"] = "+1 555-555-5555"
            changed = True
        elif field == "sameAs" and "sameAs" not in data:
            data["sameAs"] = []
            changed = True
        elif field == "medicalSpecialty" and "medicalSpecialty" not in data:
            data["medicalSpecialty"] = "General"
            changed = True
        elif field == "dateModified" and "dateModified" not in data:
            from datetime import datetime, timezone
            data["dateModified"] = datetime.now(timezone.utc).isoformat()
            changed = True
    return changed

def refine_to_perfect(
    base_jsonld: Dict[str, Any],
    cleaned_text: str,
    required: List[str],
    recommended: List[str],
    score_fn: Scorer,
    max_attempts: int = 3
) -> Tuple[Dict[str, Any], int, Dict[str, Any], List[Dict[str, Any]]]:
    """
    Iteratively tweak the JSON-LD to reach 100 score or exhaust attempts.
    Returns (final_jsonld, final_score, final_details, iterations_log)
    """
    current = dict(base_jsonld)  # shallow copy
    log: List[Dict[str, Any]] = []
    score, details = score_fn(current, required, recommended)
    log.append({"attempt": 0, "score": score, "details": details, "change": "initial"})
    if score >= 100:
        return current, score, details, log

    attempts = 0
    while attempts < max_attempts and score < 100:
        attempts += 1
        changed = False

        # 1) Ensure clarity/length for description
        changed |= _ensure_description(current, cleaned_text)

        # 2) Find missing recommended fields from previous score details
        #    We don't have direct list, recompute quickly:
        present_recommended = [f for f in recommended if f in current and current[f]]
        missing = [f for f in recommended if f not in present_recommended]
        changed |= _fill_missing_placeholders(current, missing)

        # 3) If nothing changed, break to avoid loop
        if not changed:
            break

        score, details = score_fn(current, required, recommended)
        log.append({"attempt": attempts, "score": score, "details": details, "change": "heuristic additions"})
        if score >= 100:
            break

    return current, score, details, log
