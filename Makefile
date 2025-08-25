PY?=python3

.PHONY: setup dev run fmt

setup:
	$(PY) -m venv .venv
	. .venv/bin/activate && $(PY) -m pip install -U pip wheel
	. .venv/bin/activate && $(PY) -m pip install -r requirements.txt
	. .venv/bin/activate && $(PY) -m playwright install --with-deps chromium
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
