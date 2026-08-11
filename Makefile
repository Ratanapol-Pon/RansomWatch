.PHONY: dev bot lint fmt

dev:
	uv run uvicorn apps.api.main:app --reload

bot:
	uv run python -m packages.bot.bot

lint:
	uv run ruff check .

fmt:
	uv run ruff format .
