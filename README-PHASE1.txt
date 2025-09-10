
Phase 1 Enrichment Patch
========================
This patch adds safe, deterministic enrichments with feature flags + shadow mode.

Files:
- app/settings_models.py              (adds extract_config defaults)
- app/services/enrichment.py          (Phase-1 enrichers + shadow mode)
- app/services/settings.py            (supports extract_config get/update)
- app/web/templates/admin_settings.html (simple toggles UI)
- tests/test_enrichment_phase1.py     (unit tests)

Integration (minimal, no scraping):
1) After you assemble your JSON-LD graph (and BEFORE final sanitize), call:

   from app.services.enrichment import enrich_phase1
   from app.services.settings import get_settings

   # example (inside your request handler)
   s = await get_settings(session)
   flags = s.extract_config or {}
   # Provide optional hints if you have them (no scraping):
   html_lang = request_state.get("html_lang")         # e.g., 'en' or 'en-US'
   canonical = request_state.get("canonical_link")    # from <link rel="canonical">
   last_mod = request_state.get("last_modified")      # HTTP 'Last-Modified' header

   graph, diff = enrich_phase1(graph, url, html_lang=html_lang, canonical_link=canonical, last_modified_header=last_mod, flags=flags)
   # If flags['shadow'] is True, graph is unchanged but 'diff' lists proposed changes.

2) To enable writing changes, turn OFF shadow mode in Admin or set:
   settings.extract_config.shadow = false

Admin:
- Mount 'admin_settings.html' at /admin/settings and pass {'cfg': settings.extract_config} into the template.
- POST handler should parse toggles and call update_settings(..., extract_config=new_cfg).

Testing:
- Run `pytest -q` to verify unit tests.
