
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.datastructures import URL

from app.services.fetch import fetch_url
from app.services.extract import extract_clean_text
from app.services.ai import get_provider, GenerationInputs
from app.services.validate import validate_against_schema
from app.services.score import score_jsonld
from app.services.signals import extract_signals
from app.services.refine import refine_to_perfect

from pathlib import Path
hospital_schema = Path("app/schemas/hospital.schema.json").read_text()

app = FastAPI(title="Schema Gen", version="0.3.0")
templates = Jinja2Templates(directory="app/web/templates")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, ok: str | None = None, error: str | None = None):
    return templates.TemplateResponse("index.html", {"request": request, "ok": ok, "error": error})

@app.post("/submit", response_class=HTMLResponse)
async def submit(
    request: Request,
    url: str = Form(...),
    topic: str | None = Form(None),
    subject: str | None = Form(None),
    audience: str | None = Form(None),
    address: str | None = Form(None),
    phone: str | None = Form(None),
):
    try:
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

        # Validate and score initial
        valid, errors = validate_against_schema(jsonld, hospital_schema)
        required = ["@context", "@type", "name", "url"]
        recommended = ["description", "telephone", "address", "audience", "dateModified", "sameAs", "medicalSpecialty"]
        overall, details = score_jsonld(jsonld, required, recommended)

        # If not perfect, refine iteratively (heuristics; real LLM refine later)
        final_jsonld, final_score, final_details, iterations = refine_to_perfect(
            base_jsonld=jsonld,
            cleaned_text=cleaned_text,
            required=required,
            recommended=recommended,
            score_fn=score_jsonld,
            max_attempts=3,
        )

        # Re-validate after refine
        final_valid, final_errors = validate_against_schema(final_jsonld, hospital_schema)

        return templates.TemplateResponse(
            "result.html",
            {
                "request": request,
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
            },
        )
    except Exception as e:
        return RedirectResponse(url=str(URL("/").include_query_params(error=str(e))), status_code=303)
