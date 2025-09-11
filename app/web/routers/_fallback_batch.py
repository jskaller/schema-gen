from __future__ import annotations
import uuid, asyncio, traceback
from fastapi import APIRouter, Request, Depends, Form, UploadFile, File
from fastapi.templating import Jinja2Templates
from starlette.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
import httpx

from app.db import get_session
from app.services.settings import get_settings
from app.services.csv_ingest import parse_csv
from app.services.progress import create_job, update_job, finish_job
# Lazy import to avoid circular/import-time errors during router discovery
def _get_process_single():
    from app.main_part2 import _process_single as _ps
    return _ps

templates = Jinja2Templates(directory="app/web/templates")
router = APIRouter()

@router.get("/batch", response_class=HTMLResponse)
async def batch_page(request: Request, session: AsyncSession = Depends(get_session)):
    settings = await get_settings(session)
    return templates.TemplateResponse("batch.html", {"request": request, "settings": settings})

@router.post("/batch/fetch_async", response_class=HTMLResponse)
async def batch_fetch_async(request: Request, csv_url: str = Form(...), session: AsyncSession = Depends(get_session)):
    # Download CSV and enqueue per-row jobs
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
                    job_id=job_id,
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

        async def runner(row=row, job_id=job_id):
            try:
                await update_job(job_id, 3, "Queued")
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
                    job_id=job_id,
                )
                await finish_job(job_id, result)
            except Exception as e:
                tb = traceback.format_exc()
                await update_job(job_id, 100, f"Error: {e}")
                await finish_job(job_id, {"url": row.get("url",""), "error": str(e), "traceback": tb, "jsonld": {"@context": "https://schema.org", "@type": "Thing"}})

        asyncio.create_task(runner())
        jobs.append({"job_id": job_id, "url": row.get("url","")})

    return templates.TemplateResponse("batch_run.html", {"request": request, "jobs": jobs})
