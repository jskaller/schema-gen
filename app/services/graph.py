from __future__ import annotations
from typing import Dict, Any, List
from urllib.parse import urlparse

def _breadcrumb_from_url(url: str) -> Dict[str, Any]:
    parts = [p for p in urlparse(url or "").path.split("/") if p]
    items = []
    base = f"{urlparse(url or '').scheme}://{urlparse(url or '').netloc}" if url else ""
    accum = ""
    pos = 1
    for p in parts:
        accum += "/" + p
        items.append({
            "@type": "ListItem",
            "position": pos,
            "item": {"@id": (base + accum) if base else accum, "name": p}
        })
        pos += 1
    return {"@type": "BreadcrumbList", "itemListElement": items}

def assemble_graph(primary: Dict[str, Any], secondary_types: List[str], url: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
    ctx = primary.get("@context", "https://schema.org")
    graph: List[Dict[str, Any]] = [primary]

    types = [t.strip() for t in (secondary_types or []) if t and t.strip()]
    for t in types:
        lt = t.lower()
        if lt in ("medicalwebpage", "webpage"):
            node = {
                "@type": "WebPage",
                "url": url,
                "name": inputs.get("subject") or primary.get("name") or "",
            }
            graph.append(node)
        elif lt in ("website", "web site"):
            site = {
                "@type": "WebSite",
                "url": urlparse(url).scheme + "://" + urlparse(url).netloc if url else "",
                "name": inputs.get("site_name") or primary.get("name") or ""
            }
            graph.append(site)
        elif lt in ("medicalorganization", "medical organization"):
            node = {
                "@type": "MedicalOrganization",
                "name": inputs.get("org_name") or primary.get("name") or "",
            }
            if url:
                node["url"] = url
            graph.append(node)
        elif lt == "medicalclinic":
            node = {"@type": "MedicalClinic", "name": inputs.get("subject") or primary.get("name") or ""}
            if url:
                node["url"] = url
            graph.append(node)
        elif lt == "medicalservice":
            node = {"@type": "MedicalService", "name": inputs.get("topic") or primary.get("name") or ""}
            graph.append(node)
        elif lt == "medicalspecialty":
            spec = primary.get("medicalSpecialty") or inputs.get("topic")
            if spec:
                graph.append({"@type": "MedicalSpecialty", "name": spec})
        elif lt == "breadcrumblist":
            graph.append(_breadcrumb_from_url(url))
        elif lt == "logo":
            # Represent as an ImageObject; if we know a URL pass it via inputs["logo"]
            logo = {"@type": "ImageObject"}
            if inputs.get("logo"):
                logo["contentUrl"] = inputs["logo"]
            logo["name"] = "Logo"
            graph.append(logo)
        elif lt == "jobposting":
            # Added here; sanitizer will drop it later if requireds are missing
            graph.append({"@type": "JobPosting"})
        else:
            graph.append({"@type": t})

    return {"@context": ctx, "@graph": graph}