
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
from app.models import Run
from app.settings_models import Settings, SQLModel
from app.services.settings import get_settings, update_settings
from app.services.history import record_run, list_runs, get_run as db_get_run
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

from pathlib import Path
hospital_schema = Path("app/schemas/hospital.schema.json").read_text()

app = FastAPI(title="Schema Gen", version="1.0.0")
templates = Jinja2Templates(directory="app/web/templates")

@app.on_event("startup")
async def _startup():
    await init_db()

def _safe_filename_from_url(url: str, prefix: str, ext: str) -> str:
    host = urlparse(url).netloc.replace(":", "_") or "schema"
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{host}-{ts}.{ext}"

async def _process_single(url: str, topic, subject, audience, address, phone, compare_existing, competitor1, competitor2, session: AsyncSession):
    raw_html = await fetch_url(url)
    cleaned_text = extract_clean_text(raw_html)
    sig = extract_signals(raw_html)

    # Load settings
    s = await get_settings(session)
    provider = get_provider(s.provider or "dummy")

    payload = GenerationInputs(
        url=url,
        cleaned_text=cleaned_text,
        topic=topic,
        subject=subject,
        audience=audience,
        address=address or sig.get("address"),
        phone=phone or sig.get("phone"),
        sameAs=sig.get("sameAs"),
        page_type=s.page_type or "Hospital",
    )
    jsonld = provider.generate_jsonld(payload)

    # Validate/Score using settings-driven fields
    valid, errors = validate_against_schema(jsonld, hospital_schema)
    required = s.required_fields or ["@context","@type","name","url"]
    recommended = s.recommended_fields or ["description","telephone","address","audience","dateModified","sameAs","medicalSpecialty"]
    overall, details = score_jsonld(jsonld, required, recommended)

    final_jsonld, final_score, final_details, iterations = refine_to_perfect(
        base_jsonld=jsonld,
        cleaned_text=cleaned_text,
        required=required,
        recommended=recommended,
        score_fn=score_jsonld,
        max_attempts=3,
    )
    final_valid, final_errors = validate_against_schema(final_jsonld, hospital_schema)

    comparisons = []
    notes = []
    if compare_existing:
        onpage = extract_onpage_jsonld(raw_html)
        primary = pick_primary_by_type(onpage, s.page_type or "Hospital") if onpage else None
        if primary:
            comparisons.append(summarize_scores("On‑page JSON‑LD", primary, score_jsonld, required, recommended))
        else:
            notes.append("No on‑page JSON‑LD suitable for page type found.")
    for label, comp_url in (("Competitor #1", competitor1), ("Competitor #2", competitor2)):
        if comp_url:
            try:
                comp_html = await fetch_url(comp_url)
                comp_items = extract_onpage_jsonld(comp_html)
                comp_primary = pick_primary_by_type(comp_items, s.page_type or "Hospital")
                if comp_primary:
                    comparisons.append(summarize_scores(f"{label}", comp_primary, score_jsonld, required, recommended))
                else:
                    notes.append(f"{label}: no suitable JSON‑LD found.")
            except Exception as ce:
                notes.append(f"{label}: fetch error – {ce}")

    return {
        "url": url,
        "topic": topic,
        "subject": subject,
        "audience": audience,
        "address": address or sig.get("address"),
        "phone": phone or sig.get("phone"),
        "excerpt": cleaned_text[:2000],
        "length": len(cleaned_text),
        "jsonld": final_jsonld,
        "valid": final_valid,
        "validation_errors": final_errors,
        "overall": final_score,
        "details": final_details,
        "iterations": iterations,
        "comparisons": comparisons,
        "comparison_notes": notes,
    }

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, ok: str | None = None, error: str | None = None):
    return templates.TemplateResponse("index.html", {"request": request, "ok": ok, "error": error})

@app.get("/admin", response_class=HTMLResponse)
async def admin_get(request: Request, session: AsyncSession = Depends(get_session), ok: str | None = None):
    s = await get_settings(session)
    return templates.TemplateResponse("admin.html", {"request": request, "settings": s, "ok": ok})

@app.post("/admin", response_class=HTMLResponse)
async def admin_post(
    request: Request,
    provider: str = Form("dummy"),
    page_type: str = Form("Hospital"),
    required_fields: str = Form(""),
    recommended_fields: str = Form(""),
    session: AsyncSession = Depends(get_session),
):
    try:
        req = json.loads(required_fields) if required_fields.strip() else None
        rec = json.loads(recommended_fields) if recommended_fields.strip() else None
    except Exception as e:
        s = await get_settings(session)
        return templates.TemplateResponse("admin.html", {"request": request, "settings": s, "ok": None, "error": f"Invalid JSON lists: {e}"})
    s = await update_settings(session, provider, page_type, req, rec)
    return RedirectResponse(url="/admin?ok=1", status_code=303)

@app.post("/submit", response_class=HTMLResponse)
async def submit(
    request: Request,
    url: str = Form(""),
    topic: str | None = Form(None),
    subject: str | None = Form(None),
    audience: str | None = Form(None),
    address: str | None = Form(None),
    phone: str | None = Form(None),
    compare_existing: str | None = Form(None),
    competitor1: str | None = Form(None),
    competitor2: str | None = Form(None),
    session: AsyncSession = Depends(get_session),
):
    try:
        if not url:
            return RedirectResponse(url=str(URL("/").include_query_params(error="Please provide a URL")), status_code=303)
        result = await _process_single(url, topic, subject, audience, address, phone, compare_existing, competitor1, competitor2, session)

        # Persist run
        await record_run(session, result)

        return templates.TemplateResponse("result.html", {"request": request, **result})
    except Exception as e:
        return RedirectResponse(url=str(URL("/").include_query_params(error=str(e))), status_code=303)

# History
@app.get("/history", response_class=HTMLResponse)
async def history_list(request: Request, q: str | None = None, session: AsyncSession = Depends(get_session)):
    rows = await list_runs(session, q=q or None, limit=200)
    return templates.TemplateResponse("history_list.html", {"request": request, "rows": rows, "q": q})

@app.get("/history/{run_id}", response_class=HTMLResponse)
async def history_detail(request: Request, run_id: int, session: AsyncSession = Depends(get_session)):
    run = await db_get_run(session, run_id)
    if not run:
        return RedirectResponse(url="/history", status_code=303)
    return templates.TemplateResponse("history_detail.html", {"request": request, "run": run})
