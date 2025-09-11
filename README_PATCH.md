
# README_PATCH (Consolidated Admin Boot Fix)

This patch makes server startup robust by:
- Ensuring Python packages are recognized (`app/`, `app/web/`, `app/web/routers/` get `__init__.py`).
- Replacing `app/main.py` with a **dynamic router loader** that imports any `admin_*.py` routers found under `app/web/routers/` and includes them under `/admin`.
- Including compat redirects if `compat_redirects.py` exists.
- Rendering `admin.html` from `app/web/templates` at `/` (with a graceful fallback if the template is missing).

## Apply
```bash
unzip -o patch_final_fix.zip -d .
```

## Run
```bash
uvicorn app.main:app --reload --port 8001
```

You should see a stderr log like:
```
[INFO] Loaded routers: ['app.web.routers.admin_page', 'app.web.routers.admin_settings', ...]
```

Then visit:
- http://127.0.0.1:8001/admin (served by the `admin_page` router)
- http://127.0.0.1:8001/ (renders the same admin template)
- /admin/models, /admin/save, /admin/test, /admin/extract should all be wired if their router files exist.

## Notes
- This avoids fragile `from app.web.routers import X` imports and circular init issues.
- If a router is missing locally (e.g., `admin_page.py` was deleted), the app still boots; the log will warn about the missing module.
