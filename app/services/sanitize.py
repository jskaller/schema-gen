
from typing import Any, Dict, List, Optional
import re
from urllib.parse import urlparse

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

def _flatten_embedded_graphs(graph: List[Dict]):
    out: List[Dict] = []
    for node in graph:
        if not isinstance(node, dict): continue
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
        if v is None: continue
        if isinstance(v, (list, dict)) and not v: continue
        clean[k] = v
    return clean

def _coerce_audience(n: Dict) -> None:
    val = n.get("audience")
    if isinstance(val, str):
        n["audience"] = {"@type": "Audience", "audienceType": val}
    elif isinstance(val, list) and val and isinstance(val[0], str):
        n["audience"] = {"@type": "Audience", "audienceType": val[0]}

def _parse_address_str(addr: str) -> Optional[Dict[str, str]]:
    s = " ".join((addr or "").split())
    if not s: return None
    # simple heuristic: "..., City, ST 12345"
    m = re.search(r"(?P<street>.+?),\s*(?P<city>[A-Za-z .'-]+),\s*(?P<region>[A-Z]{2})\s*(?P<zip>\d{5}(?:-\d{4})?)?", s)
    if not m:
        return None
    out = {
        "@type": "PostalAddress",
        "streetAddress": m.group("street").strip(),
        "addressLocality": m.group("city").strip(),
        "addressRegion": m.group("region").strip(),
    }
    if m.group("zip"):
        out["postalCode"] = m.group("zip")
    return out

def _coerce_address(n: Dict) -> None:
    addr = n.get("address")
    if isinstance(addr, str):
        parsed = _parse_address_str(addr)
        if parsed:
            n["address"] = parsed
        else:
            # un-parseable junk — drop it so we don't fail validation
            n.pop("address", None)

def _fill_from_hints(n: Dict, hints: Dict[str, Any]) -> None:
    if "url" not in n and hints.get("url"): n["url"] = hints["url"]
    if "name" not in n and hints.get("name"): n["name"] = hints["name"]
    if "telephone" not in n and hints.get("telephone"): n["telephone"] = hints["telephone"]
    if "address" not in n and hints.get("address"): n["address"] = hints["address"]
    if "audience" not in n and hints.get("audience"): n["audience"] = {"@type": "Audience", "audienceType": hints["audience"]}
    if "dateModified" not in n and hints.get("dateModified"): n["dateModified"] = hints["dateModified"]
    if "sameAs" not in n and hints.get("sameAs"): n["sameAs"] = hints["sameAs"]
    if "medicalSpecialty" not in n and hints.get("medicalSpecialty"): n["medicalSpecialty"] = hints["medicalSpecialty"]
    if "description" not in n and hints.get("description"): n["description"] = hints["description"]
    if "openingHours" not in n and hints.get("openingHours"): n["openingHours"] = hints["openingHours"]
    _coerce_address(n)
    # CONTACTPOINT_FROM_TELEPHONES
    try:
        tels = hints.get("telephone")
        if tels and isinstance(tels, list):
            cps = [{"@type":"ContactPoint","telephone": t} for t in tels]
            if n.get("contactPoint") is None:
                n["contactPoint"] = cps
    except Exception:
        pass

def _needs_breadcrumbs(url: Optional[str]) -> bool:
    try:
        u = urlparse(url or "")
        return bool(u.path and u.path.strip("/"))
    except Exception:
        return False


def _has_required_jobposting_fields(node: Dict[str, Any]) -> bool:
    req = ["title","datePosted","hiringOrganization"]
    if not all(node.get(k) for k in req):
        return False
    # location is required via jobLocation or via valid remote schema
    has_loc = bool(node.get("jobLocation")) or (node.get("jobLocationType") in ["TELECOMMUTE","REMOTE"])
    return has_loc


def sanitize_jsonld(data: Any, primary_type: str, url: Optional[str], secondary_types: Optional[List[str]] = None, hints: Optional[Dict[str, Any]] = None) -> Dict:
    hints = hints or {}
    graph = _ensure_graph(data)
    graph = _flatten_embedded_graphs(graph)

    cleaned: List[Dict] = []
    for n in graph:
        n = _drop_nulls_and_empty(n)
        _coerce_audience(n)
        _coerce_address(n)
    # CONTACTPOINT_FROM_TELEPHONES
    try:
        tels = hints.get("telephone")
        if tels and isinstance(tels, list):
            cps = [{"@type":"ContactPoint","telephone": t} for t in tels]
            if n.get("contactPoint") is None:
                n["contactPoint"] = cps
    except Exception:
        pass
        cleaned.append(n)

    # Ensure root primary
    root_idx = None
    for i, n in enumerate(cleaned):
        if n.get("@type") == primary_type:
            root_idx = i; break
    if root_idx is None:
        if cleaned and (("@type" not in cleaned[0]) or cleaned[0].get("@type") in ("Thing","WebPage","MedicalWebPage")):
            cleaned[0]["@type"] = primary_type; root_idx = 0
        if root_idx is None:
            root = {"@context": "https://schema.org", "@type": primary_type}
            if url: root["url"] = url
            _fill_from_hints(root, hints)
            cleaned.insert(0, root); root_idx = 0

    _fill_from_hints(cleaned[root_idx], hints)

    # Ensure MedicalOrganization node
    if "MedicalOrganization" in set(secondary_types or []):
        mo = next((n for n in cleaned if n.get("@type") == "MedicalOrganization"), None)
        if not mo:
            mo = {"@type": "MedicalOrganization"}
            cleaned.append(mo)
        _fill_from_hints(mo, hints)

    # _JOBPOSTING_GUARD: drop JobPosting nodes that fail Google requireds, fallback to WebPage/CollectionPage
    filtered: List[Dict] = []
    for n in cleaned:
        if n.get("@type") == "JobPosting" and not _has_required_jobposting_fields(n):
            # Skip invalid JobPosting
            continue
        filtered.append(n)
    cleaned = filtered

    # Always ensure BreadcrumbList for interior pages when URL has a path
    if _needs_breadcrumbs(url):
        if not any(n.get("@type") == "BreadcrumbList" for n in cleaned):
            from app.services.graph import _breadcrumb_from_url
            try:
                cleaned.append(_breadcrumb_from_url(url))
            except Exception:
                pass

    # Ensure MedicalWebPage basics
    if "MedicalWebPage" in set(secondary_types or []):
        mwp = next((n for n in cleaned if n.get("@type") == "MedicalWebPage"), None)
        if not mwp:
            mwp = {"@type": "MedicalWebPage"}
            cleaned.append(mwp)
        if "url" not in mwp and url: mwp["url"] = url
        if "name" not in mwp and hints.get("name"): mwp["name"] = hints["name"]
        if "about" not in mwp and hints.get("name"): mwp["about"] = hints["name"]


    # _JOBPOSTING_GUARD: drop JobPosting nodes that fail Google requireds; fallback ensured by WebPage/CollectionPage present elsewhere
    filtered: List[Dict] = []
    for _n in cleaned:
        if _n.get("@type") == "JobPosting" and not _has_required_jobposting_fields(_n):
            continue
        filtered.append(_n)
    cleaned = filtered

    # Always ensure BreadcrumbList for interior pages
    if _needs_breadcrumbs(url):
        has_bc = any(isinstance(x, dict) and x.get("@type") == "BreadcrumbList" for x in cleaned)
        if not has_bc:
            # Minimal breadcrumb from URL path
            parts = [p for p in (urlparse(url or "").path or "").split("/") if p]
            items = []
            base = f"{urlparse(url or '').scheme}://{urlparse(url or '').netloc}"
            accum = ""
            for i, p in enumerate(parts, start=1):
                accum += "/" + p
                items.append({"@type":"ListItem","position": i,"name": p.replace('-', ' ').title(),"item": base+accum})
            if items:
                cleaned.append({"@type": "BreadcrumbList", "itemListElement": items})

    return {"@context": "https://schema.org", "@graph": cleaned}
