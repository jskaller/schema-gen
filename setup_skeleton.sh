#!/usr/bin/env bash
set -euo pipefail

echo "==> Creating directories"
mkdir -p app/web/templates

echo "==> Writing .gitignore"
cat > .gitignore <<'EOF'
# Python
.venv/
__pycache__/
.pytest_cache/
*.pyc

# OS / tools
.DS_Store
.vscode/
*.log

# App
*.sqlite*
*.db
playwright/.cache/
EOF

echo "==> Writing Makefile"
cat > Makefile <<'EOF'
PY?=python3

.PHONY: setup dev run fmt

setup:
	$(PY) -m venv .venv
	. .venv/bin/activate && $(PY) -m pip install -U pip
	. .venv/bin/activate && $(PY) -m pip install -e .
	. .venv/bin/activate && $(PY) -m playwright install --with-deps chromium

dev:
	. .venv/bin/activate && uvicorn app.main:app --reload

run:
	. .venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8000

fmt:
	. .venv/bin/activate && ruff format && ruff check --fix
EOF

echo "==> Writing README.md"
cat > README.md <<'EOF'
# schema-gen

This repository uses a simple *patch drop* / small-commit workflow.

## Quickstart (macOS Apple Silicon)

```bash
xcode-select --install || true
python3 -m venv .venv
. .venv/bin/activate
pip install -U pip
pip install -e .
python -m playwright install --with-deps chromium
uvicorn app.main:app --reload
# open http://127.0.0.1:8000
```

## What’s here
- FastAPI app with one route and a Jinja/Bootstrap UI
- Form for single-URL input (processing is a no-op for now)

We’ll add fetch → extract → generate → score in follow-up patches.
EOF

echo "==> Writing Python package files"
: > app/__init__.py
: > app/web/__init__.py

cat > app/main.py <<'EOF'
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
EOF

echo "==> Writing templates"
cat > app/web/templates/base.html <<'EOF'
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{% block title %}Schema Gen{% endblock %}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  </head>
  <body>
    <nav class="navbar navbar-dark bg-dark">
      <div class="container">
        <a class="navbar-brand" href="/">Schema Gen</a>
      </div>
    </nav>
    <main class="container py-4">
      {% block content %}{% endblock %}
    </main>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
  </body>
</html>
EOF

cat > app/web/templates/index.html <<'EOF'
{% extends "base.html" %}
{% block title %}Schema Gen – Home{% endblock %}
{% block content %}
<div class="card shadow-sm">
  <div class="card-body">
    <h5 class="card-title">Generate Schema from a URL</h5>
    <form method="post" action="/submit" class="mt-3">
      <div class="mb-3">
        <label class="form-label">Page URL</label>
        <input type="url" name="url" class="form-control" placeholder="https://example.org/page" required>
      </div>
      <div class="row">
        <div class="col-md-6 mb-3">
          <label class="form-label">Topic/Keyword (optional)</label>
          <input type="text" name="topic" class="form-control" placeholder="oncology, cardiology, ...">
        </div>
        <div class="col-md-6 mb-3">
          <label class="form-label">Subject (optional)</label>
          <input type="text" name="subject" class="form-control" placeholder="Hospital name, department, etc.">
        </div>
      </div>
      <div class="mb-3">
        <label class="form-label">Intended audience (optional)</label>
        <select class="form-select" name="audience">
          <option value="">-- Select --</option>
          <option value="professional">Professional</option>
          <option value="patient">Patient</option>
          <option value="student">Student</option>
        </select>
      </div>
      <button class="btn btn-primary" type="submit">Generate</button>
    </form>
  </div>
</div>
{% endblock %}
EOF

echo "==> Writing pyproject.toml"
cat > pyproject.toml <<'EOF'
[project]
name = "schema-gen"
version = "0.0.1"
description = "AI-assisted web page schema generator"
requires-python = ">=3.11"
dependencies = [
  "fastapi>=0.112",
  "uvicorn[standard]>=0.30",
  "jinja2>=3.1",
  "pydantic>=2.8",
  "httpx>=0.27",
  "playwright>=1.45",
  "beautifulsoup4>=4.12",
  "lxml>=5.2",
  "readability-lxml>=0.8",
  "sqlmodel>=0.0.21",
  "aiosqlite>=0.20",
  "python-multipart>=0.0.9",
  "python-dotenv>=1.0",
  "jsonschema>=4.23",
  "pyld>=2.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
EOF

echo "==> Done."
echo "Next steps:"
echo "  git add -A"
echo '  git commit -m "feat: seed minimal FastAPI+Bootstrap skeleton (Apple Silicon)"'
echo "  git push -u origin main"
echo "  make setup && make dev"
