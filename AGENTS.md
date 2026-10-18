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

## 10xDevs AI Toolkit - Module 2, Lesson 4

Prepare for a harder implementation stream with the **research-backed planning chain**:

```
internal research (/10x-research) + external research (exa.ai, Context7) -> /10x-plan -> /10x-implement -> success
```

The lesson focus is distinguishing internal from external research and using evidence to back planning decisions.

### Task Router - Where to start

| Skill | Use it when |
| --- | --- |
| **Internal research (lesson focus)** | |
| `/10x-research <change-id>` | You need evidence from the existing codebase — patterns, conventions, integration points, or existing implementations. Runs parallel sub-agents over the repo and writes structured findings to `research.md`. |
| **External research (lesson focus)** | |
| exa.ai | You need AI-native web search for library comparisons, best practices, or ecosystem context that the codebase cannot answer. |
| Context7 (`resolve-library-id` → `get-library-docs`) | You need live, current documentation for a specific library or framework. Resolves a library ID first, then fetches relevant doc pages. |
| **Framing spare wheel** | |
| `/10x-frame <change-id>` | The plan won't converge, the plan doesn't deliver expected results, or persistent drift keeps breaking the implementation. Use as an escape hatch on a separate problem (demonstrated on Space Explorers example), not as pre-research ritual. |
| **Planning and execution** | |
| `/10x-plan <change-id>` / `/10x-implement <change-id> phase <n>` | Use the same planning and execution chain from Lesson 2, now with upstream research evidence feeding the plan. |

### Research discipline

- Internal research (`/10x-research`) answers "what does our codebase already do?" — patterns, schemas, conventions, integration points.
- External research (exa.ai, Context7) answers "what should we do?" — library capabilities, API docs, ecosystem best practices.
- Combine both as evidence-backed input to `/10x-plan`. A plan without research evidence on a non-trivial stream is a guess.
- Agent-friendly docs (`llms.txt`, markdown-for-agents, `/md` endpoints) are a quality signal for library selection — libraries that publish agent-readable docs integrate faster.

### `/10x-frame` as spare wheel

Three triggers for reaching for `/10x-frame`:
1. The plan won't converge — research keeps opening more questions instead of narrowing to a contract.
2. The plan doesn't deliver — implementation repeatedly fails to meet success criteria.
3. Persistent drift — the implementation keeps diverging from the plan in ways that suggest the problem was mis-framed.

Demonstrated on a Space Explorers example, not the SRS path. It is an escape hatch, not a mandatory step.

### Paths used by this lesson

- `context/changes/<change-id>/research.md` - internal research output
- `context/changes/<change-id>/frame.md` - framing output when needed
- `context/changes/<change-id>/plan.md` - evidence-backed implementation contract
- `context/foundation/lessons.md` - recurring rules and pitfalls

Skills must not write to `context/archive/`. Archived changes are immutable; if a resolved target path starts with `context/archive/`, abort with: "This change is archived. Open a new change with `/10x-new` instead."

<!-- END @przeprogramowani/10x-cli -->
