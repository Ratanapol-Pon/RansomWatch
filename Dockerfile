FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev

COPY packages/ packages/
COPY apps/ apps/

ENV PATH="/app/.venv/bin:$PATH"

# SERVICE_MODULE selects which service to run:
#   bot service      -> default (packages.bot.bot)
#   scraper service  -> set SERVICE_MODULE=packages.scraper.run in Railway variables
#   dashboard API    -> set SERVICE_MODULE=apps.api.main and API_PORT to host port
#   LINE worker      -> set SERVICE_MODULE=packages.line.worker
ENV SERVICE_MODULE=packages.bot.bot

CMD python -m "$SERVICE_MODULE"
