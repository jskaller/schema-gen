
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

# DB & models
from app.db import init_db, get_session
from app.models import Run
from app.services.history import record_run, list_runs, get_run as db_get_run

# Settings
from app.services.settings import get_settings, update_settings

# Core services
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

hospital_schema = Path("app/schemas/hospital.schema.json").read_text()

app = FastAPI(title="Schema Gen", version="1.1.0")
templates = Jinja2Templates(directory="app/web/templates")

@app.on_event("startup")
async def _startup():
    await init_db()

def _safe_filename_from_url(url: str, prefix: str, ext: str) -> str:
    host = urlparse(url).netloc.replace(":", "_") or "schema"
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{host}-{ts}.{ext}"

async def _process_single(
    url: str,
    topic: str | None,
    subject: str | None,
    audience: str | None,
    address: str | None,
    phone: str | None,
    compare_existing: str | None,
    competitor1: str | None,
    competitor2: str | None,
    session: AsyncSession,
):
    raw_html = await fetch_url(url)
    cleaned_text = extract_clean_text(raw_html)
    sig = extract_signals(raw_html)

    # Load runtime settings (provider, page_type, field lists)
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

    # Validate & score
    required = (s.required_fields or ["@context","@type","name","url"])
    recommended = (s.recommended_fields or ["description","telephone","address","audience","dateModified","sameAs","medicalSpecialty"])
    valid, errors = validate_against_schema(jsonld, hospital_schema)
    overall, details = score_jsonld(jsonld, required, recommended)

    # Refine
    final_jsonld, final_score, final_details, iterations = refine_to_perfect(
        base_jsonld=jsonld,
        cleaned_text=cleaned_text,
        required=required,
        recommended=recommended,
        score_fn=score_jsonld,
        max_attempts=3,
    )
    final_valid, final_errors = validate_against_schema(final_jsonld, hospital_schema)

    # Comparisons
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

# -------------------- Core pages --------------------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request, ok: str | None = None, error: str | None = None):
    return templates.TemplateResponse("index.html", {"request": request, "ok": ok, "error": error})

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
        await record_run(session, result)
        return templates.TemplateResponse("result.html", {"request": request, **result})
    except Exception as e:
        return RedirectResponse(url=str(URL("/").include_query_params(error=str(e))), status_code=303)

# -------------------- Admin / Settings --------------------
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
    await update_settings(session, provider, page_type, req, rec)
    return RedirectResponse(url="/admin?ok=1", status_code=303)

# -------------------- History --------------------
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

# -------------------- Export (single) --------------------
@app.post("/export/jsonld")
async def export_jsonld(jsonld: str = Form(...), url: str = Form(...)):
    data = json.loads(jsonld)
    filename = _safe_filename_from_url(url, "schema", "json")
    payload = json.dumps(data, indent=2)
    return Response(content=payload, media_type="application/ld+json", headers={"Content-Disposition": f'attachment; filename="{filename}"'})

@app.post("/export/csv")
async def export_csv(jsonld: str = Form(...), url: str = Form(...), score: str = Form("")):
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["url", "score", "jsonld"])
    writer.writerow([url, score, jsonld])
    out.seek(0)
    filename = _safe_filename_from_url(url, "schema-single", "csv")
    return StreamingResponse(out, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{filename}"'})

# -------------------- Batch ingest (upload/Sheets) + Preview --------------------
async def _process_row(row: dict[str, str], session: AsyncSession) -> dict:
    result = await _process_single(
        url=(row.get("url") or "").strip(),
        topic=row.get("topic") or None,
        subject=row.get("subject") or None,
        audience=row.get("audience") or None,
        address=row.get("address") or None,
        phone=row.get("phone") or None,
        compare_existing=row.get("compare_existing") or None,
        competitor1=row.get("competitor1") or None,
        competitor2=row.get("competitor2") or None,
        session=session,
    )
    return {
        "url": result["url"],
        "overall": result["overall"],
        "valid": result["valid"],
        "validation_errors": result["validation_errors"],
        "jsonld": result["jsonld"],
        "comparisons": result["comparisons"],
        "comparison_notes": result["comparison_notes"],
        "excerpt": result["excerpt"],
    }

def _csv_from_items(items: list[dict]) -> io.StringIO:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["url", "score", "valid", "jsonld"])
    for it in items:
        writer.writerow([it["url"], it["overall"], "yes" if it["valid"] else "no", json.dumps(it["jsonld"])])
    out.seek(0)
    return out

@app.get("/batch", response_class=HTMLResponse)
async def batch_page(request: Request, error: str | None = None, warnings: list[str] | None = None):
    return templates.TemplateResponse("batch.html", {"request": request, "error": error, "warnings": warnings or []})

@app.post("/batch/upload")
async def batch_upload(file: UploadFile = File(...), session: AsyncSession = Depends(get_session)):
    text = (await file.read()).decode("utf-8", errors="ignore")
    rows, warnings = parse_csv(text)
    if not rows:
        return RedirectResponse(str(URL("/batch").include_query_params(error="No data rows found", warnings=warnings)), status_code=303)
    processed: list[dict[str, str]] = []
    for row in rows:
        try:
            r = await _process_row(row, session)
            processed.append({"url": r["url"], "score": r["overall"], "valid": "yes" if r["valid"] else "no", "jsonld": json.dumps(r["jsonld"])})
        except Exception as e:
            processed.append({"url": row.get("url",""), "score": "", "valid": "error", "jsonld": str(e)})
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=["url", "score", "valid", "jsonld"])
    writer.writeheader()
    for row in processed:
        writer.writerow(row)
    out.seek(0)
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    return StreamingResponse(out, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="schema-batch-%s.csv"' % ts})

@app.post("/batch/fetch")
async def batch_fetch(csv_url: str = Form(...), session: AsyncSession = Depends(get_session)):
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            r = await client.get(csv_url)
            r.raise_for_status()
            content = r.text
    except Exception as e:
        return RedirectResponse(str(URL("/batch").include_query_params(error=str(e))), status_code=303)
    rows, warnings = parse_csv(content)
    if not rows:
        return RedirectResponse(str(URL("/batch").include_query_params(error="No data rows found", warnings=warnings)), status_code=303)
    processed: list[dict[str, str]] = []
    for row in rows:
        try:
            r = await _process_row(row, session)
            processed.append({"url": r["url"], "score": r["overall"], "valid": "yes" if r["valid"] else "no", "jsonld": json.dumps(r["jsonld"])})
        except Exception as e:
            processed.append({"url": row.get("url",""), "score": "", "valid": "error", "jsonld": str(e)})
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=["url", "score", "valid", "jsonld"])
    writer.writeheader()
    for row in processed:
        writer.writerow(row)
    out.seek(0)
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    return StreamingResponse(out, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="schema-batch-%s.csv"' % ts})

@app.post("/batch/preview_upload", response_class=HTMLResponse)
async def batch_preview_upload(request: Request, file: UploadFile = File(...), session: AsyncSession = Depends(get_session)):
    text = (await file.read()).decode("utf-8", errors="ignore")
    rows, warnings = parse_csv(text)
    if not rows:
        return RedirectResponse(str(URL("/batch").include_query_params(error="No data rows found", warnings=warnings)), status_code=303)
    items = []
    for row in rows:
        try:
            items.append(await _process_row(row, session))
        except Exception as e:
            items.append({"url": row.get("url",""), "overall": "", "valid": False, "validation_errors": [str(e)], "jsonld": {}, "comparisons": [], "comparison_notes": [], "excerpt": ""})
    return templates.TemplateResponse("batch_preview.html", {"request": request, "items": items})

@app.post("/batch/preview_fetch", response_class=HTMLResponse)
async def batch_preview_fetch(request: Request, csv_url: str = Form(...), session: AsyncSession = Depends(get_session)):
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            r = await client.get(csv_url)
            r.raise_for_status()
            content = r.text
    except Exception as e:
        return RedirectResponse(str(URL("/batch").include_query_params(error=str(e))), status_code=303)
    rows, warnings = parse_csv(content)
    if not rows:
        return RedirectResponse(str(URL("/batch").include_query_params(error="No data rows found", warnings=warnings)), status_code=303)
    items = []
    for row in rows:
        try:
            items.append(await _process_row(row, session))
        except Exception as e:
            items.append({"url": row.get("url",""), "overall": "", "valid": False, "validation_errors": [str(e)], "jsonld": {}, "comparisons": [], "comparison_notes": [], "excerpt": ""})
    return templates.TemplateResponse("batch_preview.html", {"request": request, "items": items})

@app.post("/batch/export_from_preview")
async def batch_export_from_preview(rows_json: str = Form(...)):
    items = json.loads(rows_json)
    out = _csv_from_items(items)
    filename = f"schema-batch-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.csv"
    return StreamingResponse(out, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{filename}"'})
