PYTHON ?= $(shell if [ -x backend/.venv/bin/python ]; then echo "$(CURDIR)/backend/.venv/bin/python"; else echo python3; fi)
DAYS ?= 90
SYMBOL ?= BTCUSDT
INTERVAL ?= 1m
TARGET_POINTS ?= 129600

.PHONY: paper-demo reproduce prefill run-v1 v1-autopilot run-90d v1-compare v1-confidence v1-regime report test lint run

paper-demo:
	scripts/paper_demo.sh

reproduce: paper-demo

prefill:
	cd backend && "$(PYTHON)" scripts/prefill_history.py --days "$(DAYS)" --symbol "$(SYMBOL)" --interval "$(INTERVAL)" --target-points "$(TARGET_POINTS)"

run-v1:
	cd backend && "$(PYTHON)" run_v1_experiment.py

v1-autopilot: prefill
	cd backend && "$(PYTHON)" run_v1_experiment.py --all-models --auto-resume --auto-pull-models

run-90d:
	cd backend && "$(PYTHON)" scripts/run_90d_experiment.py --max-points "$(TARGET_POINTS)"

v1-compare:
	cd backend && "$(PYTHON)" scripts/v1_compare.py

v1-confidence:
	cd backend && "$(PYTHON)" scripts/confidence_analysis.py --experiment-name v1-live

v1-regime:
	cd backend && "$(PYTHON)" scripts/regime_analysis.py --experiment-name v1-live

report:
	cd backend && "$(PYTHON)" -c "from reports.generate_report import generate_markdown_report; generate_markdown_report(1, '../artifacts/90d_real/report.md')"

test:
	scripts/test.sh

lint:
	scripts/lint.sh

run:
	scripts/start_experiment.sh
