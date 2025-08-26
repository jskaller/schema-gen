# enhance.py hardened (v40m)
print("[enhance v40m] loaded", flush=True)

import re
from typing import Dict, Any, List, Optional

try:
    from bs4 import BeautifulSoup  # type: ignore
except Exception:  # pragma: no cover
    BeautifulSoup = None  # type: ignore

def _clean_list(items):
    out = []
    for x in items or []:
        if isinstance(x, str):
            y = x.strip(" .,:;\n\t")
            if len(y) >= 2:
                out.append(y)
    return out

def _safe_split(s: Optional[str]) -> List[str]:
    if not isinstance(s, str):
        return []
    try:
        parts = re.split(r",|;|\band\b", s, flags=re.I)
    except Exception:
        return []
    return _clean_list(parts)

def safe_extract_text(html: Optional[str]) -> str:
    if not html or not isinstance(html, str):
        return ""
    if BeautifulSoup is None:
        try:
            return re.sub(r"<[^>]+>", " ", html)
        except Exception:
            return ""
    try:
        soup = BeautifulSoup(html, "html.parser")
        return soup.get_text(" ")[:200000]
    except Exception:
        return ""

def extract_pdq_fields(html: Optional[str]) -> Dict[str, List[str]]:
    text = safe_extract_text(html).lower()
    if not text:
        print("[enhance v40m] PDQ skipped (no text)", flush=True)
        return {}

    def pull(pattern: str) -> List[str]:
        try:
            m = re.search(pattern + r"[:\-\s]+([^\n\r\.]*)", text, flags=re.I)
        except re.error:
            return []
        if not m:
            return []
        group = m.group(1) if m.lastindex and m.lastindex >= 1 else ""
        return _safe_split(group)

    out: Dict[str, List[str]] = {}
    signs = pull(r"signs? and symptoms?|symptoms?")
    if signs: out["sign"] = signs
    who = pull(r"who (?:gets|is at risk for)|risk factors?")
    if who: out["who"] = who
    cause = pull(r"cause[s]?|risk factor[s]?")
    if cause: out["cause"] = cause
    diagnosis = pull(r"diagnos(?:is|ed)|how .* diagnosed")
    if diagnosis: out["dx"] = diagnosis
    treat = pull(r"treatments?|how .* treated")
    if treat: out["tx"] = treat

    print(f"[enhance v40m] PDQ extracted keys={list(out.keys())}", flush=True)
    return out

def enhance_jsonld(final_jsonld: Any, secondary_types: List[str], html: Optional[str], url: str, topic: str, subject: str) -> Any:
    try:
        data = final_jsonld
        if isinstance(data, dict) and "@graph" in data and isinstance(data["@graph"], list):
            graph = data["@graph"]
        elif isinstance(data, dict):
            graph = [data]
        else:
            graph = []

        # Breadcrumb fallback
        has_crumb = any(isinstance(n, dict) and n.get("@type") == "BreadcrumbList" for n in graph)
        if not has_crumb and isinstance(url, str) and url:
            try:
                from urllib.parse import urlparse
                p = urlparse(url)
                parts = [x for x in (p.path or "").split("/") if x]
                if parts:
                    crumb = {"@type": "BreadcrumbList", "itemListElement": []}
                    for i, part in enumerate(parts):
                        crumb["itemListElement"].append({
                            "@type": "ListItem",
                            "position": i+1,
                            "name": part.replace("-", " ").title(),
                            "item": f"{p.scheme}://{p.netloc}/" + "/".join(parts[:i+1])
                        })
                    graph.append(crumb)
                    print("[enhance v40m] breadcrumb added", flush=True)
            except Exception as e:
                print(f"[enhance v40m] breadcrumb failed: {e}", flush=True)

        pdq = extract_pdq_fields(html)
        if pdq:
            for n in graph:
                if not isinstance(n, dict): 
                    continue
                if n.get("@type") == "MedicalCondition":
                    if pdq.get("sign"):
                        n.setdefault("signOrSymptom", [])
                        if isinstance(n["signOrSymptom"], list):
                            for item in pdq["sign"]:
                                n["signOrSymptom"].append({"@type": "MedicalSignOrSymptom", "name": item})
                    if pdq.get("who"):
                        n.setdefault("epidemiology", "; ".join(pdq["who"]))
                    if pdq.get("cause"):
                        n.setdefault("cause", "; ".join(pdq["cause"]))
                    if pdq.get("dx"):
                        n.setdefault("naturalHistory", "; ".join(pdq["dx"]))
                    if pdq.get("tx"):
                        n.setdefault("possibleTreatment", [])
                        if isinstance(n["possibleTreatment"], list):
                            for item in pdq["tx"]:
                                n["possibleTreatment"].append({"@type": "TherapeuticProcedure", "name": item})
            print("[enhance v40m] PDQ enrichment applied", flush=True)

        if isinstance(final_jsonld, dict) and "@graph" in final_jsonld and isinstance(final_jsonld["@graph"], list):
            final_jsonld["@graph"] = graph
            return final_jsonld
        elif isinstance(final_jsonld, dict):
            return {"@context": "https://schema.org", "@graph": graph}
        else:
            return final_jsonld
    except Exception as e:
        print(f"[enhance v40m] enhance_jsonld caught: {e}", flush=True)
        return final_jsonld
