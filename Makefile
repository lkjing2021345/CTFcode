.PHONY: test lint run fmt

test:
	./venv/bin/python tests/smoke.py

lint:
	./venv/bin/ruff check ctfcode main.py scripts

fmt:
	./venv/bin/ruff check --fix ctfcode main.py scripts

run:
	./bin/ctfcode
