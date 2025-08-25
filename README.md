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
