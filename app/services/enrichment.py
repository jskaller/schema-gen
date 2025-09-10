# app/services/enrichment.py
from __future__ import annotations
from typing import Dict, Any, Optional, List, Tuple
from urllib.parse import urlparse
from datetime import datetime
import email.utils as eut

Json = Dict[str, Any]

def _first_nonempty(*vals: Optional[str]) -> Optional[str]:
    for v in vals:
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None

def _parse_rfc2822(dt: str) -> Optional[str]:
    try:
        # Normalize to ISO 8601 date (yyyy-mm-dd) for schema.org dateModified
        d = eut.parsedate_to_datetime(dt)
        return d.date().isoformat()
    except Exception:
        return None

def _set_if_absent(node: Json, key: str, value: Any) -> None:
    if value is None:
        return
    if key not in node or (isinstance(node[key], str) and not node[key].strip()):
        node[key] = value

def _find_first(nodes: List[Json], typ: str) -> Optional[Json]:
    for n in nodes:
        t = n.get("@type")
        if (isinstance(t, str) and t == typ) or (isinstance(t, list) and typ in t):
            return n
    return None

def enrich_phase1(graph: Json, url: str, *, html_lang: Optional[str] = None, canonical_link: Optional[str] = None, last_modified_header: Optional[str] = None, flags: Dict[str, bool] | None = None) -> Tuple[Json, Dict[str, Any]]:
    """Return (maybe_modified_graph, diff) using Phase-1 rules.
    We do not scrape; we only use provided hints + URL + existing graph.
    If flags['shadow'] is True, we compute a diff but do NOT apply changes.
    """
    flags = flags or {"shadow": True, "inLanguage": True, "canonical": True, "dateModified": True}
    shadow = bool(flags.get("shadow", True))
    want_lang = bool(flags.get("inLanguage", True))
    want_canon = bool(flags.get("canonical", True))
    want_mod = bool(flags.get("dateModified", True))

    if not isinstance(graph, dict):
        return graph, {"applied": False, "reason": "graph not a dict"}
    nodes = graph.get("@graph") or []
    if not isinstance(nodes, list):
        return graph, {"applied": False, "reason": "graph missing @graph list"}

    # Identify key nodes
    wp = _find_first(nodes, "WebPage")
    ws = _find_first(nodes, "WebSite")

    changes: List[Dict[str, Any]] = []

    # inLanguage
    if want_lang and wp is not None:
        lang = None
        # Accept 'en' if html_lang looks like 'en' or 'en-US' etc.
        if isinstance(html_lang, str) and html_lang.strip():
            lang_code = html_lang.strip()
            # Normalize BCP47 to lowercase language part
            lang = lang_code
        if lang:
            if wp.get("inLanguage") != lang:
                changes.append({"node": "WebPage", "set": {"inLanguage": lang}})
                if not shadow:
                    _set_if_absent(wp, "inLanguage", lang)

    # canonical
    if want_canon and wp is not None:
        # If a canonical link is provided and is same-host absolute URL, apply
        if isinstance(canonical_link, str) and canonical_link.strip():
            parsed = urlparse(canonical_link)
            site = urlparse(url)
            if parsed.scheme and parsed.netloc and parsed.netloc == site.netloc:
                if wp.get("url") != canonical_link:
                    changes.append({"node": "WebPage", "set": {"url": canonical_link}})
                    if not shadow:
                        wp["url"] = canonical_link

    # dateModified
    if want_mod:
        # Prefer an explicit meta (not provided here), else Last-Modified header
        iso = None
        if isinstance(last_modified_header, str) and last_modified_header.strip():
            iso = _parse_rfc2822(last_modified_header)
        if iso:
            # Apply to WebPage; optionally to top-level org if present
            if wp is not None and wp.get("dateModified") != iso:
                changes.append({"node": "WebPage", "set": {"dateModified": iso}})
                if not shadow:
                    _set_if_absent(wp, "dateModified", iso)

    applied = not shadow and len(changes) > 0
    diff = {"applied": applied, "shadow": shadow, "changes": changes}
    return (graph, diff)