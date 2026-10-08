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
<!-- BEGIN @przeprogramowani/10x-cli -->

## 10xDevs AI Toolkit - Module 2, Lesson 1

Move from sprint-zero setup to project orchestration with the **roadmap chain**:

```
(Module 1 foundation docs) -> /10x-roadmap -> backlog-ready roadmap items
```

`/10x-roadmap` is the lesson focus. `/10x-new` is intentionally introduced in Module 2, Lesson 2, when a selected roadmap item becomes an implementation change folder.

### Task Router - Where to start

| Skill | Use it when |
| --- | --- |
| **Roadmap (lesson focus)** | |
| `/10x-roadmap` | You have `context/foundation/prd.md` and a scaffolded project baseline, and you need a vertical-first MVP roadmap. The skill reads the PRD, inspects the code baseline, uses available foundation docs such as `tech-stack.md`, `infrastructure.md`, and `deploy-plan.md`, then writes `context/foundation/roadmap.md`. Use it BEFORE creating per-change folders or implementation plans. |
| **Re-run upstream if needed** | |
| `/10x-shape` / `/10x-prd` / `/10x-tech-stack-selector` / `/10x-bootstrapper` / `/10x-agents-md` / `/10x-infra-research` | Bundled from Module 1 so foundation contracts can be fixed before roadmap sequencing. If roadmap generation exposes a PRD gap, repair the PRD before pretending the backlog is ready. |

### How the chain hands off

- `/10x-roadmap` bridges product and implementation. It does not choose frameworks, design schemas, or write a per-change implementation plan.
- The output is `context/foundation/roadmap.md`: ordered milestones, vertical slices, bounded foundations, dependencies, unknowns, risk, and backlog handoff fields.
- Roadmap items should receive stable human-readable identifiers in backlog tools. The actual `context/changes/<change-id>/` folder is created in Lesson 2 with `/10x-new`.

### Roadmap boundaries

- Default to vertical slices: user-visible outcomes that cross UI, data, business logic, and integrations.
- Horizontal work is allowed only as a bounded enabler that names the downstream vertical milestone it unlocks.
- Avoid orphan horizontal work such as "build the whole database", "build all API endpoints", or "design the whole UI" before the first user-visible flow.
- Roadmap is not a calendar estimate. Do not invent dates, story points, or sprint velocity unless the user explicitly asks for a separate planning artifact.

### Foundation paths used by this lesson

- `context/foundation/prd.md` - input
- `context/foundation/tech-stack.md` - optional input
- `context/foundation/infrastructure.md` - optional input
- `context/deployment/deploy-plan.md` - optional input
- `context/foundation/roadmap.md` - output
- `context/foundation/lessons.md` - recurring rules and pitfalls
- `docs/reference/contract-surfaces.md` - load-bearing names registry

Skills must not write to `context/archive/`. Archived changes are immutable; if a resolved target path starts with `context/archive/`, abort with: "This change is archived. Open a new change with `/10x-new` instead."

<!-- END @przeprogramowani/10x-cli -->
