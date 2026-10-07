# Dormant fallback builder for Railway.
#
# Railpack is the intended PRIMARY builder for this service, but Railway
# auto-detects a Dockerfile and prefers it whenever one is present (verified
# 2026-10-07: a local `railway up` built via this Dockerfile even with the
# service builder pinned to RAILPACK). Kept as a working, correct build path so
# either builder produces a reachable container.
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
