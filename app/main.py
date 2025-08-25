
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
from app.services.settings import get_settings, update_settings
from app.services.providers import list_ollama_models
from app.services.ai import get_provider, GenerationInputs
from app.services.schemas import load_schema, defaults_for
from app.services.csv_ingest import parse_csv
from app.services.fetch import fetch_url
from app.services.extract import extract_clean_text
from app.services.validate import validate_against_schema
from app.services.score import score_jsonld
from app.services.signals import extract_signals
from app.services.refine import refine_to_perfect
from app.services.jsonld_extract import extract_onpage_jsonld
from app.services.compare import summarize_scores, pick_primary_by_type

app = FastAPI(title="Schema Gen", version="1.4.0")
templates = Jinja2Templates(directory="app/web/templates")

@app.on_event("startup")
async def _startup():
    await init_db()

def _resolve_types(s, label: str):
    # label from row or default settings.page_type
    mapping = s.page_type_map or {}
    entry = mapping.get(label) or {"primary": label, "secondary": []}
    primary = entry.get("primary") or label
    secondary = entry.get("secondary") or []
    return primary, secondary

def _safe_filename_from_url(url: str, prefix: str, ext: str) -> str:
    host = urlparse(url).netloc.replace(":", "_") or "schema"
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{host}-{ts}.{ext}"

async def _process_single(effective_label, url, topic, subject, audience, address, phone, compare_existing, competitor1, competitor2, session: AsyncSession):
    s = await get_settings(session)
    primary_type, secondary_types = _resolve_types(s, effective_label or s.page_type)

    raw_html = await fetch_url(url)
    cleaned_text = extract_clean_text(raw_html)
    sig = extract_signals(raw_html)

    provider = get_provider(s.provider or "dummy", model=s.provider_model or None)
    payload = GenerationInputs(
        url=url, cleaned_text=cleaned_text, topic=topic, subject=subject, audience=audience,
        address=address or sig.get("address"), phone=phone or sig.get("phone"), sameAs=sig.get("sameAs"),
        page_type=primary_type, secondary_types=secondary_types
    )
    jsonld = await provider.generate_jsonld(payload)

    # If provider didn't include @graph nodes for secondaries, add minimal stubs
    if secondary_types:
        if "@graph" not in jsonld:
            jsonld = {"@context": "https://schema.org", "@graph": [jsonld]}
        existing_types = set()
        for node in jsonld.get("@graph", []):
            t = node.get("@type")
            if isinstance(t, list):
                existing_types.update(t)
            elif isinstance(t, str):
                existing_types.add(t)
        for t in secondary_types:
            if t not in existing_types:
                stub = {"@type": t}
                if t == "BreadcrumbList":
                    stub["@id"] = url + "#breadcrumbs"; stub["itemListElement"] = []
                elif t.endswith("WebPage") or t == "MedicalWebPage":
                    stub["@id"] = url; stub["name"] = subject or topic or t; stub["url"] = url
                jsonld["@graph"].append(stub)

    required = (s.required_fields or defaults_for(primary_type)["required"])
    recommended = (s.recommended_fields or defaults_for(primary_type)["recommended"])

    # validation against primary schema
    schema_text = load_schema(primary_type)
    valid, errors = validate_against_schema(jsonld if "@graph" not in jsonld else jsonld["@graph"][0], schema_text)

    overall, details = score_jsonld(jsonld if "@graph" not in jsonld else jsonld["@graph"][0], required, recommended)

    final_jsonld, final_score, final_details, iterations = refine_to_perfect(
        base_jsonld=jsonld if "@graph" not in jsonld else jsonld["@graph"][0],
        cleaned_text=cleaned_text,
        required=required,
        recommended=recommended,
        score_fn=score_jsonld,
        max_attempts=3,
    )
    # If we refined main node, put it back into @graph if needed
    if "@graph" in jsonld:
        jsonld["@graph"][0] = final_jsonld
        final_jsonld = jsonld

    final_valid, final_errors = validate_against_schema(final_jsonld if "@graph" not in final_jsonld else final_jsonld["@graph"][0], schema_text)

    # comparisons
    comparisons, notes = [], []
    if compare_existing:
        onpage = extract_onpage_jsonld(raw_html)
        primary = pick_primary_by_type(onpage, primary_type) if onpage else None
        if primary:
            comparisons.append(summarize_scores("On‑page JSON‑LD", primary, score_jsonld, required, recommended))
        else:
            notes.append("No on‑page JSON‑LD suitable for page type found.")
    for label, comp_url in (("Competitor #1", competitor1), ("Competitor #2", competitor2)):
        if comp_url:
            try:
                comp_html = await fetch_url(comp_url)
                comp_items = extract_onpage_jsonld(comp_html)
                comp_primary = pick_primary_by_type(comp_items, primary_type)
                if comp_primary:
                    comparisons.append(summarize_scores(f"{label}", comp_primary, score_jsonld, required, recommended))
                else:
                    notes.append(f"{label}: no suitable JSON‑LD found.")
            except Exception as ce:
                notes.append(f"{label}: fetch error – {ce}")

    return {
        "url": url,
        "page_type_label": effective_label or s.page_type,
        "primary_type": primary_type,
        "secondary_types": secondary_types,
        "jsonld": final_jsonld,
        "valid": final_valid,
        "validation_errors": final_errors,
        "overall": final_score,
        "details": final_details,
        "iterations": iterations,
        "comparisons": comparisons,
        "comparison_notes": notes,
        "excerpt": cleaned_text[:2000],
        "length": len(cleaned_text),
    }

# Routes: admin, including page_type_map JSON
@app.get("/admin", response_class=HTMLResponse)
async def admin_get(request: Request, session: AsyncSession = Depends(get_session), ok: str | None = None):
    s = await get_settings(session)
    models = await list_ollama_models()
    return templates.TemplateResponse("admin.html", {"request": request, "settings": s, "ok": ok, "ollama_models": models})

@app.post("/admin", response_class=HTMLResponse)
async def admin_post(
    request: Request,
    provider: str = Form("dummy"),
    provider_model: str = Form(""),
    page_type: str = Form("Hospital"),
    required_fields: str = Form(""),
    recommended_fields: str = Form(""),
    use_defaults: str = Form(None),
    page_type_map: str = Form(""),
    session: AsyncSession = Depends(get_session),
):
    try:
        page_type_map_obj = json.loads(page_type_map) if page_type_map.strip() else None
        if use_defaults:
            req, rec = defaults_for(page_type)["required"], defaults_for(page_type)["recommended"]
        else:
            req = json.loads(required_fields) if required_fields.strip() else None
            rec = json.loads(recommended_fields) if recommended_fields.strip() else None
    except Exception as e:
        s = await get_settings(session)
        models = await list_ollama_models()
        return templates.TemplateResponse("admin.html", {"request": request, "settings": s, "error": f"Invalid JSON: {e}", "ollama_models": models})
    await update_settings(session, provider, page_type, req, rec, provider_model or None, page_type_map_obj)
    return RedirectResponse(url="/admin?ok=1", status_code=303)

# Batch: accept per-row page_type
@app.get("/batch", response_class=HTMLResponse)
async def batch_page(request: Request, error: str | None = None, warnings: list[str] | None = None):
    return templates.TemplateResponse("batch.html", {"request": request, "error": error, "warnings": warnings or []})

def _csv_from_items(items: list[dict]) -> io.StringIO:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["url","page_type_label","primary_type","secondary_types","score","valid","jsonld"])
    for it in items:
        writer.writerow([it["url"], it["page_type_label"], it["primary_type"], "|".join(it["secondary_types"]), it["overall"], "yes" if it["valid"] else "no", json.dumps(it["jsonld"])])
    out.seek(0); return out

@app.post("/batch/upload")
async def batch_upload(file: UploadFile = File(...), session: AsyncSession = Depends(get_session)):
    text = (await file.read()).decode("utf-8", errors="ignore")
    rows, warnings = parse_csv(text)
    if not rows:
        return RedirectResponse(str(URL("/batch").include_query_params(error="No data rows found", warnings=warnings)), status_code=303)
    processed = []
    for row in rows:
        try:
            r = await _process_single(row.get("page_type") or None, row.get("url",""), row.get("topic") or None, row.get("subject") or None, row.get("audience") or None, row.get("address") or None, row.get("phone") or None, row.get("compare_existing") or None, row.get("competitor1") or None, row.get("competitor2") or None, session)
            processed.append(r)
        except Exception as e:
            processed.append({"url": row.get("url",""), "page_type_label": row.get("page_type") or "", "primary_type": "", "secondary_types": [], "overall": "", "valid": False, "jsonld": {"error": str(e)}})
    out = _csv_from_items(processed)
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
            items.append(await _process_single(row.get("page_type") or None, row.get("url",""), row.get("topic") or None, row.get("subject") or None, row.get("audience") or None, row.get("address") or None, row.get("phone") or None, row.get("compare_existing") or None, row.get("competitor1") or None, row.get("competitor2") or None, session))
        except Exception as e:
            items.append({"url": row.get("url",""), "page_type_label": row.get("page_type") or "", "primary_type": "", "secondary_types": [], "overall": "", "valid": False, "validation_errors": [str(e)], "jsonld": {}, "comparisons": [], "comparison_notes": [], "excerpt": ""})
    return templates.TemplateResponse("batch_preview.html", {"request": request, "items": items})

# Minimal root and export endpoints preserved are assumed present elsewhere
