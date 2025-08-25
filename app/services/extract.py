from bs4 import BeautifulSoup
from lxml.html import fromstring
from readability import Document

BLOCK_TAGS = {"nav", "footer", "header", "aside"}
STRIP_TAGS = {"script", "style", "noscript", "form", "template"}

def readability_skim(html: str) -> str:
    """
    Use readability-lxml to get the main content HTML (summary).
    """
    doc = Document(html)
    # title = doc.short_title()  # (optional) could return alongside content
    return doc.summary(html_partial=True)

def strip_noise(html: str) -> str:
    """
    Remove scripts/styles/forms and common chrome (nav/footer/header/aside).
    """
    soup = BeautifulSoup(html, "lxml")

    # Drop known noisy tags globally
    for tg in STRIP_TAGS:
        for el in soup.find_all(tg):
            el.decompose()

    # Remove common chrome containers by tag and by class/id hints
    for tg in BLOCK_TAGS:
        for el in soup.find_all(tg):
            el.decompose()
    for el in soup.select(
        "[role=navigation], .nav, .navbar, .site-header, .site-footer, .footer, .breadcrumb, .breadcrumbs, .cookie, .cookie-banner, .banner, .ads, .ad, .promo"
    ):
        el.decompose()

    return str(soup)

def extract_clean_text(html: str) -> str:
    """
    Run readability, then strip residual noise and return plain text.
    """
    main_html = readability_skim(html)
    cleaned_html = strip_noise(main_html)
    soup = BeautifulSoup(cleaned_html, "lxml")
    text = soup.get_text(separator="\n", strip=True)

    # Normalize excessive blank lines
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    return "\n".join(lines)
