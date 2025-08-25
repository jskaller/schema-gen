
from __future__ import annotations
from typing import Dict, Any, List

PRIMARY_SUGGESTIONS = {
    "MedicalOrganization": [
        ("description", "Provide a concise summary (30–400 chars)."),
        ("telephone", "Add a customer-facing phone number."),
        ("address", "Add a postal address."),
        ("medicalSpecialty", "Include a clear specialty keyword (e.g., Cardiology)."),
        ("sameAs", "Link official profiles (Google Business, Wikipedia, LinkedIn)."),
        ("audience", "Specify intended audience (e.g., patient)."),
        ("dateModified", "Ensure recent dateModified (ISO8601)."),
        ("geo", "Add latitude/longitude for better map precision (optional)."),
        ("image", "Include a representative image URL (logo or photo)."),
        ("areaServed", "List cities/regions served (if applicable)."),
    ],
    "Hospital": [
        ("url", "Add the hospital page URL."),
        ("telephone", "Add a main line number."),
        ("address", "Provide the street address."),
        ("geo", "Add precise latitude/longitude (optional but useful)."),
        ("sameAs", "Link official map/listing profiles."),
    ],
    "MedicalWebPage": [
        ("name", "Provide a human-friendly page title."),
        ("about", "Summarize what the page is about."),
        ("primaryImageOfPage", "Include the main image of the page."),
        ("breadcrumb", "Ensure a BreadcrumbList is present."),
    ],
}

def advise(root_node: Dict[str, Any], required: List[str], recommended: List[str]) -> List[str]:
    tips: List[str] = []
    # Generic required/recommended guidance
    for k in required:
        if k not in root_node or root_node.get(k) in (None, "", []):
            tips.append(f"Missing required field: {k}")
    for k in recommended:
        if k not in root_node or root_node.get(k) in (None, "", []):
            tips.append(f"Consider adding: {k}")

    # Primary-type specific suggestions
    t = root_node.get("@type")
    for field, msg in PRIMARY_SUGGESTIONS.get(t, []):
        if root_node.get(field) in (None, "", []):
            tips.append(msg)

    # Tighten name/description heuristics
    name = root_node.get("name")
    if isinstance(name, str) and len(name) > 120:
        tips.append("Tighten name (≤120 chars).")
    desc = root_node.get("description")
    if not isinstance(desc, str) or not (30 <= len(desc) <= 400):
        tips.append("Provide a 30–400 char description summarizing the page focus.")
    return tips
