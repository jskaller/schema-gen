from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.datastructures import URL

from app.services.fetch import fetch_url
from app.services.extract import extract_clean_text
from app.services.ai import get_provider, GenerationInputs
from app.services.validate import validate_against_schema
from app.services.score import score_jsonld

# Load schema file
from pathlib import Path
hospital_schema = Path("app/schemas/hospital.schema.json").read_text()

app = FastAPI(title="Schema Gen", version="0.1.0")
templates = Jinja2Templates(directory="app/web/templates")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, ok: str | None = None, error: str | None = None):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "ok": ok, "error": error},
    )


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

        # Generate JSON-LD via provider
        provider = get_provider("dummy")
        payload = GenerationInputs(
            url=url,
            cleaned_text=cleaned_text,
            topic=topic,
            subject=subject,
            audience=audience,
            address=address,
            phone=phone,
            page_type="Hospital",
        )
        jsonld = provider.generate_jsonld(payload)

        # Validate against our minimal schema
        valid, errors = validate_against_schema(jsonld, hospital_schema)

        # Score
        required = ["@context", "@type", "name", "url"]
        recommended = ["description", "telephone", "address", "audience", "dateModified"]
        overall, details = score_jsonld(jsonld, required, recommended)

        return templates.TemplateResponse(
            "result.html",
            {
                "request": request,
                "url": url,
                "topic": topic,
                "subject": subject,
                "audience": audience,
                "address": address,
                "phone": phone,
                "excerpt": cleaned_text[:2000],
                "length": len(cleaned_text),
                "jsonld": jsonld,
                "valid": valid,
                "validation_errors": errors,
                "overall": overall,
                "details": details,
            },
        )
    except Exception as e:
        return RedirectResponse(
            url=str(URL("/").include_query_params(error=str(e))), status_code=303
        )
