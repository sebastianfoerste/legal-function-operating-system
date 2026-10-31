PYTHON ?= python3
PYTHONPATH := src

.PHONY: install install-dev test lint package-check demo board-demo raas-demo contracts site site-check check-generated manifest-check contract-check agent-check agent-export check clean

install:
	@echo "No third-party dependencies. Pure standard library."
	@$(PYTHON) --version

# The pinned tools behind `make lint` and `make check` (the agent gate included).
install-dev:
	@$(PYTHON) -m pip install -r requirements-dev.txt
	@$(MAKE) -C supervised-agent install PYTHON=$(PYTHON)

test:
	@PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m unittest discover -s tests -t . -q

# Needs the pinned tools: $(PYTHON) -m pip install -r requirements-dev.txt
lint:
	@$(PYTHON) -m ruff check src/legal_function_os scripts
	@$(PYTHON) -m mypy

# Builds the wheel, installs it in a fresh virtual environment and runs it there.
package-check:
	@$(PYTHON) scripts/check_package.py

demo: board-demo raas-demo

board-demo:
	@PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m legal_function_os.cli --input src/legal_function_os/data/sample_requests.json --out examples --period "Q2 2026 (synthetic)" --capacity-scenarios src/legal_function_os/data/capacity_scenarios.json --capacity-output examples --events-input src/legal_function_os/data/service_events.json --outcome-config src/legal_function_os/data/outcome_config.json --outcome-output examples --approval-matrix-output examples

raas-demo:
	@PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m legal_function_os.raas_cli --input src/legal_function_os/data/raas_deal.json --out examples --quiet
	@echo "Wrote examples/raas-deal-pack.md, .json, reviewer HTML, visual SVG, and source manifest."

contracts:
	@$(PYTHON) scripts/build_contracts.py

site:
	@$(PYTHON) scripts/build_site.py

site-check: site
	@$(PYTHON) scripts/check_site_links.py

check-generated:
	@PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/check_generated.py

manifest-check:
	@$(PYTHON) scripts/check_verification_manifest.py

contract-check:
	@$(PYTHON) scripts/check_shared_contracts.py

agent-check:
	@$(MAKE) -C supervised-agent check

agent-export:
	@scripts/export-supervised-agent.sh

check: test check-generated manifest-check contract-check site-check agent-check
	@git diff --check

clean:
	@find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
