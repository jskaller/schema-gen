from __future__ import annotations
from typing import Dict, Any, List, Optional
import re
from urllib.parse import urlparse
from bs4 import BeautifulSoup

# Domains we consider for sameAs (social + brand/affiliates)
SOCIAL_DOMAINS = [
    "facebook.com", "twitter.com", "x.com", "linkedin.com",
    "instagram.com", "youtube.com", "tiktok.com",
    "montefioreeinstein.org", "einsteinmed.edu", "cham.org",
]

# Phone numbers like (212) 555-1212, 212-555-1212, +1 212 555 1212
PHONE_RE = re.compile(
    r"(?:\+?\d{1,2}[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}"
)

# Street + type, optional unit, optional "City, ST 12345"
ADDRESS_HINT_RE = re.compile(
    r"\b(\d{1,6}\s+[A-Za-z0-9.\-'\s]+(?:Street|St\.?|Avenue|Ave\.?|Road|Rd\.?|"
    r"Boulevard|Blvd\.?|Lane|Ln\.?|Drive|Dr\.?|Way|Court|Ct\.?|Place|Pl\.?|Plaza|"
    r"Parkway|Pkwy|Highway|Hwy|Turnpike|Tpke))\b"
    r"(?:[ ,\n]*(?:Suite|Ste\.?|\#)\s*\w+)?"
    r"(?:[ ,\n]*([A-Za-z\s]+,\s*[A-Z]{2}\s*\d{5}))?",
    re.IGNORECASE,
)

# Opening hours like "Mon - Fri 8:00am - 5:00pm"
DAY_MAP = {
    "mon": "Mo", "monday": "Mo",
    "tue": "Tu", "tues": "Tu", "tuesday": "Tu",
    "wed": "We", "wednesday": "We",
    "thu": "Th", "thur": "Th", "thurs": "Th", "thursday": "Th",
    "fri": "Fr", "friday": "Fr",
    "sat": "Sa", "saturday": "Sa",
    "sun": "Su", "sunday": "Su",
}

def _normalize_time_24h(t: str) -> str:
    s = t.strip().lower().replace(" ", "")
    m = re.match(r"^(\d{1,2})(?::(\d{2}))?(am|pm)$", s)
    if not m:
        return t.strip()
    h = int(m.group(1)); mins = int(m.group(2) or 0); ap = m.group(3)
    if ap == "pm" and h != 12: h += 12
    if ap == "am" and h == 12: h = 0
    return f"{h:02d}:{mins:02d}"

HOURS_RANGE_RE = re.compile(
    r"(?P<d1>Mon|Tue|Tues|Wed|Thu|Thur|Thurs|Fri|Sat|Sun)\s*[-–]\s*"
    r"(?P<d2>Mon|Tue|Tues|Wed|Thu|Thur|Thurs|Fri|Sat|Sun)\s*"
    r"(?P<t1>\d{1,2}:?\d{0,2}\s*(?:am|pm))\s*[-–]\s*"
    r"(?P<t2>\d{1,2}:?\d{0,2}\s*(?:am|pm))",
    re.IGNORECASE
)

def extract_phone(text: str) -> Optional[List[str]]:
    phones = PHONE_RE.findall(text or "")
    # Deduplicate while preserving order
    out: List[str] = []
    seen = set()
    for p in phones:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out or None

def extract_address(text: str) -> Optional[str]:
    m = ADDRESS_HINT_RE.search(text or "")
    if not m:
        return None
    street = m.group(1).strip()
    citystate = (m.group(2) or "").strip()
    return f"{street}, {citystate}" if citystate else street

def extract_opening_hours(text: str) -> Optional[List[str]]:
    m = HOURS_RANGE_RE.search(text or "")
    if not m:
        return None
    d1 = DAY_MAP[m.group("d1").lower()]
    d2 = DAY_MAP[m.group("d2").lower()]
    t1 = _normalize_time_24h(m.group("t1"))
    t2 = _normalize_time_24h(m.group("t2"))
    return [f"{d1}-{d2} {t1}-{t2}"]

def extract_social_sameas(html: str) -> Optional[List[str]]:
    try:
        soup = BeautifulSoup(html or "", "lxml")
    except Exception:
        soup = BeautifulSoup(html or "", "html.parser")
    links: List[str] = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        netloc = urlparse(href).netloc.lower()
        if not netloc:
            continue
        if any(netloc.endswith(d) for d in SOCIAL_DOMAINS):
            if href not in seen:
                seen.add(href)
                links.append(href)
    return links or None

def extract_signals(html: str) -> Dict[str, Any]:
    # Create a plain text for regex scanning
    try:
        text = BeautifulSoup(html or "", "lxml").get_text(" ", strip=True)
    except Exception:
        text = BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True)
    return {
        "telephone": extract_phone(text),
        "address": extract_address(text),
        "openingHours": extract_opening_hours(text),
        "sameAs": extract_social_sameas(html),
    }
