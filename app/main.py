
from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.datastructures import URL

import io, csv, json
import httpx
from datetime import datetime
from urllib.parse import urlparse

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

app = FastAPI(title="Schema Gen", version="0.7.3")
templates = Jinja2Templates(directory="app/web/templates")

# ------------------------------
# Helpers
# ------------------------------
def _safe_filename_from_url(url: str, prefix: str, ext: str) -> str:
    host = urlparse(url).netloc.replace(":", "_") or "schema"
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{host}-{ts}.{ext}"

async def _process_single(url: str, topic, subject, audience, address, phone, compare_existing, competitor1, competitor2):
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

async def _process_row(row: dict[str, str]) -> dict:
    # Row -> lightweight dict for batch preview/export
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

# ------------------------------
# Routes
# ------------------------------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request, ok: str | None = None, error: str | None = None):
    return templates.TemplateResponse("index.html", {"request": request, "ok": ok, "error": error})

@app.post("/submit", response_class=HTMLResponse)
async def submit(
    request: Request,
    url: str = Form(""),
    batch_urls: str = Form(""),
    topic: str | None = Form(None),
    subject: str | None = Form(None),
    audience: str | None = Form(None),
    address: str | None = Form(None),
    phone: str | None = Form(None),
    compare_existing: str | None = Form(None),
    competitor1: str | None = Form(None),
    competitor2: str | None = Form(None),
):
    try:
        urls = [u.strip() for u in (batch_urls or "").splitlines() if u.strip()]
        if urls:
            # Legacy single-page batch entry: produce CSV directly
            items = []
            for u in urls:
                try:
                    r = await _process_single(u, topic, subject, audience, address, phone, None, None, None)
                    items.append({"url": r["url"], "overall": r["overall"], "valid": r["valid"], "jsonld": r["jsonld"]})
                except Exception as e:
                    items.append({"url": u, "overall": "", "valid": False, "jsonld": {"error": str(e)}})
            out = _csv_from_items(items)
            filename = f"schema-export-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.csv"
            cd = f'attachment; filename="{filename}"'
            return StreamingResponse(out, media_type="text/csv", headers={"Content-Disposition": cd})
        else:
            if not url:
                return RedirectResponse(url=str(URL("/").include_query_params(error="Please provide a URL")), status_code=303)
            result = await _process_single(url, topic, subject, audience, address, phone, compare_existing, competitor1, competitor2)
            return templates.TemplateResponse("result.html", {"request": request, **result})
    except Exception as e:
        return RedirectResponse(url=str(URL("/").include_query_params(error=str(e))), status_code=303)

# ------------------------------
# Export endpoints (single)
# ------------------------------
@app.post("/export/jsonld")
async def export_jsonld(jsonld: str = Form(...), url: str = Form(...)):
    data = json.loads(jsonld)
    filename = _safe_filename_from_url(url, "schema", "json")
    payload = json.dumps(data, indent=2)
    cd = f'attachment; filename="{filename}"'
    return Response(content=payload, media_type="application/ld+json", headers={"Content-Disposition": cd})

@app.post("/export/csv")
async def export_csv(jsonld: str = Form(...), url: str = Form(...), score: str = Form("")):
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["url", "score", "jsonld"])
    writer.writerow([url, score, jsonld])
    out.seek(0)
    filename = _safe_filename_from_url(url, "schema-single", "csv")
    cd = f'attachment; filename="{filename}"'
    return StreamingResponse(out, media_type="text/csv", headers={"Content-Disposition": cd})

# ------------------------------
# Batch ingest + preview routes
# ------------------------------
@app.get("/batch", response_class=HTMLResponse)
async def batch_page(request: Request, error: str | None = None, warnings: list[str] | None = None):
    return templates.TemplateResponse("batch.html", {"request": request, "error": error, "warnings": warnings or []})

@app.post("/batch/upload")
async def batch_upload(file: UploadFile = File(...)):
    text = (await file.read()).decode("utf-8", errors="ignore")
    rows, warnings = parse_csv(text)
    if not rows:
        return RedirectResponse(str(URL("/batch").include_query_params(error="No data rows found", warnings=warnings)), status_code=303)
    processed: list[dict[str, str]] = []
    for row in rows:
        try:
            r = await _process_row(row)
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
    cd = f'attachment; filename="schema-batch-{ts}.csv"'
    return StreamingResponse(out, media_type="text/csv", headers={"Content-Disposition": cd})

@app.post("/batch/fetch")
async def batch_fetch(csv_url: str = Form(...)):
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
            r = await _process_row(row)
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
    cd = f'attachment; filename="schema-batch-{ts}.csv"'
    return StreamingResponse(out, media_type="text/csv", headers={"Content-Disposition": cd})

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
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["url", "score", "valid", "jsonld"])
    for it in items:
        writer.writerow([it["url"], it["overall"], "yes" if it["valid"] else "no", json.dumps(it["jsonld"])])
    out.seek(0)
    filename = f"schema-batch-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.csv"
    cd = f'attachment; filename="{filename}"'
    return StreamingResponse(out, media_type="text/csv", headers={"Content-Disposition": cd})
