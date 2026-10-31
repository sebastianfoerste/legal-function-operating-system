PYTHON := $(shell if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python; fi)

.PHONY: lock install check test lint format compile

lock:
	uv pip compile requirements.in -o requirements.txt --python-version 3.13

install:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt -r requirements-dev.txt

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m black --check .
	$(PYTHON) -m mypy .

test:
	$(PYTHON) -m pytest -q

compile:
	$(PYTHON) -m compileall master_orchestrator.py models.py src runtime_agent tests

check: lint test compile

format:
	$(PYTHON) -m ruff check --fix .
	$(PYTHON) -m black .
