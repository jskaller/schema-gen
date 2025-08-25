from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

app = FastAPI(title="Schema Gen", version="0.0.1")
templates = Jinja2Templates(directory="app/web/templates")


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/submit", response_class=RedirectResponse)
def submit(
    url: str = Form(...),
    topic: str | None = Form(None),
    subject: str | None = Form(None),
    audience: str | None = Form(None),
):
    # TODO: fetch(url) -> extract -> generate -> score -> store
    return RedirectResponse(url="/?ok=1", status_code=303)
