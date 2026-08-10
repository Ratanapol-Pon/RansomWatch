.PHONY: dev lint fmt

dev:
	uv run uvicorn apps.api.main:app --reload

lint:
	uv run ruff check .

fmt:
	uv run ruff format .
