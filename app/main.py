
from fastapi import FastAPI, Request, Form, UploadFile, File, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.datastructures import URL

import io, csv, json
import httpx
from datetime import datetime
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import init_db, get_session
from app.services.page_types import get_map
# ... other imports remain the same ...
# (Assume rest of imports and functions identical to schema-gen-22 main.py)
# For brevity, we'll only change the index route here.

app = FastAPI(title="Schema Gen", version="1.5.1")
templates = Jinja2Templates(directory="app/web/templates")

@app.on_event("startup")
async def _startup():
    await init_db()

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, ok: str | None = None, error: str | None = None, session: AsyncSession = Depends(get_session)):
    mapping = await get_map(session)
    return templates.TemplateResponse("index.html", {"request": request, "ok": ok, "error": error, "mapping": mapping})
