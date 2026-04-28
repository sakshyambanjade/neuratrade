.PHONY: paper-demo test lint

paper-demo:
	scripts/paper_demo.sh

test:
	scripts/test.sh

lint:
	scripts/lint.sh
