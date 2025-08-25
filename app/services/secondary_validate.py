
from __future__ import annotations
from typing import Any, List, Dict

def _find_graph_nodes(jsonld: Any) -> List[Dict]:
    if isinstance(jsonld, dict):
        if "@graph" in jsonld and isinstance(jsonld["@graph"], list):
            return [n for n in jsonld["@graph"] if isinstance(n, dict)]
        else:
            return [jsonld]
    return []

def validate_secondary(jsonld: Any, secondary_types: list[str]) -> List[str]:
    """Return a list of issues for expected secondary types (light checks)."""
    issues: List[str] = []
    nodes = _find_graph_nodes(jsonld)
    types_present = [n.get("@type") for n in nodes if isinstance(n, dict)]
    for t in secondary_types or []:
        if t not in types_present:
            issues.append(f"Secondary node @{t} missing from @graph.")
        else:
            # Type-specific light checks
            if t == "BreadcrumbList":
                # look for itemListElement array
                for n in nodes:
                    if n.get("@type") == "BreadcrumbList":
                        ile = n.get("itemListElement")
                        if not isinstance(ile, list) or len(ile) == 0:
                            issues.append("BreadcrumbList: itemListElement should be a non-empty array of ListItem.")
                        break
    return issues
