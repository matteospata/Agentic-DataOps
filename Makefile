.PHONY: install test lint format run ingest ask

install:
	python -m pip install -e '.[dev,llm]'

test:
	pytest

lint:
	ruff check .

format:
	ruff format .

run:
	uvicorn agentic_dataops.api:app --reload --host 0.0.0.0 --port 8000

ingest:
	python -m agentic_dataops.cli profile --dataset sales_demo.csv

ask:
	python -m agentic_dataops.cli ask --dataset sales_demo.csv "Compare revenue by region and check data quality."

