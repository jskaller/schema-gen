
from fastapi import FastAPI, Request, Form, UploadFile, File, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.datastructures import URL

import io, csv, json
import httpx
from datetime import datetime
from urllib.parse import urlparse
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import init_db, get_session
from app.services.history import record_run
from app.services.settings import get_settings
from app.services.providers import list_ollama_models
from app.services.csv_ingest import parse_csv
from app.services.fetch import fetch_url
from app.services.extract import extract_clean_text
from app.services.ai import get_provider, GenerationInputs
from app.services.validate import validate_against_schema
from app.services.score import score_jsonld
from app.services.signals import extract_signals
from app.services.refine import refine_to_perfect
from app.services.jsonld_extract import extract_onpage_jsonld
from app.services.compare import summarize_scores, pick_primary_by_type
from app.services.schemas import load_schema, defaults_for
from app.services.advice import advise
from app.services.normalize import normalize_jsonld
from app.services.friendly_errors import to_friendly_messages

app = FastAPI(title="Schema Gen", version="1.5.0")
templates = Jinja2Templates(directory="app/web/templates")

@app.on_event("startup")
async def _startup():
    await init_db()

def _safe_filename_from_url(url: str, prefix: str, ext: str) -> str:
    host = urlparse(url).netloc.replace(":", "_") or "schema"
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{host}-{ts}.{ext}"

async def _process_single(url, topic, subject, audience, address, phone, compare_existing, competitor1, competitor2, page_type_label, session: AsyncSession):
    # Resolve effective primary type from settings mapping
    s = await get_settings(session)
    mapping = s.page_type_map or {}
    label = page_type_label or s.page_type or "Hospital"
    cfg = mapping.get(label, {"primary": label, "secondary": []})
    primary_type = cfg.get("primary") or label

    raw_html = await fetch_url(url)
    cleaned_text = extract_clean_text(raw_html)
    sig = extract_signals(raw_html)

    provider = get_provider(s.provider or "dummy", model=s.provider_model or None)
    payload = GenerationInputs(
        url=url, cleaned_text=cleaned_text, topic=topic, subject=subject, audience=audience,
        address=address or sig.get("address"), phone=phone or sig.get("phone"),
        page_type=primary_type, sameAs=sig.get("sameAs"),
    )
    base_jsonld = await provider.generate_jsonld(payload)

    # Normalize before validation
    jsonld = normalize_jsonld(base_jsonld, primary_type=primary_type, fallback_phone=payload.phone, fallback_address=payload.address)

    # Effective requirements
    defs = defaults_for(primary_type)
    required = s.required_fields or defs["required"]
    recommended = s.recommended_fields or defs["recommended"]

    schema_text = load_schema(primary_type)
    valid, errors = validate_against_schema(jsonld, schema_text)
    overall, details = score_jsonld(jsonld, required, recommended)

    final_jsonld, final_score, final_details, iterations = refine_to_perfect(
        base_jsonld=jsonld, cleaned_text=cleaned_text, required=required, recommended=recommended, score_fn=score_jsonld, max_attempts=3
    )
    final_valid, final_errors = validate_against_schema(final_jsonld, schema_text)

    # Friendly messages
    friendly = to_friendly_messages(final_errors if not final_valid else [], primary_type)

    result = {
        "url": url,
        "primary_type": primary_type,
        "jsonld": final_jsonld,
        "valid": final_valid,
        "validation_errors": final_errors,
        "overall": final_score,
        "details": final_details,
        "effective_required": required,
        "effective_recommended": recommended,
        "friendly_errors": friendly,
    }
    return result

# Root + submit minimal to demonstrate fixes
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/submit", response_class=HTMLResponse)
async def submit(
    request: Request,
    url: str = Form(""),
    topic: str | None = Form(None),
    subject: str | None = Form(None),
    audience: str | None = Form(None),
    address: str | None = Form(None),
    phone: str | None = Form(None),
    page_type: str | None = Form(None),
    compare_existing: str | None = Form(None),
    competitor1: str | None = Form(None),
    competitor2: str | None = Form(None),
    session: AsyncSession = Depends(get_session),
):
    if not url:
        return RedirectResponse(url=str(URL("/").include_query_params(error="Please provide a URL")), status_code=303)
    result = await _process_single(url, topic, subject, audience, address, phone, compare_existing, competitor1, competitor2, page_type, session)
    await record_run(session, result)
    return templates.TemplateResponse("result.html", {"request": request, **result})

# Exports (left out here for brevity in this demo file)
