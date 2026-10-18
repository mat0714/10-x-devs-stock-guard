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

## 10xDevs AI Toolkit - Module 2, Lesson 3

Review AI-generated code before merge with the **implementation review chain**:

```
/10x-implement -> /10x-impl-review -> triage -> (/10x-lesson | fix | skip | disagree)
```

`/10x-impl-review` is the lesson focus. Review is a quality gate, not an instruction to fix every finding.

### Task Router - Where to start

| Skill | Use it when |
| --- | --- |
| **Code review (lesson focus)** | |
| `/10x-impl-review <change-id>` | You have implemented code and want a structured review before merge. The skill checks plan adherence, scope discipline, safety and quality, architecture, pattern consistency, and success criteria, then presents findings for triage. |
| **Recurring lesson outcome** | |
| `/10x-lesson` | A finding reveals a recurring project rule or agent failure pattern. Record it in `context/foundation/lessons.md` instead of treating it as a one-off note. |

### Triage discipline

- Severity says how bad the finding is. Impact says how much the decision matters now.
- Valid outcomes: fix now, fix differently, skip, accept as risk, record as recurring rule (`/10x-lesson`), disagree.
- Fix critical findings. Do not burn hours on low-impact observations just because the agent found them.
- Conscious skipping of low-impact findings is a valid review outcome, not negligence.
- If you disagree with a finding, record why. Wrong agent reasoning is also signal.

### Review boundaries

- This lesson reviews implemented code. It does not create the plan, execute new phases, or teach CI review.
- Testing strategy and quality gates are introduced in Module 3.
- Do not use `/10x-contract` as a triage outcome in this lesson.

### Paths used by this lesson

- `context/changes/<change-id>/plan.md` - expected implementation contract
- `context/changes/<change-id>/reviews/` - review output
- `context/foundation/lessons.md` - recurring lessons

Skills must not write to `context/archive/`. Archived changes are immutable; if a resolved target path starts with `context/archive/`, abort with: "This change is archived. Open a new change with `/10x-new` instead."

<!-- END @przeprogramowani/10x-cli -->
