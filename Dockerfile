# Dormant fallback builder for Railway.
#
# Railpack is the PRIMARY builder for this service. Railway "always builds with
# a Dockerfile if it finds one", so this file only takes effect if the Railway
# service builder is explicitly set to DOCKERFILE. It exists purely as a
# recoverable fallback if Railpack regresses; leave the service pinned to
# RAILPACK (see deploy-plan.md D7 / Phase 2.5) unless you need to switch.
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

CMD ["uv", "run", "gunicorn", "--bind", "0.0.0.0:8000", "stock_guard.wsgi:application"]
