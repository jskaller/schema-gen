
from typing import Any, Dict, List, Optional

def _ensure_graph(data: Any) -> List[Dict]:
    graph: List[Dict] = []
    if isinstance(data, dict):
        if "@graph" in data and isinstance(data["@graph"], list):
            for n in data["@graph"]:
                if isinstance(n, dict):
                    graph.append(n)
        else:
            graph.append(data)
    elif isinstance(data, list):
        graph = [n for n in data if isinstance(n, dict)]
    return graph

def _flatten_embedded_graphs(graph: List[Dict]) -> List[Dict]:
    out: List[Dict] = []
    for node in graph:
        if not isinstance(node, dict):
            continue
        n = dict(node)
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
    val = n.get("audience")
    if isinstance(val, str):
        n["audience"] = {"@type": "Audience", "audienceType": val}
    elif isinstance(val, list) and val and isinstance(val[0], str):
        n["audience"] = {"@type": "Audience", "audienceType": val[0]}

def sanitize_jsonld(data: Any, primary_type: str, url: Optional[str], secondary_types: Optional[List[str]] = None) -> Dict:
    graph = _ensure_graph(data)
    graph = _flatten_embedded_graphs(graph)

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
        if cleaned:
            if "@type" not in cleaned[0] or cleaned[0].get("@type") in ("Thing", "WebPage", "MedicalWebPage"):
                cleaned[0]["@type"] = primary_type
                root_idx = 0
        if root_idx is None:
            root = {"@context": "https://schema.org", "@type": primary_type}
            if url:
                root["url"] = url
            cleaned.insert(0, root)
            root_idx = 0

    sec = set(secondary_types or [])
    if "MedicalOrganization" in sec:
        found = next((n for n in cleaned if n.get("@type") == "MedicalOrganization"), None)
        if not found:
            cleaned.append({"@type": "MedicalOrganization", "url": url or ""})
        else:
            if "url" not in found and url:
                found["url"] = url

    return {"@context": "https://schema.org", "@graph": cleaned}
