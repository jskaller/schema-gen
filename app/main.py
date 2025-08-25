
from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.datastructures import URL

import io, csv, json
import httpx
from datetime import datetime

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

app = FastAPI(title="Schema Gen", version="0.7.0")
templates = Jinja2Templates(directory="app/web/templates")

@app.get("/batch", response_class=HTMLResponse)
async def batch_page(request: Request, error: str | None = None, warnings: list[str] | None = None):
    return templates.TemplateResponse("batch.html", {"request": request, "error": error, "warnings": warnings or []})

async def _process_row(row: dict[str, str]) -> dict:
    url = (row.get("url") or "").strip()
    topic = row.get("topic") or None
    subject = row.get("subject") or None
    audience = row.get("audience") or None
    address = row.get("address") or None
    phone = row.get("phone") or None
    compare_existing = row.get("compare_existing") or None
    competitor1 = row.get("competitor1") or None
    competitor2 = row.get("competitor2") or None

    raw_html = await fetch_url(url)
    cleaned_text = extract_clean_text(raw_html)
    sig = extract_signals(raw_html)

    provider = get_provider("dummy")
    payload = GenerationInputs(
        url=url,
        cleaned_text=cleaned_text,
        topic=topic,
        subject=subject,
        audience=audience,
        address=address or sig.get("address"),
        phone=phone or sig.get("phone"),
        sameAs=sig.get("sameAs"),
        page_type="Hospital",
    )
    jsonld = provider.generate_jsonld(payload)

    valid, errors = validate_against_schema(jsonld, hospital_schema)
    required = ["@context", "@type", "name", "url"]
    recommended = ["description", "telephone", "address", "audience", "dateModified", "sameAs", "medicalSpecialty"]
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

    # Comparisons
    comparisons = []
    notes = []
    if compare_existing:
        onpage = extract_onpage_jsonld(raw_html)
        primary = pick_primary_by_type(onpage, "Hospital") if onpage else None
        if primary:
            comparisons.append(summarize_scores("On‑page JSON‑LD", primary, score_jsonld, required, recommended))
        else:
            notes.append("No on‑page JSON‑LD suitable for Hospital found.")
    for label, comp_url in (("Competitor #1", competitor1), ("Competitor #2", competitor2)):
        if comp_url:
            try:
                comp_html = await fetch_url(comp_url)
                comp_items = extract_onpage_jsonld(comp_html)
                comp_primary = pick_primary_by_type(comp_items, "Hospital")
                if comp_primary:
                    comparisons.append(summarize_scores(f"{label}", comp_primary, score_jsonld, required, recommended))
                else:
                    notes.append(f"{label}: no suitable JSON‑LD found.")
            except Exception as ce:
                notes.append(f"{label}: fetch error – {ce}")

    return {
        "url": url,
        "overall": final_score,
        "valid": final_valid,
        "validation_errors": final_errors,
        "jsonld": final_jsonld,
        "comparisons": comparisons,
        "comparison_notes": notes,
        "excerpt": cleaned_text[:2000],
    }

def _csv_from_items(items: list[dict]) -> io.StringIO:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["url", "score", "valid", "jsonld"])
    for it in items:
        writer.writerow([it["url"], it["overall"], "yes" if it["valid"] else "no", json.dumps(it["jsonld"])])
    out.seek(0)
    return out

@app.post("/batch/preview_upload", response_class=HTMLResponse)
async def batch_preview_upload(request: Request, file: UploadFile = File(...)):
    text = (await file.read()).decode("utf-8", errors="ignore")
    rows, warnings = parse_csv(text)
    if not rows:
        return RedirectResponse(str(URL("/batch").include_query_params(error="No data rows found", warnings=warnings)), status_code=303)

    items = []
    for row in rows:
        try:
            items.append(await _process_row(row))
        except Exception as e:
            items.append({"url": row.get("url",""), "overall": "", "valid": False, "validation_errors": [str(e)], "jsonld": {}, "comparisons": [], "comparison_notes": [], "excerpt": ""})

    return templates.TemplateResponse("batch_preview.html", {"request": request, "items": items})

@app.post("/batch/preview_fetch", response_class=HTMLResponse)
async def batch_preview_fetch(request: Request, csv_url: str = Form(...)):
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
            items.append(await _process_row(row))
        except Exception as e:
            items.append({"url": row.get("url",""), "overall": "", "valid": False, "validation_errors": [str(e)], "jsonld": {}, "comparisons": [], "comparison_notes": [], "excerpt": ""})

    return templates.TemplateResponse("batch_preview.html", {"request": request, "items": items})

@app.post("/batch/export_from_preview")
async def batch_export_from_preview(rows_json: str = Form(...)):
    items = json.loads(rows_json)
    out = _csv_from_items(items)
    filename = f"schema-batch-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.csv"
    return StreamingResponse(
        out, media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )
