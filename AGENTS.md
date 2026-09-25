# Repository Guidelines

Stock Guard is a greenfield Django 6.1 web app (Python 3.12, dependency-managed by `uv`) that flags bearish reversal formations — double top and RGR — on a watchlist's price series. Product truth lives in `@context/foundation/prd.md` and `@context/foundation/tech-stack.md`; read them before non-trivial work.

## Hard rules

- `context/` is the bootstrap chain's source of truth. Never modify files the scaffold dropped under `context/archive/` (archived changes are immutable). Treat `context/foundation/{prd,tech-stack,shape-notes}.md` as canonical product intent.
- Detection logic stays in a service module named `score_formation(price_series)` — keep formation math out of Django views/templates so models and detection survive a future API/SPA migration.
- `@pyproject.toml` pins `django>=6.1.1` and `requires-python = ">=3.12"`. Add dependencies there, not via bare `pip install`; regenerate `@uv.lock` with `uv lock`.
- Settings commit a dev-only secret key and `DEBUG = True` in `@stock_guard/settings.py`; never change those for deployment without a secrets/env split.

## Project structure

Django startproject layout: `@manage.py` at root, `@stock_guard/settings.py|urls.py|asgi.py|wsgi.py` as the project package (`DJANGO_SETTINGS_MODULE = stock_guard.settings`). The PRD foresees feature apps, a service layer for detection, and Pydantic-validated request boundaries when an API lands. Register new Django apps in `INSTALLED_APPS`; SQLite (`db.sqlite3`) is the dev DB, Postgres the hand-off target on Railway.

## Build, test, and development commands

- `uv lock` then `uv sync` — install/reconcile pinned deps.
- `uv run python manage.py runserver` — dev server.
- `uv run python manage.py makemigrations && uv run python manage.py migrate` — schema changes.
- `uv run python manage.py createsuperuser` — admin access.
- `uv run python manage.py test` — Django test runner (no tests yet; add them alongside feature apps).

## Coding style & conventions

- Add type hints at function and service boundaries (the stack is untyped at runtime, so hints carry the weight here). Use Pydantic models to validate any API request payloads.
- No lint/format config exists yet. When adding one, prefer `ruff` config in `@pyproject.toml` rather than a separate file.

## Testing guidelines

No test config is committed. Write Django `TestCase` subclasses inside each app's `tests.py`, runnable with `uv run python manage.py test <app_label>`.

## Commit & pull request guidelines

No fixed convention is visible yet in `git log` (initial scaffold commits only). Use short imperative summaries until one is adopted. No `.github/workflows/` or test step exists; the hand-off intends GitHub Actions auto-deploy-on-merge with `mypy` enforcement — wire that up before relying on a CI check.
