# app/services/sanitize.py
"""
Sanitization utilities: enforce single @context/@graph and normalize node @type
to valid Schema.org classes using the page-type registry (future-proof).

BACKWARD COMPAT:
- Provide sanitize_jsonld(...) alias expected by app.main
- Provide sanitize(...) alias as well if other modules used it
"""
from __future__ import annotations
from typing import Any, Dict, List, Union

try:
    from app.services.page_types import coerce_schema_type
except Exception:
    def coerce_schema_type(x: str) -> str:
        return "WebPage"

Json = Dict[str, Any]

def _normalize_type(t: Union[str, List[str]]) -> Union[str, List[str]]:
    if isinstance(t, str):
        return coerce_schema_type(t)
    if isinstance(t, list):
        return [coerce_schema_type(x) for x in t]
    return t

def sanitize_graph(graph_obj: Json) -> Json:
    """Normalize @type values for every node in @graph; ensure single top-level @context."""
    if not isinstance(graph_obj, dict):
        return graph_obj

    if "@context" not in graph_obj:
        graph_obj["@context"] = "https://schema.org"

    g = graph_obj.get("@graph")
    if isinstance(g, list):
        for node in g:
            if isinstance(node, dict):
                if "@type" in node:
                    node["@type"] = _normalize_type(node.get("@type"))
                if "@context" in node:
                    node.pop("@context", None)

    return graph_obj

# ---- Backward-compatible aliases ----

def sanitize_jsonld(graph_obj: Json) -> Json:
    """Legacy entrypoint used by app.main; delegates to sanitize_graph."""
    return sanitize_graph(graph_obj)

def sanitize(graph_obj: Json) -> Json:
    """Legacy alias for any modules calling sanitize(...)."""
    return sanitize_graph(graph_obj)
