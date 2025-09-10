# tests/test_enrichment_phase1.py
from app.services.enrichment import enrich_phase1

def test_shadow_mode_no_apply():
    graph = {"@context": "https://schema.org", "@graph": [{"@type": "WebPage", "url": "https://x/y"}]}
    g2, diff = enrich_phase1(graph, "https://x/y", html_lang="en", canonical_link="https://x/y", last_modified_header="Tue, 03 Sep 2024 10:00:00 GMT", flags={"shadow": True, "inLanguage": True, "canonical": True, "dateModified": True})
    assert diff["shadow"] is True
    # graph remains unchanged in shadow
    wp = [n for n in g2["@graph"] if n.get("@type") == "WebPage"][0]
    assert "inLanguage" not in wp
    assert "dateModified" not in wp

def test_apply_language_and_date():
    graph = {"@context": "https://schema.org", "@graph": [{"@type": "WebPage", "url": "https://x/y"}]}
    g2, diff = enrich_phase1(graph, "https://x/y", html_lang="en-US", last_modified_header="Tue, 03 Sep 2024 10:00:00 GMT", flags={"shadow": False, "inLanguage": True, "canonical": False, "dateModified": True})
    wp = [n for n in g2["@graph"] if n.get("@type") == "WebPage"][0]
    assert wp["inLanguage"] == "en-US"
    assert wp["dateModified"] == "2024-09-03"

def test_canonical_same_host_only():
    graph = {"@context": "https://schema.org", "@graph": [{"@type": "WebPage", "url": "https://site/a"}]}
    # foreign canonical must not apply
    g2, diff = enrich_phase1(graph, "https://site/a", canonical_link="https://othersite/a", flags={"shadow": False, "inLanguage": False, "canonical": True, "dateModified": False})
    wp = [n for n in g2["@graph"] if n.get("@type") == "WebPage"][0]
    assert wp["url"] == "https://site/a"
    # same host canonical applies
    g3, diff2 = enrich_phase1(graph, "https://site/a", canonical_link="https://site/canonical", flags={"shadow": False, "inLanguage": False, "canonical": True, "dateModified": False})
    wp2 = [n for n in g3["@graph"] if n.get("@type") == "WebPage"][0]
    assert wp2["url"] == "https://site/canonical"