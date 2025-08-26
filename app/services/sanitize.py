
from typing import Any, Dict, List, Optional

def _ensure_graph(data: Any) -> List[Dict]:
    """Return a flat list of nodes. Accepts dict with/without @graph or a list."""
    graph: List[Dict] = []
    if isinstance(data, dict):
        if "@graph" in data and isinstance(data["@graph"], list):
            for n in data["@graph"]:
                if isinstance(n, dict):
                    graph.append(n)
        elif isinstance(data, dict):
            graph.append(data)
    elif isinstance(data, list):
        graph = [n for n in data if isinstance(n, dict)]
    return graph

def _flatten_embedded_graphs(graph: List[Dict]) -> List[Dict]:
    """If a node contains an embedded @graph, lift its items to top-level and drop the nested @graph key."""
    out: List[Dict] = []
    for node in graph:
        if not isinstance(node, dict):
            continue
        n = dict(node)  # shallow copy
        if "@graph" in n and isinstance(n["@graph"], list):
            for sub in n["@graph"]:
                if isinstance(sub, dict):
                    out.append(sub)
            n.pop("@graph", None)
        out.append(n)
    return out

def _drop_nulls_and_empty(n: Dict) -> Dict:
    clean = {}
    for k, v in n.items():
        if v is None:
            continue
        if isinstance(v, (list, dict)) and not v:
            continue
        clean[k] = v
    return clean

def _coerce_audience(n: Dict) -> None:
    # Accept "Patient" or ["Patient"] and coerce to {'@type':'Audience','audienceType':'Patient'}
    val = n.get("audience")
    if isinstance(val, str):
        n["audience"] = {"@type": "Audience", "audienceType": val}
    elif isinstance(val, list) and val and isinstance(val[0], str):
        n["audience"] = {"@type": "Audience", "audienceType": val[0]}

def sanitize_jsonld(data: Any, primary_type: str, url: Optional[str], secondary_types: Optional[List[str]] = None) -> Dict:
    """Return a normalized JSON-LD dict with @context and a flat @graph.
    - Flattens nested @graph occurrences
    - Ensures root node of @type == primary_type exists
    - Cleans null/empty values
    - Coerces audience to proper object
    - If MedicalOrganization appears (or required by secondary types), ensure it has at least url/name if available
    """
    graph = _ensure_graph(data)
    graph = _flatten_embedded_graphs(graph)

    # Clean each node a bit
    cleaned: List[Dict] = []
    for n in graph:
        n = _drop_nulls_and_empty(n)
        _coerce_audience(n)
        cleaned.append(n)

    # Ensure we have a root of desired type
    root_idx = None
    for i, n in enumerate(cleaned):
        if n.get("@type") == primary_type:
            root_idx = i
            break

    if root_idx is None:
        # Promote first node to desired type if it looks generic
        if cleaned:
            if "@type" not in cleaned[0] or cleaned[0].get("@type") in ("Thing", "WebPage", "MedicalWebPage"):
                cleaned[0]["@type"] = primary_type
                root_idx = 0
        if root_idx is None:
            # Create a fresh root
            root = {"@context": "https://schema.org", "@type": primary_type}
            if url:
                root["url"] = url
            cleaned.insert(0, root)
            root_idx = 0

    # Ensure MedicalOrganization skeleton if secondary requires it
    sec = set(secondary_types or [])
    if "MedicalOrganization" in sec:
        found = next((n for n in cleaned if n.get("@type") == "MedicalOrganization"), None)
        if not found:
            cleaned.append({"@type": "MedicalOrganization", "url": url or ""})
        else:
            if "url" not in found and url:
                found["url"] = url

    # Return wrapped
    return {"@context": "https://schema.org", "@graph": cleaned}
