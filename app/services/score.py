from __future__ import annotations
from typing import Dict, Any, Tuple, List

# Categories:
# 1) AI Consumption & Data Richness
#    a) Entity Connectivity
#    b) Data Richness & Specificity
#    c) Data Clarity
# 2) Schema Validity & Correctness
#    a) Schema Validity
#    b) Required Fields
#    c) Recommended Fields

def _pct(value: int, maxv: int) -> int:
    return max(0, min(100, round(100 * value / maxv))) if maxv > 0 else 0

def score_jsonld(data: Dict[str, Any], required_fields: List[str], recommended_fields: List[str]) -> Tuple[int, Dict[str, Any]]:
    # Validity/properties
    present_required = [f for f in required_fields if f in data and data[f]]
    present_recommended = [f for f in recommended_fields if f in data and data[f]]

    required_score = _pct(len(present_required), len(required_fields))
    recommended_score = _pct(len(present_recommended), len(recommended_fields))

    # Basic "validity" heuristic: has @context/@type and JSON-serializable
    validity_score = 100 if (data.get("@context") and data.get("@type")) else 50

    # Entity connectivity: linked sub-objects (address, audience, etc.)
    connectivity_points = 0
    for key in ["address", "audience"]:
        if isinstance(data.get(key), dict) and data[key].get("@type"):
            connectivity_points += 1
    connectivity_score = _pct(connectivity_points, 2)

    # Richness/specificity: number of non-empty top-level keys beyond min set
    keys = set(data.keys())
    base_keys = {"@context", "@type", "name", "url"}
    richness_score = _pct(len([k for k in keys - base_keys if data.get(k)]), 6)  # heuristic

    # Clarity: simple length checks on name/description
    clarity_points = 0
    if isinstance(data.get("name"), str) and 3 <= len(data["name"]) <= 120:
        clarity_points += 1
    if isinstance(data.get("description"), str) and 30 <= len(data["description"]) <= 400:
        clarity_points += 1
    clarity_score = _pct(clarity_points, 2)

    # Aggregate with equal weight across 6 subs
    subs = {
        "AI Consumption & Data Richness": {
            "Entity Connectivity": connectivity_score,
            "Data Richness & Specificity": richness_score,
            "Data Clarity": clarity_score,
        },
        "Schema Validity & Correctness": {
            "Schema Validity": validity_score,
            "Required Fields": required_score,
            "Recommended Fields": recommended_score,
        },
    }

    overall = round(sum(
        subs["AI Consumption & Data Richness"].values()
    )/3*0.5 + sum(
        subs["Schema Validity & Correctness"].values()
    )/3*0.5)

    # Recommendations
    recs: List[str] = []
    missing_required = [f for f in required_fields if f not in present_required]
    missing_recommended = [f for f in recommended_fields if f not in present_recommended]
    if missing_required:
        recs.append(f"Add required fields: {', '.join(missing_required)}.")
    if missing_recommended:
        recs.append(f"Consider adding recommended fields: {', '.join(missing_recommended)}.")
    if connectivity_score < 100:
        recs.append("Link related entities with @type objects (e.g., address as PostalAddress, audience as Audience).")
    if richness_score < 100:
        recs.append("Include additional specific properties (telephone, openingHours, sameAs, medicalSpecialty, etc.).")
    if clarity_score < 100:
        recs.append("Tighten name (<=120 chars) and provide a 30–400 char description summarizing the page focus.")

    return overall, {"subscores": subs, "recommendations": recs}
