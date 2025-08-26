
# --- SNIP --- only the /result handler changed to wait for completion ---

from fastapi import FastAPI, Request, Form, UploadFile, File, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse, Response, JSONResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from starlette.datastructures import URL

import io, csv, json, sys, asyncio, uuid
import httpx
from datetime import datetime
from urllib.parse import urlparse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import init_db, get_session
from app.services.settings import get_settings, update_settings
from app.services.providers import list_ollama_models
from app.services.page_types import get_map, upsert_type, delete_type
from app.services.csv_ingest import parse_csv
from app.services.fetch import fetch_url
from app.services.extract import extract_clean_text
from app.services.ai import get_provider, GenerationInputs
from app.services.schemas import load_schema, defaults_for, AVAILABLE_PAGE_TYPES
from app.services.validate import validate_against_schema
from app.services.score import score_jsonld
from app.services.signals import extract_signals
from app.services.normalize import normalize_jsonld
from app.services.graph import assemble_graph
from app.services.history import record_run, list_runs, get_run as db_get_run
from app.services.progress import create_job, update_job, finish_job, get_job
from app.services.enhance import enhance_jsonld

app = FastAPI(title="Schema Gen", version="1.7.2")
templates = Jinja2Templates(directory="app/web/templates")

# ... all routes unchanged EXCEPT /result below ...

@app.get("/result/{job_id}", response_class=HTMLResponse)
async def result_page(request: Request, job_id: str, session: AsyncSession = Depends(get_session)):
    # Wait up to 25 seconds for the job to complete instead of bouncing home
    timeout_s, interval_s = 25, 0.5
    waited = 0.0
    job = await get_job(job_id)
    while job and not job.get("result") and (job.get("progress", 0) < 100) and waited < timeout_s:
        await asyncio.sleep(interval_s)
        waited += interval_s
        job = await get_job(job_id)

    if not job:
        # Unknown job id
        return templates.TemplateResponse("progress.html", {"request": request, "job_id": job_id, "error": "Unknown job. It may have expired."})

    if not job.get("result"):
        # Still not ready — show progress page instead of redirecting to home.
        return templates.TemplateResponse("progress.html", {"request": request, "job_id": job_id})

    result = job["result"]
    # Persist to history (best-effort)
    try:
        await record_run(session, result)
    except Exception as e:
        print(f"[history write failed] {e}", file=sys.stderr)

    return templates.TemplateResponse("result.html", {"request": request, **result})
