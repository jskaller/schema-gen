# app/services/sanitize.py
from __future__ import annotations
from typing import Any, Dict, List, Union

Json = Union[Dict[str, Any], List[Any], None]

def _as_list(x):
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return [x]

def _has_required_jobposting_fields(node: Dict[str, Any]) -> List[str]:
    required = ["title", "datePosted", "description", "hiringOrganization"]
    missing = [k for k in required if k not in node or (isinstance(node.get(k), str) and not node.get(k).strip())]
    return missing

def _flatten_to_graph(obj: Json) -> Dict[str, Any]:
    if obj is None:
        return {"@context": "https://schema.org", "@graph": []}
    if isinstance(obj, dict):
        ctx = obj.get("@context", "https://schema.org")
        g = obj.get("@graph")
        if isinstance(g, list):
            nodes = g
        else:
            # If a single node dict, treat as 1-node graph
            nodes = [obj] if "@type" in obj else []
        return {"@context": ctx, "@graph": nodes}
    if isinstance(obj, list):
        # List of nodes -> graph
        return {"@context": "https://schema.org", "@graph": [n for n in obj if isinstance(n, dict)]}
    return {"@context": "https://schema.org", "@graph": []}

def sanitize_graph(graph_obj: Json, *args, **kwargs) -> Dict[str, Any]:
    g = _flatten_to_graph(graph_obj)
    ctx = g.get("@context") or "https://schema.org"
    nodes = [n for n in _as_list(g.get("@graph")) if isinstance(n, dict)]

    # Drop nested @context on nodes; normalize @type to strings
    clean: List[Dict[str, Any]] = []
    for n in nodes:
        n = dict(n)
        n.pop("@context", None)
        t = n.get("@type")
        if isinstance(t, list):
            n["@type"] = [str(x) for x in t if x]
        elif isinstance(t, str):
            n["@type"] = t.strip()
        else:
            n.pop("@type", None)
        clean.append(n)

    # Remove JobPosting nodes missing requireds
    kept: List[Dict[str, Any]] = []
    for n in clean:
        t = n.get("@type")
        types = [t] if isinstance(t, str) else (t or [])
        if "JobPosting" in types:
            missing = _has_required_jobposting_fields(n)
            if missing:
                # skip it
                continue
        kept.append(n)

    return {"@context": ctx, "@graph": kept}

# Backward compatible aliases
def sanitize_jsonld(graph_obj: Json, *args, **kwargs) -> Dict[str, Any]:
    return sanitize_graph(graph_obj, *args, **kwargs)

def sanitize(graph_obj: Json, *args, **kwargs) -> Dict[str, Any]:
    return sanitize_graph(graph_obj, *args, **kwargs)