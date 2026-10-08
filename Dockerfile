# Canonical build path for Railway.
#
# Railway auto-detects and PREFERS a committed Dockerfile over its Railpack
# builder, regardless of the service's builder setting (verified 2026-10-07:
# every deployment reports `builder: DOCKERFILE`, even with the service builder
# pinned to RAILPACK). This Dockerfile is therefore the real build path, not a
# fallback. To switch to Railpack, delete this file from the repo.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DJANGO_SETTINGS_MODULE=stock_guard.settings

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

RUN uv run python manage.py collectstatic --noinput

# Use the shell form so $PORT is expanded at runtime; Railway injects the
# port it expects the container to listen on.
CMD uv run gunicorn --bind 0.0.0.0:${PORT:-8000} stock_guard.wsgi:application
