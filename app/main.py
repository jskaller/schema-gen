
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.datastructures import URL

import io, csv, json, re
from urllib.parse import urlparse
from datetime import datetime

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

app = FastAPI(title="Schema Gen", version="0.5.0")
templates = Jinja2Templates(directory="app/web/templates")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, ok: str | None = None, error: str | None = None):
    return templates.TemplateResponse("index.html", {"request": request, "ok": ok, "error": error})

def _safe_filename_from_url(url: str, prefix: str, ext: str) -> str:
    host = urlparse(url).netloc.replace(":", "_")
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
        "cleaned_text": cleaned_text,
        "jsonld": final_jsonld,
        "valid": final_valid,
        "validation_errors": final_errors,
        "overall": final_score,
        "details": final_details,
        "iterations": iterations,
        "comparisons": comparisons,
        "comparison_notes": notes,
        "signals": sig,
    }

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
            # Batch mode: process and return CSV
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["url", "score", "valid", "jsonld"])
            for u in urls:
                try:
                    result = await _process_single(u, topic, subject, audience, address, phone, None, None, None)
                    writer.writerow([u, result["overall"], "yes" if result["valid"] else "no", json.dumps(result["jsonld"])])
                except Exception as e:
                    writer.writerow([u, "", "error", str(e)])
            output.seek(0)
            filename = f"schema-export-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.csv"
            return StreamingResponse(
                output, media_type="text/csv",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'}
            )
        else:
            # Single mode: proceed to HTML result page
            if not url:
                return RedirectResponse(url=str(URL("/").include_query_params(error="Please provide a URL or batch URLs")), status_code=303)
            result = await _process_single(url, topic, subject, audience, address, phone, compare_existing, competitor1, competitor2)
            return templates.TemplateResponse(
                "result.html",
                {"request": request, **result, "topic": topic, "subject": subject, "audience": audience, "address": address, "phone": phone},
            )
    except Exception as e:
        return RedirectResponse(url=str(URL("/").include_query_params(error=str(e))), status_code=303)

@app.post("/export/jsonld")
async def export_jsonld(jsonld: str = Form(...), url: str = Form(...)):
    data = json.loads(jsonld)
    filename = _safe_filename_from_url(url, "schema", "json")
    payload = json.dumps(data, indent=2)
    return Response(
        content=payload,
        media_type="application/ld+json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

@app.post("/export/csv")
async def export_csv(jsonld: str = Form(...), url: str = Form(...), score: str = Form(""),):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["url", "score", "jsonld"])
    writer.writerow([url, score, jsonld])
    output.seek(0)
    filename = _safe_filename_from_url(url, "schema-single", "csv")
    return StreamingResponse(
        output, media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )
