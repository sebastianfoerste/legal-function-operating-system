PYTHON ?= python3
PYTHONPATH := src

.PHONY: install test demo clean

install:
	@echo "No third-party dependencies. Pure standard library."
	@$(PYTHON) --version

test:
	@PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m unittest discover -s tests -t . -q

demo:
	@PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m legal_function_os.cli --input data/sample_requests.json --out examples --period "Q2 2026 (synthetic)"

clean:
	@find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
