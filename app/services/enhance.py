
from __future__ import annotations
import re
from urllib.parse import urlparse, urljoin
from typing import List, Dict, Tuple, Optional

SPECIALTY_MAP = {
    "cancer": "Oncologic",
    "oncology": "Oncologic",
    "oncologic": "Oncologic",
    "cardiology": "Cardiovascular",
    "heart": "Cardiovascular",
    "neuro": "Neurologic",
    "neurology": "Neurologic",
    "orthopedic": "Orthopedic",
    "orthopedics": "Orthopedic",
    "endocrine": "Endocrine",
    "endocrinology": "Endocrine",
    "gastro": "Gastroenterologic",
    "gastroenterology": "Gastroenterologic",
    "pulmonary": "Pulmonary",
    "pulmonology": "Pulmonary",
    "ophthalmology": "Ophthalmologic",
    "derm": "Dermatologic",
    "dermatology": "Dermatologic",
    "urology": "Urologic",
    "obgyn": "Obstetric",
    "obstetrics": "Obstetric",
    "gynecology": "Gynecologic",
    "pediatrics": "Pediatric"
}

def upgrade_specialty(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    key = value.strip().lower()
    key = re.sub(r'\b(care|center|clinic|department|program|services?)\b', '', key).strip()
    return SPECIALTY_MAP.get(key, SPECIALTY_MAP.get(key.split()[0], value))

def _ensure_graph(obj: dict) -> List[dict]:
    if isinstance(obj, dict) and "@graph" in obj and isinstance(obj["@graph"], list):
        return obj["@graph"]
    return [obj]

def _to_graph(obj: dict | list) -> dict:
    if isinstance(obj, dict) and "@graph" in obj:
        if "@context" not in obj:
            obj["@context"] = "https://schema.org"
        return obj
    return {"@context": "https://schema.org", "@graph": obj if isinstance(obj, list) else [obj]}

def _site_root(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}/"

def _extract_breadcrumbs_html(html: str) -> List[Tuple[str,str]]:
    blocks = []
    for m in re.finditer(r'(<nav[^>]*aria-label=["\']breadcrumb["\'][\s\S]*?</nav>)', html, flags=re.I):
        blocks.append(m.group(1))
    for m in re.finditer(r'(<ol[^>]*class=["\'][^"\']*breadcrumb[^"\']*["\'][\s\S]*?</ol>)', html, flags=re.I):
        blocks.append(m.group(1))
    if not blocks:
        return []
    block = blocks[0]
    items = []
    for a in re.finditer(r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>([\s\S]*?)</a>', block, flags=re.I):
        href = a.group(1).strip()
        text = re.sub(r'<[^>]+>', '', a.group(2)).strip()
        if text:
            items.append((text, href))
    return items

def _fallback_breadcrumbs_from_path(url: str) -> List[Tuple[str,str]]:
    p = urlparse(url)
    parts = [part for part in p.path.split('/') if part]
    crumbs = [("Montefiore Einstein Home", f"{p.scheme}://{p.netloc}/")]
    accum = ""
    for part in parts:
        accum = accum + "/" + part
        name = part.replace('-', ' ').title()
        crumbs.append((name, f"{p.scheme}://{p.netloc}{accum}"))
    return crumbs

EXCLUDE_CRUMB_PAT = re.compile(r'^(back to|view all|all\s+)', re.I)

def build_breadcrumb_list(html: str, url: str) -> dict | None:
    items = _extract_breadcrumbs_html(html)
    if not items:
        items = _fallback_breadcrumbs_from_path(url)
    seen = set()
    item_list = []
    pos = 1
    for name, href in items:
        if not href or EXCLUDE_CRUMB_PAT.search(name.strip()):
            continue
        if href.startswith('/'):
            href = urljoin(_site_root(url), href.lstrip('/'))
        key = (name.lower(), href)
        if key in seen:
            continue
        seen.add(key)
        item_list.append({"@type":"ListItem", "position": pos, "name": name.strip(), "item": href})
        pos += 1
    if not item_list:
        return None
    return {"@type":"BreadcrumbList", "itemListElement": item_list}

SOCIAL_DOMAINS = ("facebook.com","twitter.com","x.com/","instagram.com","linkedin.com","youtube.com","wikipedia.org","tiktok.com")

def extract_social_links(html: str) -> List[str]:
    profiles = []
    for m in re.finditer(r'href=["\'](https?://[^"\']+)["\']', html, flags=re.I):
        href = m.group(1)
        if any(d in href.lower() for d in SOCIAL_DOMAINS):
            profiles.append(href)
    out, seen = [], set()
    for h in profiles:
        if h not in seen:
            out.append(h); seen.add(h)
    return out

PHONE_PAT = re.compile(r'(\+?1[\s\-\.]*)?\(?\d{3}\)?[\s\-\.]?\d{3}[\s\-\.]?\d{4}')

def extract_phones(html: str) -> List[str]:
    phones = []
    for m in PHONE_PAT.finditer(html):
        phones.append(m.group(0))
    out, seen = [], set()
    for p in phones:
        digits = re.sub(r'\D', '', p)
        if len(digits) < 10:
            continue
        npa = digits[-10:-7]
        if npa and npa[0] in ('0','1'):
            continue
        normalized = "+1-" + "-".join([digits[-10:-7], digits[-7:-4], digits[-4:]])
        if normalized not in seen:
            out.append(normalized); seen.add(normalized)
    return out

def extract_pdq_fields(html: str) -> Dict[str, list]:
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'\s+', ' ', text)
    out = {"sign": [], "risk": [], "tests": [], "tx": [], "age": None}
    m_age = re.search(r'(infants?|toddlers?|children|under\s*5\s*years?|age\s*\d\s*to\s*\d)', text, re.I)
    if m_age:
        out["age"] = "Infancy to 5 years"
    def pull(section_kw, limit=4):
        pat = re.compile(rf'{section_kw}[^:.]*[:\-]\s*([^\.;]+)', re.I)
        hits = []
        for m in pat.finditer(text):
            items = [x.strip(" .,:;") for x in re.split(r',|;|\band\b', m.group(1)) if len(x.strip())>2]
            for it in items:
                hits.append(it[:80])
                if len(hits) >= limit:
                    break
            if len(hits) >= limit:
                break
        return hits
    out["sign"] = pull("signs? and symptoms?|symptoms?") or out["sign"]
    out["risk"] = pull("risk factors?") or out["risk"]
    out["tests"] = pull("diagnostic tests?|tests?") or out["tests"]
    out["tx"] = pull("treatments?|therapy|therapies") or out["tx"]
    return out

def find_node(nodes: List[dict], typ: str) -> Optional[dict]:
    for n in nodes:
        if isinstance(n, dict):
            t = n.get("@type")
            if t == typ or (isinstance(t, list) and typ in t):
                return n
    return None

def ensure_webpage(nodes: List[dict], url: str, subject: Optional[str], about_id: Optional[str]) -> dict:
    web = find_node(nodes, "MedicalWebPage") or find_node(nodes, "WebPage")
    if not web:
        web = {"@type": "MedicalWebPage", "url": url, "name": subject or ""}
        nodes.append(web)
    web.setdefault("url", url)
    if subject:
        web.setdefault("name", subject)
    if about_id:
        web["about"] = {"@id": about_id}
        web.setdefault("mainEntity", {"@id": about_id})
    return web

def enhance_jsonld(base: dict, secondaries: list[str], html: str, url: str, topic: Optional[str], subject: Optional[str]) -> dict:
    nodes = _ensure_graph(base)
    root = nodes[0] if nodes else {}

    if topic:
        upgraded = upgrade_specialty(topic)
        if upgraded:
            if isinstance(root.get("medicalSpecialty"), list):
                if upgraded not in root["medicalSpecialty"]:
                    root["medicalSpecialty"].append(upgraded)
            elif root.get("medicalSpecialty"):
                root["medicalSpecialty"] = upgraded
            else:
                root["medicalSpecialty"] = upgraded

    p = urlparse(url)
    is_condition_page = "/cancer/types/" in p.path

    if is_condition_page:
        cond = find_node(nodes, "MedicalCondition")
        if cond:
            for k in ("address", "telephone", "contactPoint"):
                if k in cond:
                    cond.pop(k, None)

    socials = extract_social_links(html)
    if socials:
        org = find_node(nodes, "MedicalOrganization") or find_node(nodes, "Hospital")
        if org:
            same_as = set(org.get("sameAs", []))
            for s in socials:
                same_as.add(s)
            org["sameAs"] = list(same_as)

    phones = extract_phones(html)
    if phones:
        org = find_node(nodes, "MedicalOrganization") or find_node(nodes, "Hospital")
        if org and "contactPoint" not in org:
            org["contactPoint"] = [{"@type": "ContactPoint", "contactType": "appointments", "telephone": phones[0]}]
        elif org and "telephone" not in org:
            org["telephone"] = phones[0]

    web = ensure_webpage(nodes, url, subject, about_id=None)
    bc = build_breadcrumb_list(html, url)
    if bc:
        nodes = [n for n in nodes if not (isinstance(n, dict) and n.get("@type") == "BreadcrumbList")]
        nodes.append(bc)
        web["breadcrumb"] = bc

    if is_condition_page:
        cond = find_node(nodes, "MedicalCondition")
        if cond:
            cond_id = cond.get("@id") or (url + "#condition")
            cond["@id"] = cond_id
            web["about"] = {"@id": cond_id}
            web["mainEntity"] = {"@id": cond_id}

            pdq = extract_pdq_fields(html)
            if pdq.get("age") and not cond.get("typicalAgeRange"):
                cond["typicalAgeRange"] = pdq["age"]
            if pdq["sign"]:
                cond.setdefault("signOrSymptom", [])
                for s in pdq["sign"][:3]:
                    cond["signOrSymptom"].append({"@type":"MedicalSignOrSymptom","name": s})
            if pdq["risk"]:
                cond.setdefault("riskFactor", [])
                for r in pdq["risk"][:5]:
                    cond["riskFactor"].append(r)
            if pdq["tests"]:
                cond.setdefault("typicalTest", [])
                for t in pdq["tests"][:3]:
                    cond["typicalTest"].append({"@type":"MedicalTest","name": t})
            if pdq["tx"]:
                cond.setdefault("possibleTreatment", [])
                for tx in pdq["tx"][:5]:
                    cond["possibleTreatment"].append({"@type":"MedicalTherapy","name": tx})

            if re.search(r'\bPDQ\b|National Cancer Institute|cancer\.gov', html, re.I):
                web.setdefault("citation", [])
                joined = " ".join(web["citation"]) if isinstance(web["citation"], list) else str(web["citation"])
                if "https://www.cancer.gov" not in joined:
                    if isinstance(web["citation"], list):
                        web["citation"].append("https://www.cancer.gov")
                    else:
                        web["citation"] = ["https://www.cancer.gov"]

    return _to_graph(nodes)
