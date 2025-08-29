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
    timeout_s, interval_s = 25, 0.5
    waited = 0.0
    job = await get_job(job_id)
    while job and not job.get("result") and (job.get("progress", 0) < 100) and waited < timeout_s:
        await asyncio.sleep(interval_s)
        waited += interval_s
        job = await get_job(job_id)

    if not job:
        return templates.TemplateResponse("progress.html", {"request": request, "job_id": job_id, "error": "Unknown or expired job."})

    if not job.get("result"):
        return templates.TemplateResponse("progress.html", {"request": request, "job_id": job_id})

    result = job["result"]
    try:
        await record_run(session, result)
    except Exception as e:
        print(f"[history write failed] {e}", file=sys.stderr)
    return templates.TemplateResponse("result.html", {"request": request, **result})
