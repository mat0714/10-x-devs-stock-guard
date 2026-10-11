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

## 10xDevs AI Toolkit - Module 2, Lesson 2

Turn one roadmap item into the first implementation cycle with the **change planning chain**:

```
/10x-roadmap -> /10x-new -> /10x-plan -> /10x-plan-review -> /10x-implement
```

`/10x-new`, `/10x-plan`, `/10x-plan-review`, and `/10x-implement` are the lesson focus. `/10x-frame` and `/10x-research` are not required rituals here; they are escalation paths introduced in the next lesson.

### Task Router - Where to start

| Skill | Use it when |
| --- | --- |
| **Change setup (lesson focus)** | |
| `/10x-new <change-id>` | You selected a roadmap item and need a stable change folder. Creates `context/changes/<change-id>/change.md` so planning, implementation, progress, commits, and later review all share one identity. Use AFTER roadmap selection, BEFORE `/10x-plan`. |
| **Planning (lesson focus)** | |
| `/10x-plan <change-id>` | You have a change folder and need a reviewable implementation plan. Reads roadmap context, foundation docs, codebase evidence, and any existing change notes; writes `plan.md` and `plan-brief.md` with phases, file contracts, success criteria, and `## Progress`. |
| **Plan readiness (lesson focus)** | |
| `/10x-plan-review <change-id>` | You have `plan.md` and need a light pre-code readiness check. Use it to catch missing end state, weak contracts, malformed progress, scope drift, or blind spots before code changes begin. |
| **Implementation (lesson focus)** | |
| `/10x-implement <change-id> phase <n>` | You have an approved plan and want to execute one phase with verification, manual gate, commit ritual, and SHA write-back to `## Progress`. |
| **Lifecycle closure** | |
| `/10x-archive <change-id>` | A change is merged or intentionally closed. Move it out of active `context/changes/` into archive state. |

### How the chain hands off

- `/10x-new` creates the durable change identity.
- `/10x-plan` turns that identity into an implementation contract.
- `/10x-plan-review` checks the plan before the agent mutates code.
- `/10x-implement` executes one planned phase, verifies, asks for manual confirmation when needed, commits, and records progress.

### Lesson boundaries

- Plan is the default router after roadmap selection. Start with `/10x-plan` unless the problem is unclear or external evidence is blocking.
- Do not run `/10x-frame + /10x-research` as ceremony for every change.
- Do not turn this lesson into a full end-to-end product build. A checkpoint with a planned and partially or fully implemented stream is valid.
- Code review of the implemented diff belongs to Lesson 3 via `/10x-impl-review`.
- Lifecycle closure via `/10x-archive` after a change is merged or intentionally closed.

### Paths used by this lesson

- `context/foundation/roadmap.md` - upstream roadmap
- `context/changes/<change-id>/change.md` - change identity
- `context/changes/<change-id>/plan.md` - implementation contract
- `context/changes/<change-id>/plan-brief.md` - compressed handoff
- `context/foundation/lessons.md` - recurring rules and pitfalls
- `docs/reference/contract-surfaces.md` - load-bearing names registry

Skills must not write to `context/archive/`. Archived changes are immutable; if a resolved target path starts with `context/archive/`, abort with: "This change is archived. Open a new change with `/10x-new` instead."

<!-- END @przeprogramowani/10x-cli -->
