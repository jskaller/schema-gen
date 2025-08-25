
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
from app.services.history import record_run, list_runs, get_run as db_get_run
from app.services.settings import get_settings, update_settings
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
from app.services.schemas import load_schema, defaults_for, COMMON_PRIMARY_TYPES, COMMON_SECONDARY_TYPES
from app.services.advice import advise
from app.services.page_types import get_map, upsert_type, delete_type
from app.services.secondary_validate import validate_secondary

app = FastAPI(title="Schema Gen", version="1.5.0")
templates = Jinja2Templates(directory="app/web/templates")

@app.on_event("startup")
async def _startup():
    await init_db()

def _safe_filename_from_url(url: str, prefix: str, ext: str) -> str:
    host = urlparse(url).netloc.replace(":", "_") or "schema"
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{host}-{ts}.{ext}"

async def resolve_types(session: AsyncSession, label: str | None):
    s = await get_settings(session)
    mapping = s.page_type_map or {}
    effective_label = (label or s.page_type or "Hospital")
    cfg = mapping.get(effective_label, {"primary": effective_label, "secondary": []})
    primary = cfg.get("primary") or effective_label
    secondary = cfg.get("secondary") or []
    return effective_label, primary, secondary, s

async def _process_single(url, topic, subject, audience, address, phone, compare_existing, competitor1, competitor2, label, session: AsyncSession):
    raw_html = await fetch_url(url)
    cleaned_text = extract_clean_text(raw_html)
    sig = extract_signals(raw_html)

    label, primary_type, secondary_types, s = await resolve_types(session, label)
    provider = get_provider(s.provider or "dummy", model=s.provider_model or None)

    payload = GenerationInputs(
        url=url, cleaned_text=cleaned_text, topic=topic, subject=subject, audience=audience,
        address=address or sig.get("address"), phone=phone or sig.get("phone"), sameAs=sig.get("sameAs"),
        page_type=primary_type,
    )
    jsonld = await provider.generate_jsonld(payload)

    schema_json = load_schema(primary_type)
    effective_required = (s.required_fields or defaults_for(primary_type)["required"])
    effective_recommended = (s.recommended_fields or defaults_for(primary_type)["recommended"])

    valid, errors = validate_against_schema(jsonld, schema_json)
    overall, details = score_jsonld(jsonld, effective_required, effective_recommended)
    tips = advise(jsonld, effective_required, effective_recommended)

    final_jsonld, final_score, final_details, iterations = refine_to_perfect(
        base_jsonld=jsonld, cleaned_text=cleaned_text, required=effective_required, recommended=effective_recommended, score_fn=score_jsonld, max_attempts=3
    )
    final_valid, final_errors = validate_against_schema(final_jsonld, schema_json)
    final_tips = advise(final_jsonld, effective_required, effective_recommended)
    secondary_issues = validate_secondary(final_jsonld, secondary_types)

    comparisons, notes = [], []
    if compare_existing:
        onpage = extract_onpage_jsonld(raw_html)
        primary = pick_primary_by_type(onpage, primary_type) if onpage else None
        if primary:
            comparisons.append(summarize_scores("On‑page JSON‑LD", primary, score_jsonld, effective_required, effective_recommended))
        else:
            notes.append("No on‑page JSON‑LD suitable for page type found.")
    for labelc, comp_url in (("Competitor #1", competitor1), ("Competitor #2", competitor2)):
        if comp_url:
            try:
                comp_html = await fetch_url(comp_url)
                comp_items = extract_onpage_jsonld(comp_html)
                comp_primary = pick_primary_by_type(comp_items, primary_type)
                if comp_primary:
                    comparisons.append(summarize_scores(f"{labelc}", comp_primary, score_jsonld, effective_required, effective_recommended))
                else:
                    notes.append(f"{labelc}: no suitable JSON‑LD found.")
            except Exception as ce:
                notes.append(f"{labelc}: fetch error – {ce}")

    return {
        "url": url, "page_type_label": label, "primary_type": primary_type, "secondary_types": secondary_types,
        "topic": topic, "subject": subject, "audience": audience,
        "address": address or sig.get("address"), "phone": phone or sig.get("phone"),
        "excerpt": cleaned_text[:2000], "length": len(cleaned_text),
        "jsonld": final_jsonld, "valid": final_valid, "validation_errors": final_errors,
        "overall": final_score, "details": final_details, "iterations": iterations,
        "comparisons": comparisons, "comparison_notes": notes,
        "advice": final_tips, "secondary_issues": secondary_issues,
        "effective_required": effective_required, "effective_recommended": effective_recommended,
    }

# ---------- Admin (link already in template) & Page Types ----------
@app.get("/admin/types", response_class=HTMLResponse)
async def admin_types(request: Request, session: AsyncSession = Depends(get_session)):
    mapping = await get_map(session)
    return templates.TemplateResponse("admin_types.html", {"request": request, "mapping": mapping, "common_primary": COMMON_PRIMARY_TYPES, "common_secondary": COMMON_SECONDARY_TYPES})

@app.post("/admin/types/upsert", response_class=HTMLResponse)
async def admin_types_upsert(
    request: Request,
    label: str = Form(...),
    primary: str = Form(...),
    primary_custom: str = Form(""),
    secondary_select: list[str] = Form([]),
    secondary_custom: str = Form(""),
    session: AsyncSession = Depends(get_session),
):
    primary_type = primary_custom.strip() or primary
    custom_secs = [s.strip() for s in secondary_custom.split(",") if s.strip()]
    secondaries = list(dict.fromkeys(list(secondary_select) + custom_secs))  # dedupe, keep order
    await upsert_type(session, label, primary_type, secondaries)
    return RedirectResponse(url="/admin/types", status_code=303)

@app.post("/admin/types/delete", response_class=HTMLResponse)
async def admin_types_delete(
    request: Request,
    label: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    await delete_type(session, label)
    return RedirectResponse(url="/admin/types", status_code=303)

# ---------- Result & Submit ----------
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
    page_type: str | None = Form(None),  # optional override from form
    session: AsyncSession = Depends(get_session),
):
    if not url:
        return RedirectResponse(url=str(URL("/").include_query_params(error="Please provide a URL")), status_code=303)
    result = await _process_single(url, topic, subject, audience, address, phone, compare_existing, competitor1, competitor2, page_type, session)
    await record_run(session, result)
    return templates.TemplateResponse("result.html", {"request": request, **result})

# ---------- Batch Preview/Export (unchanged endpoints, using _process_single already adds advice & types) ----------
def _csv_from_items(items: list[dict]) -> io.StringIO:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["url","page_type_label","primary_type","secondary_types","score","valid","jsonld"])
    for it in items:
        writer.writerow([it["url"], it.get("page_type_label",""), it.get("primary_type",""), json.dumps(it.get("secondary_types",[])), it["overall"], "yes" if it["valid"] else "no", json.dumps(it["jsonld"])])
    out.seek(0); return out

@app.post("/batch/export_from_preview")
async def batch_export_from_preview(rows_json: str = Form(...)):
    items = json.loads(rows_json); out = _csv_from_items(items)
    filename = f"schema-batch-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.csv"
    return StreamingResponse(out, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{filename}"'})
