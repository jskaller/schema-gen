
from __future__ import annotations
import re
from urllib.parse import urlparse, urljoin

# Map common user/page terms to Schema.org MedicalSpecialty enum values
SPECIALTY_MAP = {
    "cancer": "Oncologic",
    "oncology": "Oncologic",
    "oncologic": "Oncologic",
    "cardiology": "Cardiovascular",
    "heart": "Cardiovascular",
    "neuro": "Neurologic",
    "neurology": "Neurologic",
    "orthopedic": "Orthopedic",
    "orthopaedic": "Orthopedic",
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
    "pediatrics": "Pediatric",
}

def upgrade_specialty(value: str | None) -> str | None:
    if not value:
        return None
    key = value.strip().lower()
    # normalize phrases like "cancer care", "cancer center"
    key = re.sub(r'\b(care|center|clinic|department|program|services?)\b', '', key).strip()
    return SPECIALTY_MAP.get(key, SPECIALTY_MAP.get(key.split()[0], value))

def _ensure_graph(obj: dict) -> list:
    """Return a list of nodes; if obj already has @graph, use it, else return [obj]."""
    if isinstance(obj, dict) and "@graph" in obj and isinstance(obj["@graph"], list):
        return obj["@graph"]
    return [obj]

def _to_graph(obj: dict | list) -> dict:
    """Wrap list of nodes in {'@context':'https://schema.org','@graph':[...]} if needed."""
    if isinstance(obj, dict) and "@graph" in obj:
        if "@context" not in obj:
            obj["@context"] = "https://schema.org"
        return obj
    return {"@context": "https://schema.org", "@graph": obj if isinstance(obj, list) else [obj]}

def _site_root(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}/"

def _extract_breadcrumbs_html(html: str) -> list[tuple[str,str]]:
    """
    Very light-weight breadcrumb extractor:
    - looks for aria-label="breadcrumb" or class names containing 'breadcrumb'
    - captures anchor text + href order
    Returns list of (name, href)
    """
    blocks = []
    # Find containers that look like breadcrumbs
    for m in re.finditer(r'(<nav[^>]*aria-label=["\']breadcrumb["\'][\s\S]*?</nav>)', html, flags=re.I):
        blocks.append(m.group(1))
    for m in re.finditer(r'(<ol[^>]*class=["\'][^"\']*breadcrumb[^"\']*["\'][\s\S]*?</ol>)', html, flags=re.I):
        blocks.append(m.group(1))
    if not blocks:
        return []
    # Parse anchors in first block
    block = blocks[0]
    items = []
    for a in re.finditer(r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>([\s\S]*?)</a>', block, flags=re.I):
        href = a.group(1).strip()
        text = re.sub(r'<[^>]+>', '', a.group(2)).strip()
        if text:
            items.append((text, href))
    return items

def _fallback_breadcrumbs_from_path(url: str) -> list[tuple[str,str]]:
    p = urlparse(url)
    parts = [part for part in p.path.split('/') if part]
    crumbs = [("Home", f"{p.scheme}://{p.netloc}/")]
    accum = ""
    for part in parts:
        accum = accum + "/" + part
        name = part.replace('-', ' ').title()
        crumbs.append((name, f"{p.scheme}://{p.netloc}{accum}"))
    return crumbs

def build_breadcrumb_list(html: str, url: str) -> dict | None:
    items = _extract_breadcrumbs_html(html)
    if not items:
        items = _fallback_breadcrumbs_from_path(url)
    # de-duplicate, ensure last is the page url
    seen = set()
    item_list = []
    pos = 1
    for name, href in items:
        if not href:
            continue
        if href.startswith('/'):
            href = urljoin(_site_root(url), href.lstrip('/'))
        key = (name.lower(), href)
        if key in seen:
            continue
        seen.add(key)
        item_list.append({"@type":"ListItem", "position": pos, "name": name, "item": href})
        pos += 1
    if not item_list:
        return None
    return {"@type":"BreadcrumbList", "itemListElement": item_list}

def extract_social_links(html: str, base_url: str) -> list[str]:
    profiles = []
    for m in re.finditer(r'href=["\'](https?://[^"\']+)["\']', html, flags=re.I):
        href = m.group(1)
        if any(domain in href.lower() for domain in ["facebook.com","twitter.com","x.com/","instagram.com","linkedin.com","youtube.com","wikipedia.org","tiktok.com"]):
            profiles.append(href)
    # unique preserve order
    seen = set(); out = []
    for h in profiles:
        if h not in seen:
            out.append(h); seen.add(h)
    return out

def extract_phones(html: str) -> list[str]:
    phones = []
    for m in re.finditer(r'(\+?1[\s\-\.]*)?\(?\d{3}\)?[\s\-\.]?\d{3}[\s\-\.]?\d{4}', html):
        phones.append(m.group(0))
    seen = set(); out = []
    for p in phones:
        p_norm = re.sub(r'[^0-9\+]', '', p)
        if p_norm not in seen:
            out.append(p if p.startswith('+') else "+1-" + "-".join([p_norm[-10:-7], p_norm[-7:-4], p_norm[-4:]]))
            seen.add(p_norm)
    return out

def enhance_jsonld(base: dict, secondaries: list[str], html: str, url: str, topic: str | None, subject: str | None) -> dict:
    nodes = _ensure_graph(base)
    # Root node assumed to be first
    root = nodes[0]

    # 1) Specialty upgrade
    if topic:
        upgraded = upgrade_specialty(topic)
        if upgraded and root.get("medicalSpecialty"):
            root["medicalSpecialty"] = upgraded
        elif upgraded:
            root["medicalSpecialty"] = upgraded

    # 2) Social profiles
    same_as = set(root.get("sameAs", []))
    for prof in extract_social_links(html, url):
        same_as.add(prof)
    if same_as:
        root["sameAs"] = list(same_as)

    # 3) Contact points (simple heuristic: first phone becomes appointments line if not present)
    phones = extract_phones(html)
    if phones and "contactPoint" not in root:
        root["contactPoint"] = [{
            "@type": "ContactPoint",
            "contactType": "appointments",
            "telephone": phones[0]
        }]
    elif phones:
        # ensure at least one phone is present
        if not root.get("telephone"):
            root["telephone"] = phones[0]

    # 4) WebPage node: ensure it exists and links to breadcrumbs
    web = next((n for n in nodes if isinstance(n, dict) and n.get("@type") in ("WebPage","MedicalWebPage")), None)
    if not web:
        web = {"@type": "MedicalWebPage", "name": subject or root.get("name") or "", "url": url}
        nodes.append(web)
    web.setdefault("url", url)
    web.setdefault("name", subject or root.get("name") or "")
    web.setdefault("about", root.get("name"))

    # 5) Breadcrumbs
    bc = build_breadcrumb_list(html, url)
    if bc:
        nodes.append(bc)
        web["breadcrumb"] = bc

    return _to_graph(nodes)
