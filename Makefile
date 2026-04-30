PYTHON ?= $(shell if [ -x backend/.venv/bin/python ]; then echo "$(CURDIR)/backend/.venv/bin/python"; else echo python3; fi)
DAYS ?= 7
SYMBOL ?= BTCUSDT
INTERVAL ?= 1m

.PHONY: paper-demo reproduce prefill test lint run

paper-demo:
	scripts/paper_demo.sh

reproduce: paper-demo

prefill:
	cd backend && "$(PYTHON)" scripts/prefill_history.py --days "$(DAYS)" --symbol "$(SYMBOL)" --interval "$(INTERVAL)"

test:
	scripts/test.sh

lint:
	scripts/lint.sh

run:
	scripts/start_experiment.sh
