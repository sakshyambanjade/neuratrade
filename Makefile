.PHONY: paper-demo test lint run

paper-demo:
	scripts/paper_demo.sh

test:
	scripts/test.sh

lint:
	scripts/lint.sh

run:
	scripts/start_experiment.sh
