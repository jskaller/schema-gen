from __future__ import annotations

import uuid
import asyncio
import traceback
import json

from fastapi import APIRouter, Request, Depends, Form, UploadFile, File
from fastapi.templating import Jinja2Templates
from starlette.responses import HTMLResponse, StreamingResponse
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

        async def runner(row=row, ):
            try:
                await update_job(job_id, 3, "Queued")

                # Log provider selection for debugging (read from DB at runtime)
                try:
                    s = await get_settings(session)
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
                    row.get("city"),
                    row.get("state"),
                    row.get("zip"),
                    row.get("geo"),
                    row.get("phone"),
                    row.get("email"),
                    row.get("hours"),
                    row.get("services"),
                    row.get("existing"),
                    row.get("competitor1"),
                    row.get("competitor2"),
                    row.get("page_type") or None,
                    session,
                    ,
                )
                await finish_job(job_id, result)
            except Exception as e:
                tb = traceback.format_exc()
                await update_job(job_id, 100, f"Error: {e}")
                await finish_job(job_id, {"url": row.get("url",""), "error": str(e), "traceback": tb, "jsonld": {"@context": "https://schema.org", "@type": "Thing"}})

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

        async def runner(row=row, ):
            try:
                await update_job(job_id, 3, "Queued")

                # Log provider selection for debugging
                try:
                    s = await get_settings(session)
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
                    row.get("city"),
                    row.get("state"),
                    row.get("zip"),
                    row.get("geo"),
                    row.get("phone"),
                    row.get("email"),
                    row.get("hours"),
                    row.get("services"),
                    row.get("existing"),
                    row.get("competitor1"),
                    row.get("competitor2"),
                    row.get("page_type") or None,
                    session,
                    ,
                )
                await finish_job(job_id, result)
            except Exception as e:
                tb = traceback.format_exc()
                await update_job(job_id, 100, f"Error: {e}")
                await finish_job(job_id, {"url": row.get("url",""), "error": str(e), "traceback": tb, "jsonld": {"@context": "https://schema.org", "@type": "Thing"}})

        asyncio.create_task(runner())
        jobs.append({"job_id": job_id, "url": row.get("url","")})

    return templates.TemplateResponse("batch_run.html", {"request": request, "jobs": jobs})

@router.get("/events/{job_id}")
async def events(job_id: str):
    # Lazy import to avoid hard dependency at import time
    from app.services.progress import get_job

    async def event_stream():
        last_len = 0
        for _ in range(900):  # ~15 minutes
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
    # Lazy imports
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
