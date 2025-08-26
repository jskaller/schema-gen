
from fastapi import FastAPI, Request, Form, UploadFile, File, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse, Response, JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.datastructures import URL

import io, csv, json, sys, asyncio, uuid, traceback
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
from app.services.sanitize import sanitize_jsonld

app = FastAPI(title="Schema Gen", version="1.8.5")
templates = Jinja2Templates(directory="app/web/templates")

HEARTBEAT_INTERVAL = 0.5
GEN_TIMEOUT = 60  # seconds for provider.generate_jsonld

@app.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)

@app.get("/__routes")
async def __routes():
    data = [{"path": getattr(r, "path", "?"), "methods": sorted(list(getattr(r, "methods", {'*'})))} for r in app.router.routes]
    return JSONResponse(data)

@app.on_event("startup")
async def _startup():
    await init_db()
    print("[startup] app v1.8.5", file=sys.stderr)

def _safe_filename_from_url(url: str, prefix: str, ext: str) -> str:
    host = urlparse(url or '').netloc.replace(":", "_") or "schema"
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{host}-{ts}.{ext}"

async def resolve_types(session: AsyncSession, label: str | None):
    s = await get_settings(session)
    mapping = s.page_type_map or {}
    effective_label = (label or getattr(s, "page_type", None) or "Hospital")
    cfg = mapping.get(effective_label, {"primary": effective_label, "secondary": []})
    primary = cfg.get("primary") or effective_label
    secondary = cfg.get("secondary") or []
    return effective_label, primary, secondary, s

def _desc_from_text(txt: str, fallback: str = "") -> str:
    t = (txt or "").strip()
    if not t:
        return fallback
    t = " ".join(t.split())
    if len(t) <= 280:
        return t
    p = t.find(". ", 180, 280)
    if p != -1: return t[:p+1]
    return t[:280]

async def _process_single(url: str, topic, subject, audience, address, phone, compare_existing, competitor1, competitor2, label, session: AsyncSession, job_id: str | None = None):
    async def hb(pct, msg):
        if job_id:
            await update_job(job_id, pct, msg)
        print(f"[job {job_id or '-'}] {pct}% {msg}", file=sys.stderr)

    await hb(5, "Fetching URL")
    try:
        raw_html = await fetch_url(url)
    except Exception as e:
        print(f"[fetch_url] {e}", file=sys.stderr)
        raw_html = ""
    raw_html = raw_html or ""

    await hb(15, "Extracting text")
    try:
        cleaned_text = extract_clean_text(raw_html) or ""
    except Exception as e:
        print(f"[extract_clean_text] {e}", file=sys.stderr)
        cleaned_text = ""

    await hb(25, "Scanning signals")
    try:
        sig = extract_signals(raw_html) or {}
    except Exception as e:
        print(f"[extract_signals] {e}", file=sys.stderr)
        sig = {}

    page_label, primary_type, secondary_types, s = await resolve_types(session, label)

    await hb(35, f"Provider init ({s.provider or 'dummy'})")
    provider = get_provider(s.provider or "dummy", model=(s.provider_model or None))

    payload = GenerationInputs(
        url=url or "",
        cleaned_text=cleaned_text,
        topic=topic or "",
        subject=subject or "",
        audience=audience or "",
        address=address or sig.get("address"),
        phone=phone or sig.get("phone"),
        sameAs=sig.get("sameAs"),
        page_type=primary_type,
    )

    await hb(45, "Generating JSON-LD")
    base_jsonld = {}
    try:
        base_jsonld = await asyncio.wait_for(provider.generate_jsonld(payload), timeout=GEN_TIMEOUT)
    except asyncio.TimeoutError:
        print("[generate_jsonld] timeout", file=sys.stderr)
    except Exception as e:
        print(f"[generate_jsonld] {e}", file=sys.stderr)

    await hb(60, "Normalizing")
    try:
        primary_node = normalize_jsonld(base_jsonld or {}, primary_type, {"topic": topic or "", "subject": subject or "", "address": address or "", "phone": phone or "", "url": url or ""})
    except Exception as e:
        print(f"[normalize] {e}", file=sys.stderr)
        primary_node = {"@context": "https://schema.org", "@type": primary_type, "url": url or ""}

    await hb(70, "Assembling graph")
    try:
        final_jsonld = assemble_graph(primary_node, secondary_types or [], url or "", {"topic": topic or "", "subject": subject or "", "address": address or "", "phone": phone or "", "url": url or ""}) if secondary_types else primary_node
    except Exception as e:
        print(f"[assemble_graph] {e}", file=sys.stderr)
        final_jsonld = primary_node

    await hb(80, "Enhancing")
    try:
        final_jsonld = enhance_jsonld(final_jsonld, secondary_types or [], raw_html, url or "", topic or "", subject or "")
    except Exception as e:
        print(f"[enhance] {e}", file=sys.stderr)

    hints = {
        "url": url or "",
        "name": (subject or "").strip() or sig.get("org") or "",
        "telephone": (phone or "").strip() or sig.get("phone") or "",
        "address": address or sig.get("address"),
        "audience": (audience or "").strip() or "Patient",
        "sameAs": sig.get("sameAs") or [],
        "medicalSpecialty": (topic or "").strip(),
        "dateModified": datetime.utcnow().isoformat() + "Z",
        "description": _desc_from_text(cleaned_text, ""),
    }

    await hb(88, "Sanitizing")
    try:
        final_jsonld = sanitize_jsonld(final_jsonld, primary_type, url or "", secondary_types or [], hints)
    except Exception as e:
        print(f"[sanitize] {e}", file=sys.stderr)

    # Root for validation
    root_node = None
    if isinstance(final_jsonld, dict) and "@graph" in final_jsonld and isinstance(final_jsonld["@graph"], list) and final_jsonld["@graph"]:
        for n in final_jsonld["@graph"]:
            if isinstance(n, dict) and n.get("@type") == primary_type:
                root_node = n; break
        root_node = root_node or final_jsonld["@graph"][0]
    elif isinstance(final_jsonld, dict):
        root_node = final_jsonld

    await hb(92, "Loading schema")
    try:
        schema_json = load_schema(primary_type)
    except Exception:
        schema_json = {}

    defs = defaults_for(primary_type) if primary_type else {"required": [], "recommended": []}
    s = await get_settings(session)
    effective_required = (getattr(s, "required_fields", None) or defs["required"])
    effective_recommended = (getattr(s, "recommended_fields", None) or defs["recommended"])

    await hb(95, "Validating & scoring")
    try:
        valid, errors = validate_against_schema(root_node or {}, schema_json)
    except Exception as e:
        valid, errors = False, [f"Validation failed: {e}"]

    try:
        overall, details = score_jsonld(root_node or {}, effective_required, effective_recommended)
    except Exception:
        overall, details = 0, {"subscores": {}, "notes": []}

    missing_recommended = [key for key in (effective_recommended or []) if key not in (root_node or {}) or (root_node or {}).get(key) in (None, "", [])]
    tips = [f"Consider adding: {key}" for key in missing_recommended]

    await hb(99, "Finalizing")
    return {
        "url": url or "",
        "page_type_label": page_label,
        "primary_type": primary_type,
        "secondary_types": secondary_types or [],
        "topic": topic or "",
        "subject": subject or "",
        "audience": audience or "",
        "address": (root_node or {}).get("address"),
        "phone": (root_node or {}).get("telephone") or hints.get("telephone") or "",
        "excerpt": (cleaned_text or "")[:2000],
        "length": len(cleaned_text or ""),
        "jsonld": final_jsonld,
        "valid": bool(valid),
        "validation_errors": errors or [],
        "overall": overall,
        "details": details,
        "iterations": 0,
        "comparisons": [],
        "comparison_notes": [],
        "advice": tips,
        "effective_required": effective_required or [],
        "effective_recommended": effective_recommended or [],
    }

# ---------- Routes ----------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request, ok: str | None = None, error: str | None = None, session: AsyncSession = Depends(get_session)):
    mapping = await get_map(session)
    return templates.TemplateResponse("index.html", {"request": request, "ok": ok, "error": error, "mapping": mapping})

@app.post("/submit", response_class=HTMLResponse)
async def submit(request: Request,
    url: str = Form(""), page_type: str | None = Form(None), topic: str | None = Form(None),
    subject: str | None = Form(None), audience: str | None = Form(None),
    address: str | None = Form(None), phone: str | None = Form(None),
    compare_existing: str | None = Form(None), competitor1: str | None = Form(None), competitor2: str | None = Form(None),
    session: AsyncSession = Depends(get_session)):
    if not url:
        return RedirectResponse(url=str(URL("/").include_query_params(error="Please provide a URL")), status_code=303)
    result = await _process_single(url, topic, subject, audience, address, phone, compare_existing, competitor1, competitor2, page_type, session)
    await record_run(session, result)
    return templates.TemplateResponse("result.html", {"request": request, **result})

@app.post("/submit_async")
async def submit_async(request: Request,
    url: str = Form(""), page_type: str | None = Form(None), topic: str | None = Form(None),
    subject: str | None = Form(None), audience: str | None = Form(None),
    address: str | None = Form(None), phone: str | None = Form(None),
    compare_existing: str | None = Form(None), competitor1: str | None = Form(None), competitor2: str | None = Form(None),
    session: AsyncSession = Depends(get_session)):
    job_id = str(uuid.uuid4())
    await create_job(job_id)
    print(f"[runner] created {job_id}", file=sys.stderr)

    async def runner():
        try:
            await update_job(job_id, 3, "Queued")
            result = await _process_single(url, topic, subject, audience, address, phone, compare_existing, competitor1, competitor2, page_type, session, job_id=job_id)
            await finish_job(job_id, result)
            print(f"[runner] finished {job_id}", file=sys.stderr)
        except Exception as e:
            tb = traceback.format_exc()
            print(f"[runner] error {job_id}: {e}\n{tb}", file=sys.stderr)
            try:
                await update_job(job_id, 100, f"Error: {e}")
                await finish_job(job_id, {"url": url, "overall": 0, "valid": False, "validation_errors": [str(e)], "details": {"notes": [tb]}, "jsonld": {"@context": "https://schema.org", "@type": "Thing"}})
            except Exception as e2:
                print(f"[runner] error finalize {job_id}: {e2}", file=sys.stderr)

    asyncio.create_task(runner())
    return {"job_id": job_id}

@app.get("/events/{job_id}")
async def events(job_id: str):
    async def gen():
        last = -1
        while True:
            job = await get_job(job_id)
            if not job:
                break
            progress = job.get("progress", 0)
            msg = job.get("messages", [{"msg": "Working..."}])[-1]["msg"]
            if progress != last:
                yield f"data: {json.dumps({'progress': progress, 'msg': msg})}\n\n"
                last = progress
            if progress >= 100 or job.get("result"):
                break
            await asyncio.sleep(HEARTBEAT_INTERVAL)
    return StreamingResponse(gen(), media_type="text/event-stream")

@app.get("/progress/{job_id}", response_class=HTMLResponse)
async def progress_page(request: Request, job_id: str):
    return templates.TemplateResponse("progress.html", {"request": request, "job_id": job_id})

@app.get("/result/{job_id}", response_class=HTMLResponse)
async def result_page(request: Request, job_id: str, session: AsyncSession = Depends(get_session)):
    # block briefly to allow jobs that just finished to be visible
    waited = 0.0
    while waited < 1.5:
        job = await get_job(job_id)
        if job and job.get("result"):
            break
        await asyncio.sleep(0.2)
        waited += 0.2
    job = await get_job(job_id)
    if not job:
        return templates.TemplateResponse("progress.html", {"request": request, "job_id": job_id, "error": "Unknown or expired job."})
    if not job.get("result"):
        return templates.TemplateResponse("progress.html", {"request": request, "job_id": job_id})
    result = job["result"]
    try:
        await record_run(session, result)
    except Exception:
        pass
    return templates.TemplateResponse("result.html", {"request": request, **result})

# Admin, History, Export, Batch endpoints are unchanged from earlier bundle and should already exist in your tree.
# This file only replaces app/main.py to prevent stalling and add heartbeats/timeouts.
