PYTHON ?= python3
PYTHONPATH := src

.PHONY: install test demo board-demo raas-demo check-generated proof-check check clean

install:
	@echo "No third-party dependencies. Pure standard library."
	@$(PYTHON) --version

test:
	@PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m unittest discover -s tests -t . -q

demo: board-demo raas-demo

board-demo:
	@PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m legal_function_os.cli --input data/sample_requests.json --out examples --period "Q2 2026 (synthetic)"

raas-demo:
	@PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m legal_function_os.raas_cli --input data/raas_deal.json --out examples --quiet
	@echo "Wrote examples/raas-deal-pack.md, .json, reviewer HTML, visual SVG, and source manifest."

check-generated:
	@PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/check_generated.py

proof-check:
	@$(PYTHON) scripts/check_portfolio_proof.py

check: test check-generated proof-check
	@git diff --check

clean:
	@find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
