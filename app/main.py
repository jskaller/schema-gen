
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.responses import HTMLResponse

from app.db import get_session, init_db
from app.services.settings import get_settings

APP_NAME = "schema-gen"
app = FastAPI(title=f"{APP_NAME} API")

TEMPLATES_DIR = "app/web/templates"
templates = Jinja2Templates(directory=TEMPLATES_DIR)

STATIC_DIR = "app/web/static"
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

def _try(modname: str) -> Optional[object]:
    try:
        return importlib.import_module(modname)
    except Exception as e:
        return None

def _include_admin_router(primary: str, fallback: str) -> Optional[str]:
    mod = _try(primary) or _try(fallback)
    if mod and getattr(mod, "router", None):
        app.include_router(mod.router, prefix="/admin")
        return mod.__name__
    return None

def _include_page_router(primary: str, fallback: str, prefix: str = "") -> Optional[str]:
    mod = _try(primary) or _try(fallback)
    if mod and getattr(mod, "router", None):
        app.include_router(mod.router, prefix=prefix)
        return mod.__name__
    return None

loaded = []

# Prefer ORIGINAL admin routers; fallback only if missing
for primary, fallback in [
    ("app.web.routers.admin_page",     "app.web.routers._fallback_admin_page"),
    ("app.web.routers.admin_models",   "app.web.routers._fallback_admin_models"),
    ("app.web.routers.admin_settings", "app.web.routers._fallback_admin_settings"),
    ("app.web.routers.admin_test",     "app.web.routers._fallback_admin_test"),
    ("app.web.routers.admin_extract",  "app.web.routers._fallback_admin_extract"),
    ("app.web.routers.admin_types",    "app.web.routers._fallback_admin_types"),
]:
    name = _include_admin_router(primary, fallback)
    if name:
        loaded.append(name)

# IMPORTANT: mount REAL /batch and /history pages (NO redirects)
for primary, fallback in [
    ("app.web.routers.batch",   "app.web.routers._fallback_batch"),
    ("app.web.routers.history", "app.web.routers._fallback_history"),
]:
    name = _include_page_router(primary, fallback, prefix="")
    if name:
        loaded.append(name)

# DO NOT include compat_redirects at all (avoids 307s)

print(f"[INFO] Mounted routers: {loaded}", file=sys.stderr)

@app.on_event("startup")
async def startup_event():
    await init_db()

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, session=Depends(get_session)):
    settings = await get_settings(session)
    tpl = "admin.html"
    path = Path(TEMPLATES_DIR) / tpl
    if path.exists():
        return templates.TemplateResponse(tpl, {"request": request, "settings": settings})
    return HTMLResponse("<h3>Schema Gen</h3><p>Admin template not found. Ensure app/web/templates/admin.html exists.</p>")
