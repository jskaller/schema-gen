
from fastapi import FastAPI, Request, Form, UploadFile, File, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.datastructures import URL

import io, csv, json
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
from app.services.geocode import geocode_postal_address

app = FastAPI(title="Schema Gen", version="1.7.0")
templates = Jinja2Templates(directory="app/web/templates")

@app.on_event("startup")
async def _startup():
    await init_db()

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

async def _process_single(
    url: str, topic, subject, audience, address, phone, compare_existing, competitor1, competitor2, label,
    session: AsyncSession
):
    raw_html = await fetch_url(url)
    cleaned_text = extract_clean_text(raw_html)
    sig = extract_signals(raw_html)

    page_label, primary_type, secondary_types, s = await resolve_types(session, label)
    provider = get_provider(s.provider or "dummy", model=s.provider_model or None)

    # Attempt geocoding if we have a postal address (form input overrides signals if present)
    addr_input = address or (sig.get("address") if isinstance(sig, dict) else None)
    geo = None
    if isinstance(addr_input, dict):
        geo = await geocode_postal_address(addr_input)

    payload = GenerationInputs(
        url=url, cleaned_text=cleaned_text, topic=topic, subject=subject, audience=audience,
        address=addr_input, phone=phone or (sig.get("phone") if isinstance(sig, dict) else None),
        sameAs=(sig.get("sameAs") if isinstance(sig, dict) else None),
        page_type=primary_type,
    )
    base_jsonld = await provider.generate_jsonld(payload)

    inputs = {"topic": topic, "subject": subject, "address": addr_input, "phone": phone, "url": url, "geo": geo}
    primary_node = normalize_jsonld(base_jsonld, primary_type, inputs)

    final_jsonld = assemble_graph(primary_node, secondary_types, url, inputs) if secondary_types else primary_node

    schema_json = load_schema(primary_type)
    effective_required = (s.required_fields or defaults_for(primary_type)["required"])
    effective_recommended = (s.recommended_fields or defaults_for(primary_type)["recommended"])

    root_node = final_jsonld["@graph"][0] if isinstance(final_jsonld, dict) and "@graph" in final_jsonld else final_jsonld
    valid, errors = validate_against_schema(root_node, schema_json)
    overall, details = score_jsonld(root_node, effective_required, effective_recommended)

    # Advice moved into score/validate context; keep details minimal here
    from app.services.advice import advise
    tips = advise(root_node, effective_required, effective_recommended)

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
