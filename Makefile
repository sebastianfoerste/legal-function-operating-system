PYTHON ?= python3
PYTHONPATH := src

.PHONY: install test demo board-demo raas-demo site check-generated manifest-check contract-check agent-check agent-export check clean

install:
	@echo "No third-party dependencies. Pure standard library."
	@$(PYTHON) --version

test:
	@PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m unittest discover -s tests -t . -q

demo: board-demo raas-demo

board-demo:
	@PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m legal_function_os.cli --input src/legal_function_os/data/sample_requests.json --out examples --period "Q2 2026 (synthetic)" --capacity-scenarios src/legal_function_os/data/capacity_scenarios.json --capacity-output examples --events-input src/legal_function_os/data/service_events.json --outcome-config src/legal_function_os/data/outcome_config.json --outcome-output examples

raas-demo:
	@PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m legal_function_os.raas_cli --input src/legal_function_os/data/raas_deal.json --out examples --quiet
	@echo "Wrote examples/raas-deal-pack.md, .json, reviewer HTML, visual SVG, and source manifest."

site:
	@$(PYTHON) scripts/build_site.py

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

check: test check-generated manifest-check contract-check agent-check
	@git diff --check

clean:
	@find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
