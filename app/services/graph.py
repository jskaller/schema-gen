
from __future__ import annotations
from typing import Dict, Any, List
from urllib.parse import urlparse

def _breadcrumb_from_url(url: str) -> Dict[str, Any]:
    parts = [p for p in urlparse(url).path.split("/") if p]
    items = []
    base = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    accum = ""
    pos = 1
    for p in parts:
        accum += "/" + p
        items.append({
            "@type":"ListItem",
            "position": pos,
            "name": p.replace("-", " ").title(),
            "item": base + accum
        })
        pos += 1
    return {
        "@type": "BreadcrumbList",
        "itemListElement": items or [{
            "@type":"ListItem","position":1,"name":"Home","item": base
        }]
    }

def assemble_graph(primary: Dict[str, Any], secondary_types: List[str], url: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
    # Wrap into @graph and add secondary stubs when requested
    ctx = primary.get("@context", "https://schema.org")
    graph: List[Dict[str, Any]] = [primary]

    types = [t.strip() for t in (secondary_types or []) if t and t.strip()]
    for t in types:
        if t.lower() in ("medicalwebpage","webpage"):
            node = {
                "@type": "MedicalWebPage",
                "url": url,
                "name": inputs.get("subject") or primary.get("name") or "",
                "about": primary.get("name") or inputs.get("topic") or ""
            }
            graph.append(node)
        elif t.lower() == "hospital":
            node = {
                "@type": "Hospital",
                "name": inputs.get("subject") or primary.get("name") or "",
                "address": primary.get("address"),
                "telephone": primary.get("telephone")
            }
            graph.append(node)
        elif t.lower() == "medicalspecialty":
            # Represent as a node for user visibility, even though it's usually an enumeration
            spec = primary.get("medicalSpecialty") or inputs.get("topic") or "General"
            node = {"@type": "MedicalSpecialty", "name": spec}
            graph.append(node)
        elif t.lower() == "breadcrumblist":
            graph.append(_breadcrumb_from_url(url))
        else:
            # Generic stub
            graph.append({"@type": t})

    return {"@context": ctx, "@graph": graph}
