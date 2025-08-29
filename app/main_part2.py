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
