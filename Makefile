.PHONY: paper-demo reproduce test lint run

paper-demo:
	scripts/paper_demo.sh

reproduce: paper-demo

test:
	scripts/test.sh

lint:
	scripts/lint.sh

run:
	scripts/start_experiment.sh
