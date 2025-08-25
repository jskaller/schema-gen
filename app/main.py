
from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.datastructures import URL
import io, csv, json
import httpx

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
from datetime import datetime
from urllib.parse import urlparse

hospital_schema = Path("app/schemas/hospital.schema.json").read_text()

app = FastAPI(title="Schema Gen", version="0.6.0")
templates = Jinja2Templates(directory="app/web/templates")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, ok: str | None = None, error: str | None = None):
    return templates.TemplateResponse("index.html", {"request": request, "ok": ok, "error": error})

@app.get("/batch", response_class=HTMLResponse)
async def batch_page(request: Request, error: str | None = None, warnings: list[str] | None = None):
    return templates.TemplateResponse("batch.html", {"request": request, "error": error, "warnings": warnings or []})

async def _process_row(row: dict[str, str]) -> dict:
    url = row.get("url", "").strip()
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

    # Optional: compare existing on-page schema
    comp_summary = []
    if compare_existing:
        onpage = extract_onpage_jsonld(raw_html)
        primary = pick_primary_by_type(onpage, "Hospital") if onpage else None
        if primary:
            comp_summary.append(summarize_scores("On‑page JSON‑LD", primary, score_jsonld, required, recommended))

    return {
        "url": url,
        "score": final_score,
        "valid": "yes" if valid else "no",
        "jsonld": json.dumps(final_jsonld, ensure_ascii=False),
    }

def _csv_download(rows: list[dict[str, str]], prefix: str) -> StreamingResponse:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["url", "score", "valid", "jsonld"])
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    output.seek(0)
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    return StreamingResponse(
        output, media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{prefix}-{ts}.csv"'}
    )

@app.post("/batch/upload")
async def batch_upload(file: UploadFile = File(...)):
    text = (await file.read()).decode("utf-8", errors="ignore")
    rows, warnings = parse_csv(text)
    if not rows:
        return RedirectResponse(str(URL("/batch").include_query_params(error="No data rows found", warnings=warnings)), status_code=303)

    processed: list[dict[str, str]] = []
    for row in rows:
        try:
            result = await _process_row(row)
            processed.append(result)
        except Exception as e:
            processed.append({"url": row.get("url",""), "score": "", "valid": "error", "jsonld": str(e)})
    return _csv_download(processed, "schema-batch")

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
            result = await _process_row(row)
            processed.append(result)
        except Exception as e:
            processed.append({"url": row.get("url",""), "score": "", "valid": "error", "jsonld": str(e)})
    return _csv_download(processed, "schema-batch")
