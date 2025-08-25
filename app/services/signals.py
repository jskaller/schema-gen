
from __future__ import annotations
from typing import Dict, Any, List, Optional
import re
from bs4 import BeautifulSoup

SOCIAL_DOMAINS = [
    "facebook.com", "twitter.com", "x.com", "linkedin.com",
    "instagram.com", "youtube.com", "tiktok.com"
]

PHONE_RE = re.compile(
    r"(?:\+?\d{1,2}[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}"
)
ADDRESS_HINT_RE = re.compile(
    r"\b(\d{1,5}\s+[A-Za-z0-9.\-'\s]+(?:Street|St\.?|Avenue|Ave\.?|Road|Rd\.?|Boulevard|Blvd\.?|Lane|Ln\.?|Drive|Dr\.?|Way|Court|Ct\.?|Place|Pl\.?))\b",
    re.IGNORECASE,
)

def extract_social_sameas(html: str) -> List[str]:
    soup = BeautifulSoup(html, "lxml")
    urls: List[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if any(d in href for d in SOCIAL_DOMAINS):
            urls.append(href)
    seen = set()
    out: List[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out

def extract_phone(html_text: str) -> Optional[str]:
    m = PHONE_RE.search(html_text)
    return m.group(0) if m else None

def extract_address(html_text: str) -> Optional[str]:
    m = ADDRESS_HINT_RE.search(html_text)
    return m.group(1) if m else None

def extract_signals(html: str) -> Dict[str, Any]:
    text = BeautifulSoup(html, "lxml").get_text(" ", strip=True)
    return {
        "phone": extract_phone(text),
        "address": extract_address(text),
        "sameAs": extract_social_sameas(html),
    }
