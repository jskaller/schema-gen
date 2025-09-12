
from __future__ import annotations

import uuid
import asyncio
import traceback
import json
from urllib.parse import urlparse
from datetime import datetime, timezone

from fastapi import APIRouter, Request, Depends, Form, UploadFile, File, HTTPException
from fastapi.templating import Jinja2Templates
from starlette.responses import HTMLResponse, StreamingResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
import httpx

from app.db import get_session
from app.services.settings import get_settings
from app.services.csv_ingest import parse_csv
from app.services.progress import create_job, update_job, finish_job

templates = Jinja2Templates(directory="app/web/templates")
router = APIRouter()

# Lazy import to avoid circular/import-time errors during router discovery
def _get_process_single():
    from app.main_part2 import _process_single as _ps
    return _ps

def _base_url(u: str) -> str:
    try:
        p = urlparse(u)
        return f"{p.scheme}://{p.netloc}"
    except Exception:
        return u

def _breadcrumb_from_url(u: str):
    try:
        p = urlparse(u)
        seg = [s for s in p.path.split('/') if s]
        last = seg[-1] if seg else p.netloc
        return {"@type": "ListItem","position": 1,"item": {"@id": u, "name": last}}
    except Exception:
        return None

def _fallback_graph(label: str, url: str, subject: str, phone: str|None, address: str|None, mapping: dict):
    # Build a best-effort @graph using admin mapping (case-insensitive)
    key = (label or "WebPage").strip().lower()
    cfg = None
    if isinstance(mapping, dict):
        lower = { (k or "").strip().lower(): v for k, v in mapping.items() }
        cfg = lower.get(key) or mapping.get(label)
    primary = (cfg or {}).get("primary") or label or "WebPage"
    secondary = (cfg or {}).get("secondary") or []

    # Primary
    primary_node = {
        "@type": primary,
        "url": url,
        "name": subject,
        "dateModified": datetime.now(timezone.utc).isoformat()
    }
    if phone:
        primary_node["telephone"] = phone
    if address:
        primary_node["address"] = {"@type":"PostalAddress","streetAddress": address}

    graph = [primary_node]

    # Secondary
    site = _base_url(url)
    for t in secondary:
        tnorm = (t or "").strip()
        if tnorm == "JobPosting":
            # Only when fully populated (we don't have that here)
            continue
        if tnorm == "WebSite":
            graph.append({"@type":"WebSite","url": site, "name": subject})
        elif tnorm == "WebPage":
            graph.append({"@type":"WebPage","url": url, "name": subject})
        elif tnorm == "BreadcrumbList":
            crumb = _breadcrumb_from_url(url)
            if crumb:
                graph.append({"@type":"BreadcrumbList","itemListElement":[crumb]})
        else:
            # Generic node with a name if sensible
            node = {"@type": tnorm}
            if tnorm.endswith("Organization") or tnorm.endswith("Clinic") or tnorm.endswith("Service") or tnorm.endswith("Specialty"):
                node["name"] = subject
            if tnorm.endswith("Organization"):
                node["url"] = url
            graph.append(node)

    return {"@context":"https://schema.org", "@graph": graph}

@router.get("/batch", response_class=HTMLResponse)
async def batch_page(request: Request, session: AsyncSession = Depends(get_session)):
    settings = await get_settings(session)
    return templates.TemplateResponse("batch.html", {"request": request, "settings": settings})

@router.post("/batch/fetch_async", response_class=HTMLResponse)
async def batch_fetch_async(request: Request, csv_url: str = Form(...), session: AsyncSession = Depends(get_session)):
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            r = await client.get(csv_url)
            r.raise_for_status()
            content = r.text
    except Exception as e:
        return templates.TemplateResponse("batch.html", {"request": request, "error": str(e), "warnings": []})

    rows, warnings = parse_csv(content)
    if not rows:
        return templates.TemplateResponse("batch.html", {"request": request, "error": "No data rows found", "warnings": warnings or []})

    jobs = []
    for row in rows:
        job_id = str(uuid.uuid4())
        await create_job(job_id)

        async def runner(row=row, job_id=job_id):
            try:
                await update_job(job_id, 3, "Queued")
                # Open a fresh DB session for this background task
                async for task_session in get_session():
                    # log provider/model for quick sanity
                    try:
                        s = await get_settings(task_session)
                        prov = getattr(s, "provider", None)
                        pmodel = getattr(s, "provider_model", None)
                        await update_job(job_id, 5, f"Provider: {prov or 'unset'} | Model: {pmodel or 'unset'}")
                    except Exception:
                        await update_job(job_id, 5, "Provider: <error reading settings>")

                    result = await _get_process_single()(
                        row.get("url",""),
                        row.get("topic"),
                        row.get("subject"),
                        row.get("audience"),
                        row.get("address"),
                        row.get("phone"),
                        row.get("existing") or row.get("compare_existing"),
                        row.get("competitor1"),
                        row.get("competitor2"),
                        row.get("page_type") or None,
                        task_session,
                    )
                    await finish_job(job_id, result)
                    break
            except Exception as e:
                tb = traceback.format_exc()
                await update_job(job_id, 100, f"Error: {e}")
                # Build a valid @graph fallback using admin mapping
                url = row.get("url", "")
                label = row.get("page_type") or "WebPage"
                subject = row.get("subject") or row.get("topic") or url
                phone = row.get("phone")
                address = row.get("address")
                # Open a short-lived session to read mapping for fallback
                try:
                    async for ssession in get_session():
                        settings = await get_settings(ssession)
                        mapping = settings.page_type_map or {}
                        jsonld = _fallback_graph(label, url, subject, phone, address, mapping)
                        await finish_job(job_id, {"url": url, "error": str(e), "traceback": tb, "jsonld": jsonld})
                        break
                except Exception:
                    # Absolute fallback if settings fetch fails
                    jsonld = _fallback_graph(label, url, subject, phone, address, {})
                    await finish_job(job_id, {"url": url, "error": str(e), "traceback": tb, "jsonld": jsonld})

        asyncio.create_task(runner())
        jobs.append({"job_id": job_id, "url": row.get("url","")})

    return templates.TemplateResponse("batch_run.html", {"request": request, "jobs": jobs})

@router.post("/batch/upload_async", response_class=HTMLResponse)
async def batch_upload_async(request: Request, file: UploadFile = File(...), session: AsyncSession = Depends(get_session)):
    text = (await file.read()).decode("utf-8", errors="ignore")
    rows, warnings = parse_csv(text)
    if not rows:
        return templates.TemplateResponse("batch.html", {"request": request, "error": "No data rows found", "warnings": warnings or []})

    jobs = []
    for row in rows:
        job_id = str(uuid.uuid4())
        await create_job(job_id)

        async def runner(row=row, job_id=job_id):
            try:
                await update_job(job_id, 3, "Queued")
                async for task_session in get_session():
                    try:
                        s = await get_settings(task_session)
                        prov = getattr(s, "provider", None)
                        pmodel = getattr(s, "provider_model", None)
                        await update_job(job_id, 5, f"Provider: {prov or 'unset'} | Model: {pmodel or 'unset'}")
                    except Exception:
                        await update_job(job_id, 5, "Provider: <error reading settings>")

                    result = await _get_process_single()(
                        row.get("url",""),
                        row.get("topic"),
                        row.get("subject"),
                        row.get("audience"),
                        row.get("address"),
                        row.get("phone"),
                        row.get("existing") or row.get("compare_existing"),
                        row.get("competitor1"),
                        row.get("competitor2"),
                        row.get("page_type") or None,
                        task_session,
                    )
                    await finish_job(job_id, result)
                    break
            except Exception as e:
                tb = traceback.format_exc()
                await update_job(job_id, 100, f"Error: {e}")
                url = row.get("url", "")
                label = row.get("page_type") or "WebPage"
                subject = row.get("subject") or row.get("topic") or url
                phone = row.get("phone")
                address = row.get("address")
                try:
                    async for ssession in get_session():
                        settings = await get_settings(ssession)
                        mapping = settings.page_type_map or {}
                        jsonld = _fallback_graph(label, url, subject, phone, address, mapping)
                        await finish_job(job_id, {"url": url, "error": str(e), "traceback": tb, "jsonld": jsonld})
                        break
                except Exception:
                    jsonld = _fallback_graph(label, url, subject, phone, address, {})
                    await finish_job(job_id, {"url": url, "error": str(e), "traceback": tb, "jsonld": jsonld})

        asyncio.create_task(runner())
        jobs.append({"job_id": job_id, "url": row.get("url","")})

    return templates.TemplateResponse("batch_run.html", {"request": request, "jobs": jobs})

@router.get("/events/{job_id}")
async def events(job_id: str):
    from app.services.progress import get_job
    async def event_stream():
        last_len = 0
        for _ in range(900):
            job = await get_job(job_id)
            if not job:
                yield "event: error\n"
                yield "data: {\"msg\": \"unknown job\", \"progress\": 100}\n\n"
                return
            msgs = job.get("messages") or []
            for i in range(last_len, len(msgs)):
                payload = {"msg": msgs[i]["msg"], "progress": int(job.get("progress", 0))}
                yield "data: " + json.dumps(payload) + "\n\n"
            last_len = len(msgs)
            if job.get("status") == "done" or int(job.get("progress", 0)) >= 100:
                yield "data: " + json.dumps({"msg": "done", "progress": 100}) + "\n\n"
                return
            await asyncio.sleep(1)
    return StreamingResponse(event_stream(), media_type="text/event-stream")

@router.get("/result/{job_id}", response_class=HTMLResponse)
async def batch_result(request: Request, job_id: str, session: AsyncSession = Depends(get_session)):
    from app.services.progress import get_job
    from app.services.history import record_run

    job = await get_job(job_id)
    if not job or not job.get("result"):
        return templates.TemplateResponse("progress.html", {"request": request, "job_id": job_id, "error": job and job.get("error")})
    result = job["result"]
    try:
        await record_run(session, result)
    except Exception:
        pass
    return templates.TemplateResponse("result.html", {"request": request, **result})

@router.get("/api/job/{job_id}")
async def api_job(job_id: str):
    from app.services.progress import get_job
    job = await get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return JSONResponse(job)

@router.post("/batch/export_jobs")
async def export_jobs():
    # Minimal JSON export of finished jobs
    try:
        from app.services.progress import list_jobs
        jobs = await list_jobs()
    except Exception:
        return JSONResponse({"ok": False, "error": "export not implemented in this build"}, status_code=200)

    out = []
    for job_id, job in jobs.items():
        if job.get("result"):
            out.append({"job_id": job_id, "result": job["result"]})
    return JSONResponse({"ok": True, "count": len(out), "items": out})
