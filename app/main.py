
from fastapi import FastAPI, Request, Form, UploadFile, File, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse, Response, JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.datastructures import URL

import io, csv, json, sys, asyncio, uuid
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

app = FastAPI(title="Schema Gen", version="1.7.1")
templates = Jinja2Templates(directory="app/web/templates")

@app.get("/__routes")
async def __routes():
    data = [{"path": getattr(r, "path", "?"), "methods": sorted(list(getattr(r, "methods", {'*'})))} for r in app.router.routes]
    return JSONResponse(data)

@app.on_event("startup")
async def _startup():
    await init_db()
    print("[ROUTES at startup]\n" + "\n".join(sorted(f"{','.join(sorted(getattr(r,'methods',{'*'})))} {getattr(r,'path','?')}" for r in app.router.routes)), file=sys.stderr)

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

async def _process_single(url: str, topic, subject, audience, address, phone, compare_existing, competitor1, competitor2, label, session: AsyncSession):
    raw_html = await fetch_url(url)
    cleaned_text = extract_clean_text(raw_html)
    sig = extract_signals(raw_html)

    page_label, primary_type, secondary_types, s = await resolve_types(session, label)
    provider = get_provider(s.provider or "dummy", model=s.provider_model or None)

    payload = GenerationInputs(
        url=url, cleaned_text=cleaned_text, topic=topic, subject=subject, audience=audience,
        address=address or sig.get("address"), phone=phone or sig.get("phone"), sameAs=sig.get("sameAs"),
        page_type=primary_type,
    )
    base_jsonld = await provider.generate_jsonld(payload)

    inputs = {"topic": topic, "subject": subject, "address": address, "phone": phone, "url": url}
    primary_node = normalize_jsonld(base_jsonld, primary_type, inputs)
    final_jsonld = assemble_graph(primary_node, secondary_types, url, inputs) if secondary_types else primary_node
    final_jsonld = enhance_jsonld(final_jsonld, secondary_types, raw_html, url, topic, subject)

    schema_json = load_schema(primary_type)
    effective_required = (s.required_fields or defaults_for(primary_type)["required"])
    effective_recommended = (s.recommended_fields or defaults_for(primary_type)["recommended"])

    root_node = final_jsonld["@graph"][0] if isinstance(final_jsonld, dict) and "@graph" in final_jsonld else final_jsonld
    valid, errors = validate_against_schema(root_node, schema_json)
    overall, details = score_jsonld(root_node, effective_required, effective_recommended)

    missing_recommended = [key for key in effective_recommended if key not in root_node or root_node.get(key) in (None, "", [])]
    tips = [f"Consider adding: {key}" for key in missing_recommended]

    return {
        "url": url, "page_type_label": page_label, "primary_type": primary_type, "secondary_types": secondary_types,
        "topic": topic, "subject": subject, "audience": audience,
        "address": root_node.get("address"), "phone": root_node.get("telephone"),
        "excerpt": cleaned_text[:2000], "length": len(cleaned_text),
        "jsonld": final_jsonld, "valid": valid, "validation_errors": errors,
        "overall": overall, "details": details, "iterations": 0,
        "comparisons": [], "comparison_notes": [],
        "advice": tips,
        "effective_required": effective_required, "effective_recommended": effective_recommended,
    }

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

    async def runner():
        steps = [("Fetching URL",10),("Extracting text",25),("Scanning signals",35),("Generating JSON-LD",55),("Normalizing",70),("Assembling graph",80),("Enhancing",85),("Validating",90),("Scoring & advice",95)]
        try:
            for msg, pct in steps:
                await update_job(job_id, pct, msg)
                await asyncio.sleep(0.12)
            result = await _process_single(url, topic, subject, audience, address, phone, compare_existing, competitor1, competitor2, page_type, session)
            await finish_job(job_id, result)
        except Exception as e:
            await update_job(job_id, 100, f"Error: {e}")
    asyncio.create_task(runner())
    return {"job_id": job_id}

@app.get("/events/{job_id}")
async def events(job_id: str):
    async def gen():
        while True:
            job = await get_job(job_id)
            if not job: break
            progress = job["progress"]
            msg = job["messages"][-1]["msg"] if job["messages"] else "Starting..."
            yield f"data: {json.dumps({'progress': progress, 'msg': msg})}\n\n"
            if progress >= 100: break
            await asyncio.sleep(1)
    return StreamingResponse(gen(), media_type="text/event-stream")

@app.get("/progress/{job_id}", response_class=HTMLResponse)
async def progress_page(request: Request, job_id: str):
    return templates.TemplateResponse("progress.html", {"request": request, "job_id": job_id})

@app.get("/result/{job_id}", response_class=HTMLResponse)
async def result_page(request: Request, job_id: str, session: AsyncSession = Depends(get_session)):
    job = await get_job(job_id)
    if not job or not job.get("result"):
        return RedirectResponse("/")
    result = job["result"]
    try:
        await record_run(session, result)
    except Exception as e:
        print(f"[history write failed] {e}", file=sys.stderr)
    return templates.TemplateResponse("result.html", {"request": request, **result})

@app.get("/admin", response_class=HTMLResponse)
async def admin_get(request: Request, session: AsyncSession = Depends(get_session), ok: str | None = None, error: str | None = None):
    s = await get_settings(session)
    models = await list_ollama_models()
    mapping = await get_map(session)
    return templates.TemplateResponse("admin.html", {"request": request, "settings": s, "ok": ok, "error": error, "ollama_models": models, "page_types": AVAILABLE_PAGE_TYPES, "mapping": mapping})

@app.post("/admin", response_class=HTMLResponse)
async def admin_post(request: Request,
    provider: str = Form("dummy"), provider_model: str = Form(""),
    page_type: str = Form("Hospital"), required_fields: str = Form(""), recommended_fields: str = Form(""),
    use_defaults: str = Form(None), page_type_map: str = Form(None),
    session: AsyncSession = Depends(get_session)):
    try:
        if use_defaults:
            defs = defaults_for(page_type); req, rec = defs["required"], defs["recommended"]
        else:
            req = json.loads(required_fields) if required_fields.strip() else None
            rec = json.loads(recommended_fields) if recommended_fields.strip() else None
        ptm = json.loads(page_type_map) if page_type_map else None
    except Exception as e:
        return await admin_get(request, session, error=str(e))
    await update_settings(session, provider, page_type, req, rec, provider_model or None, ptm)
    return RedirectResponse(url="/admin?ok=1", status_code=303)

@app.post("/admin/test", response_class=HTMLResponse)
async def admin_test(request: Request, session: AsyncSession = Depends(get_session)):
    s = await get_settings(session)
    provider = get_provider(s.provider, model=s.provider_model)
    sample_inputs = GenerationInputs(url="http://example.org", cleaned_text="Example text", page_type=s.page_type)
    result = await provider.generate_jsonld(sample_inputs)
    models = await list_ollama_models()
    mapping = await get_map(session)
    return templates.TemplateResponse("admin.html", {"request": request, "settings": s, "test_result": result, "ollama_models": models, "page_types": AVAILABLE_PAGE_TYPES, "mapping": mapping})

@app.get("/admin/types", response_class=HTMLResponse)
async def admin_types(request: Request, session: AsyncSession = Depends(get_session)):
    mapping = await get_map(session)
    return templates.TemplateResponse("admin_types.html", {"request": request, "mapping": mapping})

@app.post("/admin/types/upsert", response_class=HTMLResponse)
async def admin_types_upsert(request: Request, label: str = Form(...), primary: str = Form(...), secondary: str = Form(""), session: AsyncSession = Depends(get_session)):
    secondaries = [s.strip() for s in secondary.split(",") if s.strip()]
    await upsert_type(session, label, primary, secondaries)
    return RedirectResponse(url="/admin/types", status_code=303)

@app.post("/admin/types/delete", response_class=HTMLResponse)
async def admin_types_delete(request: Request, label: str = Form(...), session: AsyncSession = Depends(get_session)):
    await delete_type(session, label)
    return RedirectResponse(url="/admin/types", status_code=303)

@app.get("/history", response_class=HTMLResponse)
async def history_list_page(request: Request, q: str | None = None, session: AsyncSession = Depends(get_session)):
    rows = await list_runs(session, q=q or None, limit=200)
    return templates.TemplateResponse("history_list.html", {"request": request, "rows": rows, "q": q})

@app.get("/history/{run_id}", response_class=HTMLResponse)
async def history_detail(request: Request, run_id: int, session: AsyncSession = Depends(get_session)):
    run = await db_get_run(session, run_id)
    if not run:
        return RedirectResponse(url="/history", status_code=303)
    return templates.TemplateResponse("history_detail.html", {"request": request, "run": run})

@app.post("/export/jsonld")
async def export_jsonld(jsonld: str = Form(...), url: str = Form(...)):
    data = json.loads(jsonld)
    filename = _safe_filename_from_url(url, "schema", "json")
    payload = json.dumps(data, indent=2)
    return Response(content=payload, media_type="application/ld+json", headers={"Content-Disposition": f'attachment; filename="{filename}"'})

@app.post("/export/csv")
async def export_csv(jsonld: str = Form(...), url: str = Form(...), score: str = Form("")):
    out = io.StringIO()
    writer = csv.writer(out); writer.writerow(["url", "score", "jsonld"]); writer.writerow([url, score, jsonld])
    out.seek(0); filename = _safe_filename_from_url(url, "schema-single", "csv")
    return StreamingResponse(out, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{filename}"'})

def _csv_from_items(items: list[dict]) -> io.StringIO:
    out = io.StringIO(); writer = csv.writer(out)
    writer.writerow(["url","page_type_label","primary_type","secondary_types","score","valid","jsonld"])
    for it in items:
        writer.writerow([it["url"], it.get("page_type_label",""), it.get("primary_type",""), json.dumps(it.get("secondary_types",[])), it["overall"], "yes" if it["valid"] else "no", json.dumps(it["jsonld"])])
    out.seek(0); return out

@app.get("/batch", response_class=HTMLResponse)
async def batch_page(request: Request, error: str | None = None, warnings: list[str] | None = None):
    return templates.TemplateResponse("batch.html", {"request": request, "error": error, "warnings": warnings or []})

@app.post("/batch/upload")
async def batch_upload(file: UploadFile = File(...), session: AsyncSession = Depends(get_session)):
    text = (await file.read()).decode("utf-8", errors="ignore")
    rows, warnings = parse_csv(text)
    if not rows:
        return RedirectResponse(str(URL("/batch").include_query_params(error="No data rows found", warnings=warnings)), status_code=303)
    processed = []
    for row in rows:
        try:
            r = await _process_single(row.get("url",""), row.get("topic"), row.get("subject"), row.get("audience"), row.get("address"), row.get("phone"), row.get("compare_existing"), row.get("competitor1"), row.get("competitor2"), row.get("page_type") or None, session)
            processed.append({"url": r["url"], "score": r["overall"], "valid": "yes" if r["valid"] else "no", "jsonld": json.dumps(r["jsonld"])})
        except Exception as e:
            processed.append({"url": row.get("url",""), "score": "", "valid": "error", "jsonld": str(e)})
    out = io.StringIO(); writer = csv.DictWriter(out, fieldnames=["url", "score", "valid", "jsonld"]); writer.writeheader()
    for row in processed: writer.writerow(row)
    out.seek(0)
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    return StreamingResponse(out, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="schema-batch-{ts}.csv"'} )

@app.post("/batch/fetch")
async def batch_fetch(csv_url: str = Form(...), session: AsyncSession = Depends(get_session)):
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            r = await client.get(csv_url); r.raise_for_status(); content = r.text
    except Exception as e:
        return RedirectResponse(str(URL("/batch").include_query_params(error=str(e))), status_code=303)
    rows, warnings = parse_csv(content)
    if not rows:
        return RedirectResponse(str(URL("/batch").include_query_params(error="No data rows found", warnings=warnings)), status_code=303)
    items = []
    for row in rows:
        try:
            items.append(await _process_single(row.get("url",""), row.get("topic"), row.get("subject"), row.get("audience"), row.get("address"), row.get("phone"), row.get("compare_existing"), row.get("competitor1"), row.get("competitor2"), row.get("page_type") or None, session))
        except Exception as e:
            items.append({"url": row.get("url",""), "overall": "", "valid": False, "validation_errors": [str(e)], "jsonld": {}, "comparisons": [], "comparison_notes": [], "excerpt": "", "advice": []})
    return templates.TemplateResponse("batch_preview.html", {"request": request, "items": items})

@app.post("/batch/export_from_preview")
async def batch_export_from_preview(rows_json: str = Form(...)):
    items = json.loads(rows_json); out = _csv_from_items(items)
    filename = f"schema-batch-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.csv"
    return StreamingResponse(out, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{filename}"'})
