---
bootstrapped_at: 2026-09-23T18:54:21Z
starter_id: django
starter_name: Django
project_name: stock-guard
language_family: python
package_manager: uv
cwd_strategy: native-cwd
bootstrapper_confidence: verified
phase_3_status: ok
audit_command: pip-audit --format json
---

## Hand-off

Verbatim copy of `context/foundation/tech-stack.md`.

Frontmatter:

```yaml
starter_id: django
package_manager: uv
project_name: stock-guard
hints:
  language_family: python
  team_size: solo
  deployment_target: railway
  ci_provider: github-actions
  ci_default_flow: auto-deploy-on-merge
  bootstrapper_confidence: verified
  path_taken: custom
  quality_override: true
  self_check_answers:
    typed: false
    from_official_starter: true
    conventions: true
    docs_current: true
    can_judge_agent: false
  has_auth: true
  has_payments: false
  has_realtime: false
  has_ai: false
  has_background_jobs: false
```

### Why this stack

Custom path even though Django is the recommended default for (web-app, python): the user signaled a JS frontend preference plus a backend language with strong financial-analysis libraries. Backend locked to Python for pandas + ta (double-top/RGR detection per FR-009), then Django chosen over FastAPI+React and FastAPI+Jinja because auth is a confirmed must-have (FR-001/FR-002) and Django's batteries (auth + ORM + admin + migrations) minimize assembly in a 3-week after-hours solo MVP. Detection logic stays in a service module (`score_formation(price_series)`) so a future Django-templates-to-SPA migration is bounded — add Django Ninja/DRF for the API, swap session auth for JWT, keep models and detection intact. Django fails the typed agent-friendly gate (duck-typed at runtime); user accepted (quality_override: true) with compensation via AGENTS.md: type hints at boundaries + Pydantic for request validation + mypy in CI. Deployment lands on Railway Hobby — single vendor for Django app + managed Postgres, ~$7-8/mo realistic for low-traffic solo, no cold starts; picked over Render Free + Neon to skip the 60s Render cold starts and over Fly.io's ~$38/mo to save ~$30/mo. GitHub Actions with auto-deploy-on-merge is the default for solo + small. Bootstrapper confidence: verified.

## Pre-scaffold verification

| Signal        | Value    | Severity | Notes                                                                           |
| ------------- | -------- | -------- | ------------------------------------------------------------------------------- |
| npm package   | not run  | —        | Non-JS starter (`language_family: python`); npm-package derivation applies only to JS-family CLIs. |
| GitHub repo   | not run  | —        | Card `docs_url` is `https://docs.djangoproject.com` (not a `github.com/<owner>/<repo>` URL); no `pushed_at` to fetch. |

Recency summary: no recency signal available (Django is a non-JS starter with a non-GitHub docs URL). Proceeded with no warning.

Resolved from `bootstrapper-config.yaml`:
- `cwd_strategy` for `django`: `native-cwd` (scaffold directly into the current directory).
- `audit_commands[python]`: `pip-audit` (invoked as `pip-audit --format json` per the per-ecosystem block).

Toolchain observed in cwd before scaffold: uv 0.11.23; project `.venv` Python 3.12.3; `pyproject.toml` from `uv init` (name `10-x-devs-stock-guard`, version `0.1.0`, `requires-python>=3.12`, `dependencies=[]`); near-empty `uv.lock`.

## Scaffold log

**Resolved invocation**: `uv run django-admin startproject stock_guard .`
**Strategy**: native-cwd
**Exit code**: 0
**Pre-flight files-to-touch**: `manage.py`, `stock_guard/__init__.py`, `stock_guard/settings.py`, `stock_guard/urls.py`, `stock_guard/wsgi.py`, `stock_guard/asgi.py`
**Files written by CLI**: 6 (`manage.py` + the `stock_guard/` package: `asgi.py`, `__init__.py`, `settings.py`, `urls.py`, `wsgi.py`)
**Pre-existing files preserved**: none overwritten — no filename overlaps. All existing files untouched: `pyproject.toml`, `uv.lock`, `.venv`, `context/` (entire chain), `AGENTS.md`, `kilo.json`, `.10x-cli.json`, `.ai/`, `.git/`, `.idea/`.

**Pre-install step** (card `pre: pip install django`): `uv add django` — exit code 0. Resolved 5 packages, installed django 6.1.1 -> asgiref 3.12.1 + sqlparse 0.6.0 into `.venv`. Updated `pyproject.toml` (`dependencies = ["django>=6.1.1"]`) and regenerated `uv.lock`. Because the repo is uv-managed (`package_manager: uv`), `uv add` was used in place of `pip install`.

**Sanity check**: `django.setup()` against `stock_guard.settings` succeeds; `settings.INSTALLED_APPS` reports the 6 default apps (contenttypes, auth, admin, sessions, messages, staticfiles). The scaffolded project imports and configures cleanly.

### Notes — deviations from the starter card's literal command shape

The starter card's `cmd_template` is `django-admin startproject {name} .`, where `{name}` is the **project-name** positional and the trailing `.` is the **target directory**. Two real constraints forced deviations from the skill's generic substitution rules; both were verified empirically (Django 6.1.1) before execution, and the user explicitly confirmed the working plan:

1. **Native-cwd `{name}` substitution is incompatible with this template.** The generic `native-cwd` rule substitutes `{name}` = `.`, which would yield `django-admin startproject . .`. Django rejects `.` as a project name (`CommandError: '.' is not a valid project name. Please make sure the name is a valid identifier.`; verified: exit 1). The project-name positional was therefore substituted with the normalized project name (see #2) and the template's directory `.` was kept, yielding `django-admin startproject stock_guard .`. Verified working: exit 0.
2. **Project name normalization.** The hand-off `project_name: stock-guard` is not a valid Python identifier (hyphen) and Django rejects it (`CommandError: 'stock-guard' is not a valid project name`; verified: exit 1). Normalized to `stock_guard` (valid identifier) as the Django project package name. The repo directory name (`10-x-devs-stock-guard`) and the `pyproject.toml` project name (`10-x-devs-stock-guard`) were left unchanged — note that the latter also cannot be a Django project name (leading digit + hyphens), which is why the hand-off's `project_name`, normalized to `stock_guard`, is the Django project name. `project_name: stock-guard` is recorded in the frontmatter above as metadata only.
3. **Conflict-policy context for native-cwd.** There is no move-up/merge step under `native-cwd` — Django writes directly into cwd. A pre-flight check (and a sandbox reproduction with a populated mimic directory) confirmed Django's output filenames (`manage.py`, `stock_guard/`) do not overlap any existing file, so no `.scaffold` siblings were created and `context/` was preserved verbatim. `.gitignore` handling: absent in scaffold (Django's `startproject` does not create a `.gitignore`) and absent in cwd (no `.gitignore` existed pre-scaffold).
4. **`uv add django` modified pre-existing manifest files.** The occupied cwd already carried a `uv init`-created `pyproject.toml` + `uv.lock` + `.venv`. `uv add django` is the uv-idiomatic equivalent of the card's `pre: pip install django` and necessarily edits `pyproject.toml` (adds `django>=6.1.1` to `dependencies`) and regenerates `uv.lock`. This is the intended persistence of django as a declared project dependency (so the scaffolded project actually ships with Django as a manifest dep). `uv pip install django` (env-only, manifest-untouched) was rejected in favor of `uv add` for this reason. The user confirmed before this mutation.

## Post-scaffold audit

**Tool**: pip-audit --format json
**Summary**: 0 CRITICAL, 0 HIGH, 0 MODERATE, 0 LOW
**Direct vs transitive**: 0 CRITICAL, 0 HIGH, 0 MODERATE, 0 LOW direct out of 0/0/0/0 total. Scaffolded Django tree audited clean: django 6.1.1 (direct), asgiref 3.12.1 (transitive via django), sqlparse 0.6.0 (transitive via django).
**Audit scope & dispatch notes**: pip-audit was run in a scratch venv holding the resolved Django project tree (`django==6.1.1`, `asgiref==3.12.1`, `sqlparse==0.6.0`) plus pip-audit's own runtime deps; the project's `.venv`, `pyproject.toml`, and `uv.lock` were not modified to run the audit. `pip-audit -r` against a pinned requirements file was blocked in this environment — `pip-audit -r` builds an isolated resolve venv via `ensurepip`, which is unavailable here (no `python3-venv`; error: "The virtual environment was not created successfully because ensurepip is not available"). Pivoted to auditing the resolved tree directly and filtering advisories to the scaffolded project's dependency set `{django, asgiref, sqlparse}`.
**pip-audit exit code**: 0 (stderr: "No known vulnerabilities found").

#### CRITICAL findings

(none)

#### HIGH findings

(none)

#### MODERATE findings

(none)

#### LOW / INFO findings

(none)

#### Raw filtered output (project tree)

```json
{"dependencies": [
  {"name": "django",  "version": "6.1.1",   "vulns": []},
  {"name": "asgiref", "version": "3.12.1",  "vulns": []},
  {"name": "sqlparse", "version": "0.6.0",  "vulns": []}
], "fixes": []}
```

(Thirty-one packages were present in the scratch audit venv; the remaining twenty-eight are pip-audit's own runtime dependencies, not part of the scaffolded project, and all carried `vulns: []`.)

## Hints recorded but not acted on

These hand-off fields were read into working memory and are preserved here for audit-trail completeness. Bootstrapper v1 surfaces them in conversation but takes **no** compensating action. Acting on them is the job of the future memory-architecture (M1L4) skill.

| Hint                        | Value                                                                                        |
| --------------------------- | -------------------------------------------------------------------------------------------- |
| bootstrapper_confidence     | verified                                                                                     |
| quality_override            | true                                                                                         |
| path_taken                  | custom                                                                                       |
| self_check_answers           | typed: false, from_official_starter: true, conventions: true, docs_current: true, can_judge_agent: false |
| team_size                   | solo                                                                                         |
| deployment_target           | railway                                                                                      |
| ci_provider                 | github-actions                                                                               |
| ci_default_flow             | auto-deploy-on-merge                                                                         |
| has_auth                    | true                                                                                         |
| has_payments                | false                                                                                        |
| has_realtime                | false                                                                                        |
| has_ai                      | false                                                                                        |
| has_background_jobs         | false                                                                                        |

Notes:
- **`quality_override: true`** — the user proceeded past the typed agent-friendly gate during stack selection (Django is duck-typed at runtime). The hand-off's planned compensation — type hints at boundaries + Pydantic for request validation + mypy in CI — is **not** applied by bootstrapper in v1; it surfaces here for the future M1L4 skill to act on.
- **`bootstrapper_confidence: verified`** — no heads-up; the scaffold path was battle-tested end-to-end.

## Next steps

Next: a future skill will set up agent context (CLAUDE.md, AGENTS.md). For now, your project is scaffolded and verified — happy hacking.

Useful manual steps in the meantime:
- `git init` (if you have not already) to start your own repo history. — Note: this cwd already contains a `.git/` (the repo pre-existed); the scaffold added untracked `manage.py` and `stock_guard/` and modified `pyproject.toml` + `uv.lock` via `uv add django`. Stage those as your first Django commit.
- Review any `.scaffold` siblings the conflict policy created and decide which version of each file to keep. — None created this run (no file-name overlaps under native-cwd).
- Address audit findings per your project's risk tolerance — the full breakdown is in this log. — Audit was clean (0 findings across all tiers).
- Project-specific: consider adding `psycopg` (for PostgreSQL on Railway) and `gunicorn` to `dependencies` before deploy; Django's default `sqlite3` is fine for local dev but Railway Postgres needs a driver. `uv add psycopg[binary] gunicorn` is the uv-idiomatic equivalent.
