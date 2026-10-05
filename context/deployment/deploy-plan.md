# Deploy Plan — Stock Guard → Railway (MVP foundation)

> Inputs: `context/foundation/infrastructure.md` (Railway recommended), `context/foundation/tech-stack.md` (Django 6.1 / Python 3.12 / uv / Postgres), `context/foundation/prd.md`.
> Scope: **productionize the bare scaffold and prove the deploy pipeline end-to-end.** No feature views shipped here — feature work deploys continuously on top once the pipeline is proven.
> Artifact role: audit trail for "what was supposed to happen" when the live run goes sideways. Consumed downstream by milestone-planning skills.

## Current repo state (verified 2026-10-05)

- `pyproject.toml`: deps = `django>=6.1.1` only. **Missing** production deps (gunicorn, dj-database-url, whitenoise, psycopg).
- `stock_guard/settings.py`: raw startproject — hardcoded insecure `SECRET_KEY`, `DEBUG = True`, `ALLOWED_HOSTS = []`, SQLite `DATABASES`, no `STATIC_ROOT`, no env-driven config, `MAILERS = console.EmailBackend`.
- `stock_guard/urls.py`: only `admin/`. No feature apps, no login view, no root `/` view. `wsgi.py`/`asgi.py` default to `stock_guard.settings`.
- No `Dockerfile`, `Procfile`, `railway.json`, `.python-version`, `requirements.txt`, `.github/workflows/`, or migrations beyond Django's built-in app tables.
- `uv.lock` exists and is consistent with `pyproject.toml`.

## Infra-doc staleness findings (corrections carried into this plan)

The infra doc was researched 2026-09-25; two of its literal instructions are now stale against current Railway docs (verified 2026-10-05). This plan corrects both rather than propagating them:

1. **"Use Railway's Config-as-Code"** — Config-as-Code (`railway.json`/`railway.toml`) is **deprecated with a hard 2026-12-01 cutoff, and new services CANNOT opt into it at all.** A fresh Railway service created today has no CaC path. The replacement (Infrastructure as Code, `.railway/railway.ts`) is GA but requires a Node SDK (`npm install railway`) — toolchain contamination for a deliberately-Python repo; the Python variant (`.railway/railway.py`) is beta. **This plan uses dashboard service settings instead** (see D13). Record this in `context/foundation/lessons.md` if the cohort wants the infra doc patched.
2. **Railpack's default Django start command** (verified from railpack.com/languages/python) is `python manage.py migrate && gunicorn {appName}:application` — with **no `--bind` flag**. Gunicorn defaults to `127.0.0.1:8000`, which Railway's router cannot reach. Compare Railpack's Flask default (`gunicorn --bind 0.0.0.0:${PORT:-8000} main:app`), which binds correctly. **Any Django deploy on Railway must override `startCommand` with an explicit bind** — the infra doc's literal startCommand omits it and would produce a deploy that "runs" but 502s.

## Decisions (locked during planning)

| # | Decision | Choice |
|---|---|---|
| D1 | Deploy scope | Productionize scaffold + deploy foundation (no feature code) |
| D2 | Deploy trigger | Railway native GitHub auto-deploy on `main` push; GitHub Actions = pre-merge gate only (no `RAILWAY_TOKEN` in CI) |
| D3 | Settings split | Single `settings.py`, env-driven (no settings package, no `--settings` flag) |
| D4 | Static files | WhiteNoise + `CompressedManifestStaticFilesStorage`, served by gunicorn |
| D5 | Postgres driver | `psycopg[binary]` (v3). **Rationale (corrected):** Railpack auto-provides `libpq-dev`+`libpq5`, so libpq is NOT the reason; `[binary]` bundles the precompiled C extension, avoiding any compiler-toolchain dependency during build. Bare `psycopg` would also work (libpq is present) but couples the build to the toolchain. |
| D6 | Python pin | `.python-version` = `3.12` locally + Railway var `RAILPACK_PYTHON_VERSION=3.12`. **Note (corrected):** Railpack reads `.python-version` directly (per its version-resolution order), so the var is *redundant-but-explicit* hardening — kept because it survives if `.python-version` is ever removed, and documents builder intent. Not "belt-and-suspenders" against a gap. |
| D7 | Railpack hedge | Add minimal fallback `Dockerfile` (dormant; Railpack stays primary via `uv.lock` detection. Railway always builds with a Dockerfile if present — so this Dockerfile MUST be structured to *not* accidentally become the active builder; verify in service settings that builder = RAILPACK after first deploy.) |
| D8 | CI gate content | `uv sync --frozen --no-dev` + `manage.py check` + `makemigrations --check --dry-run` + **`collectstatic --noinput`** + **`check --deploy`** (all on SQLite — no Postgres service container). The last two close the CI/prod parity gap for static-config and deploy-checklist failures that would otherwise pass CI green and ship to prod on the first `main` merge. Postgres-specific migration/SSL surface is intentionally NOT covered in CI — the scaffold has only Django built-in migrations (identical on SQLite/Postgres); revisit when feature migrations land. No ruff/mypy/tests yet (no feature code). |
| D8a | Dev-dep group convention | Add an empty `[dependency-groups] dev = []` to `pyproject.toml` now. Future test/lint/type deps (pytest, mypy, ruff) go in `dev`, NEVER in `dependencies`. Makes the `--no-dev` flag (CI + Railpack build) meaningful from day-1 and prevents the latent trap of shipping test tooling into the prod runtime image. |
| D9 | Migrate pattern | `preDeployCommand` (Railway field, takes a **list**) runs `migrate --noinput`; `startCommand` runs `collectstatic --noinput && gunicorn --bind 0.0.0.0:${PORT:-8000} stock_guard.wsgi:application` only. **The `--bind` is load-bearing** — fixes the Railpack-default-omission bug. |
| D10 | `ALLOWED_HOSTS` | Env var comma-list (`ALLOWED_HOSTS=stock-guard-*.up.railway.app`); dev default `[]` |
| D11 | Backups | Deferred — ship `sslmode=require` only; nightly `pg_dump`→external bucket is a follow-up milestone (DB empty after scaffold deploy) |
| D12 | Agent ops/MCP | CLI-only now; Railway MCP wiring deferred (no recurring query pattern yet to justify MCP schema cost) |
| D13 | Railway config source | **Dashboard service settings** (no committed `railway.json`/`railway.toml`/`.railway/*`). CaC is unavailable to new services; IaC contaminates the Python repo with Node or bets on beta Python authoring. Tradeoff accepted: config is not version-controlled (drift risk) — mitigate by recording the exact settings in this plan as the audit trail. |
| D14 | Healthcheck | Add a `/health/` view (200, no DB/auth) to `urls.py`; point Railway `healthcheckPath` at `/health/`. Catches the "up-but-unreachable" bind-bug failure mode and drives deploy-success / auto-restart. |
| D15 | DB connection robustness | `dj_database_url.config(conn_max_age=600, conn_health_checks=True, ssl_require=True)`. `conn_health_checks=True` is the current dj-database-url README recommendation whenever `conn_max_age` is non-zero; mitigates Railway's "DB service restart briefly drops connections" unknown-unknown. |
| D16 | WSGI app resolution | Set `RAILPACK_DJANGO_APP_NAME=stock_guard.wsgi` as a Railway var. Removes reliance on Railpack scanning settings.py for `WSGI_APPLICATION` (scan works, but explicit is safer against a future settings refactor). |

## Boundary: what this plan does NOT do

- Does not build feature views, auth, watchlist, or `score_formation` — that's feature work landing on top of this verified pipeline.
- Does not add ruff/mypy config or tests — AGENTS.md says "wire that up before relying on a CI check," and there's no code to check yet; gate is narrow on purpose.
- Does not provision nightly backups / external bucket credentials — DB is empty post-deploy; deferred per D11.
- Does not configure Railway MCP server — deferred per D12.
- Does not adopt Railway IaC — deferred per D13 (toolchain contamination / beta).
- Does not handle multi-region HA, read replicas, or DR — explicitly out of scope (infra doc "Out of Scope").

## Known gaps deliberately left open

- **CI/Postgres parity:** CI runs on SQLite (D8). Postgres-specific migration/SSL behavior is not exercised pre-merge. Acceptable while the app has only Django built-in migrations (identical across SQLite/Postgres). **Trigger to revisit:** the first feature migration that uses Postgres-specific features (e.g., `JSONField` indexes, partial indexes, `sslmode`). At that point add a Postgres service container to the CI workflow.
- **Config drift (D13):** Railway service settings are not version-controlled. Mitigated by recording exact values in Phase 2.5 as the audit trail, but a manual dashboard edit can silently diverge from the plan. Reconsider Railway IaC adoption (see Open items) if drift incidents occur.

---

## Execution order

### Phase 0 — Human setup gates (manual, before any code/agent work)

These are panel/account actions the agent cannot perform. Do them first so the agent's CLI steps don't block.

- **G1.** Create a Railway account at railway.com (Hobby $5/mo + usage credit) if not present.
- **G2.** Create a GitHub repo (or confirm the existing one) and note its remote URL; Railway's GitHub integration will connect to it.
- **G3.** Have a payment method on file in Railway (Hobby requires it even with the credit).

### Phase 1 — Source code changes (agent-owned, reviewable as a PR)

> All edits land in one PR so the pre-merge gate exercises the productionized tree before Railway auto-deploys `main`.

**1.1 `pyproject.toml` — add production deps + dev group**

Add to `dependencies`:
- `gunicorn` (WSGI server; startproject ships none. Django 6.1 docs include a dedicated "How to use Django with Gunicorn" page; gunicorn 26.x is pure-Python and compatible with Python 3.12.)
- `dj-database-url` (parses `DATABASE_URL`; current v3.x supports `conn_max_age`/`conn_health_checks`/`ssl_require` kwargs.)
- `whitenoise` (static serving from the process; Ephemeral-FS-safe.)
- `psycopg[binary]` (Django 6 `django.db.backends.postgresql` requires psycopg v3; `[binary]` bundles the precompiled C extension — no compiler toolchain needed at build. Railpack provides `libpq-dev`/`libpq5` regardless.)

Add an empty dev-dependency group (D8a):
```toml
[dependency-groups]
dev = []
```
Document (in a code comment or the PR description) that future pytest/mypy/ruff go in `dev`, never `dependencies`.

Then run `uv lock` to regenerate `uv.lock` with the new deps pinned.

**1.2 `.python-version` — new file**

Pin `3.12` so local `uv sync` resolves 3.12 (uv honors this file). Documents local-dev intent. Railpack also reads this file (per D6 note), so `RAILPACK_PYTHON_VERSION` is redundant-but-explicit hardening on top.

**1.3 `stock_guard/settings.py` — env-driven productionization**

Keep the single-file structure. Apply these changes (exact semantics, not literal code — implementation agent writes idiomatic Django 6.1):

- `SECRET_KEY`: read from `os.environ["SECRET_KEY"]`. Dev fallback: if the env var is absent, use the existing dev-insecure key AND force `DEBUG = True`. Never hardcode the production value.
- `DEBUG`: read from `os.environ.get("DEBUG", "").lower() in ("1", "true", "yes")`. Default `False`. The dev-fast-path above only flips `DEBUG=True` when `SECRET_KEY` is the dev sentinel — so a prod deploy missing `SECRET_KEY` fails start loudly rather than running insecurely.
- `ALLOWED_HOSTS`: `os.environ.get("ALLOWED_HOSTS", "").split(",")` filtered to non-empty; dev default `[]` (Django allows localhost under `DEBUG=True`).
- `DATABASES`: if `DATABASE_URL` is set, `dj_database_url.config(conn_max_age=600, conn_health_checks=True, ssl_require=True)` (D15). Else keep SQLite as the dev default. Import `dj_database_url` at top of file.
- `STATIC_ROOT = BASE_DIR / "staticfiles"` (required for `collectstatic`).
- `STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"` (infra doc mandate; Ephemeral-FS-safe).
- Insert `"whitenoise.middleware.WhiteNoiseMiddleware"` into `MIDDLEWARE` **immediately after** `SecurityMiddleware` (WhiteNoise docs require this position).
- `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` and `CSRF_COOKIE_SECURE` / `SESSION_COOKIE_SECURE` set to `not DEBUG` (respect Railway's HTTPS termination). Standard Django deploy checklist.
- `EMAIL_BACKEND`: production should not use the console backend — but the PRD has no email requirement in MVP, so leave console for now and add a `# TODO: SMTP-backed backend when email lands` note. Do not block the deploy on this.

> AGENTS.md rule: "Settings commit a dev-only secret key … never change those for deployment without a secrets/env split." This change **adds** the env split; it does not remove the dev fallback. The committed insecure key remains the dev sentinel, never the production value.

**1.4 `stock_guard/urls.py` — add `/health/` view (D14)**

Add a minimal health endpoint. A function-based view returning `HttpResponse("ok")` (200, no DB query, no auth). Wire it at `path("health/", ...)`. Keep `admin/` as-is. This is the only non-config source change in Phase 1 — it exists solely so Railway's healthcheck has a real probe target.

**1.5 `Dockerfile` — minimal fallback (new file, dormant)**

Railpack stays the active builder ONLY if Railway's service `builder` setting = RAILPACK. **Critical:** Railway's docs say "Railway will always build with a Dockerfile if it finds one" — so after first deploy, verify in service settings that the builder is explicitly pinned to RAILPACK, not auto/Dockerfile. The Dockerfile exists as a recoverable fallback if Railpack regresses; toggle the service to use it only then. Keep it small: `python:3.12-slim` base, `pip install uv`, `uv sync --frozen --no-dev`, `DJANGO_SETTINGS_MODULE`, `collectstatic --noinput` as a build step, `CMD gunicorn --bind 0.0.0.0:${PORT:-8000} stock_guard.wsgi:application`. No multi-stage complexity.

**1.6 `.github/workflows/ci.yml` — pre-merge gate (new file)**

Trigger: `pull_request` to `main` (and optionally `push` to `main` for a non-deploying sanity check — Railway-native handles the actual deploy).

Steps:
1. `actions/checkout@v4`
2. `actions/setup-python@v5` with `python-version: "3.12"`
3. Install `uv` (official `astral-sh/setup-uv@v5` action).
4. `uv sync --frozen --no-dev`
5. `uv run python manage.py check` (Django system checks — catches config/static/middleware errors)
6. `uv run python manage.py makemigrations --check --dry-run` (fails if model migration drift exists — guards against a merge shipping unmigrated schema)
7. `uv run python manage.py collectstatic --noinput` (D8 parity — catches `CompressedManifestStaticFilesStorage` misconfig pre-merge; prod `startCommand` runs the same command)
8. `uv run python manage.py check --deploy` (D8 parity — surfaces deploy-checklist warnings: `DEBUG`, `SECRET_KEY`, `ALLOWED_HOSTS`, secure cookies. Tolerate warnings that are env-gated; FAIL on criticals. Note: `check --deploy` warns when `DEBUG=False` and `ALLOWED_HOSTS=[]` — in CI both are the dev defaults, so expect those specific warnings and don't fail the job on them; fail only on warnings that indicate a real misconfiguration the implementation agent should judge.)

No ruff/mypy/tests in this workflow — there's no feature code to lint/type/check yet. Add them when feature apps land (AGENTS.md says "wire that up before relying on a CI check"; the workflow file is structured so those jobs slot in later).

**Intentionally NOT in CI (recorded as a known parity gap):** a Postgres service container. The scaffold's only migrations are Django's built-ins (identical on SQLite/Postgres), so the Postgres-specific surface is near-zero today. Revisit — add a Postgres service container to CI — once feature migrations land and the Postgres/SQLite behavioral delta becomes a real risk.

**1.7 Verify locally before pushing the PR**

```bash
uv sync
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py collectstatic --noinput   # confirms STATIC_ROOT + whitenoise wiring (CI step 7)
uv run python manage.py check --deploy            # mirror CI step 8; expect env-gated warnings (DEBUG/ALLOWED_HOSTS) — judge criticals
uv run python manage.py runserver                  # admin + /health/ load on SQLite + dev key
curl -s http://127.0.0.1:8000/health/              # expect "ok"
```

Open the PR; confirm the GitHub Actions gate passes. Merge to `main` once green.

### Phase 2 — Railway project (CLI-driven, agent-owned after human gates)

**2.1 Install/link CLI**
```bash
npm i -g @railway/cli          # or: bash <(curl -fsSL cli.new)
railway login
railway link                    # connect this repo to a Railway project
```

**2.2 Provision Postgres**
```bash
railway add                     # choose PostgreSQL; Railway auto-provisions DATABASE_URL + PG* vars
```

**2.3 Set Railway variables (non-secret config) — via `railway variables set` or dashboard**
```
RAILPACK_PYTHON_VERSION=3.12
RAILPACK_DJANGO_APP_NAME=stock_guard.wsgi
DJANGO_SETTINGS_MODULE=stock_guard.settings
ALLOWED_HOSTS=<your-app>.up.railway.app   # the generated Railway domain; append a custom domain later
```
`DEBUG` is intentionally **not set** (defaults to `False`).

**2.4 Set Railway variables (secrets — human generates/pastes, not the agent)**
```bash
uv run python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
railway variables set SECRET_KEY=<pasted-generated-value>
```

**2.5 Configure service settings via dashboard (D13 — NOT a committed config file)**

Set these in the service's Settings → Deploy panel (these are the audit-trail values; record them here since they're not version-controlled):
- `builder` = **RAILPACK** (explicitly pin — Railway auto-builds with Dockerfile if present per D7 caveat)
- `preDeployCommand` = `["uv run python manage.py migrate --noinput"]` (note: this field takes a **list** per Railway docs)
- `startCommand` = `uv run python manage.py collectstatic --noinput && gunicorn --bind 0.0.0.0:${PORT:-8000} stock_guard.wsgi:application` (the `--bind` is load-bearing — see D9)
- `healthcheckPath` = `/health/` (D14)
- `healthcheckTimeout` = 100 (seconds; reasonable for a cold gunicorn start)

Railpack auto-detects `pyproject.toml` + `uv.lock` and runs `uv sync --frozen --no-dev` — the fallback Dockerfile stays dormant unless Railpack breaks.

### Phase 3 — Connect Railway's GitHub auto-deploy

- In the Railway dashboard: connect the GitHub repo to the Railway service, branch = `main`. Every push to `main` triggers a deploy automatically. This **is** the `auto-deploy-on-merge` contract from `tech-stack.md` — no `RAILWAY_TOKEN` in GitHub Actions.

**2.6 First deploy**
```bash
railway up                       # blocks until complete
railway logs --tail              # stream build + runtime logs
```

### Phase 4 — Verification (definition of done)

- [ ] `railway up` completes (Railpack builds `uv sync --frozen --no-dev` green; logs show Python 3.12 resolved, not 3.13).
- [ ] `preDeployCommand` migrate hook shows Django migration output in logs (applies `auth`/`admin`/`contenttypes`/`sessions` built-in tables to Postgres).
- [ ] `collectstatic --noinput` completes with no errors in the `startCommand` log.
- [ ] **Reachability (the bind-bug regression test):** `curl -i https://<your-app>.up.railway.app/health/` returns `200 ok`. If this 502s/timeout while logs show gunicorn running, the `--bind` is wrong — the healthcheck should have caught this first.
- [ ] Railway service shows "healthy" (healthcheck passing on `/health/`).
- [ ] `/admin/` loads **with CSS** (visually confirm a styled login form — confirms WhiteNoise static serving, not just a 200 with broken assets).
- [ ] `manage.py check --deploy` surfaces no critical warnings (one-off `railway ssh` + `uv run python manage.py check --deploy`; `SECRET_KEY` notices clean since env-injected).
- [ ] Confirm `DEBUG=False` in prod: request a non-existent URL → production 404 template, not the yellow debug page.
- [ ] Postgres TLS: Django connects without error (`ssl_require=True` enforces; a TLS failure shows in logs at first request).
- [ ] **Builder pin check (D7 caveat):** service Settings shows `builder = RAILPACK`, not auto/Dockerfile — confirms the fallback Dockerfile isn't accidentally the active builder.

---

## Human-only runbook (advisory — DO NOT be automated)

These remain human panel actions per the infra doc's approval boundary. The agent should surface them as runbook steps, never execute them.

- **Rollback**: dashboard only — Service → Deployments → ⋮ → Rollback. No CLI verb. Fallback the agent CAN use: `railway up` re-deploying the last-known-good commit (keep a "last known good" commit/build tag noted). DB migrations do NOT roll back with the deploy — a forward-only migration applied by `preDeployCommand` must be manually reversed with a hand-written migration.
- **Rotate `SECRET_KEY` / DB password**: re-paste in Railway Variables, trigger a redeploy.
- **Delete the Postgres service or a project volume**: panel-only.
- **Change the billing plan / region**: panel-only (region is Pro-only).

## Open / deferred items (NOT in this plan, recorded for the next milestone)

- **ruff + mypy config + CI jobs**: AGENTS.md mandates mypy enforcement; add when there's feature code worth typing. Wire into the existing `.github/workflows/ci.yml` structure.
- **Tests**: AGENTS.md says write `TestCase` subclasses in each app's `tests.py`; add alongside feature apps.
- **Nightly `pg_dump` → external bucket (S3/R2) via Railway Cron Job**: infra Risk Register recommends this since Volume Backups are beta. Provision once the DB holds user data with value (post-feature-work).
- **Railway MCP server wiring** (`mcp.railway.com` / `railway mcp`): defer until a recurring class of live-state queries appears.
- **Railway IaC adoption** (`.railway/railway.ts` or `.railway/railway.py`): reconsider once (a) the config drift risk materializes, or (b) Python IaC authoring goes GA. Would replace the dashboard-settings approach in D13 with a version-controlled source of truth.
- **Email backend**: PRD has no email in MVP; console backend stays but is flagged `# TODO` in settings.
- **`SECURE_HSTS_*`, CSP, and the full `manage.py check --deploy` hardening list**: the basic checklist items above get the deploy out; the long-tail hardening lands with feature work.
- **Infra-doc patch**: `context/foundation/infrastructure.md` says "Use Railway's Config-as-Code" — now impossible for new services (2026-12-01 cutoff). Re-run `/10x-infra-research` or patch the doc's Operational Story + Getting Started sections to reflect dashboard-settings/IaC.

## Reference paths

- Plan inputs: `context/foundation/infrastructure.md`, `context/foundation/tech-stack.md`, `context/foundation/prd.md`
- Verified external docs (2026-10-05): railpack.com/languages/python (Python version order, Django start command, `RAILPACK_DJANGO_APP_NAME`, libpq auto-install); docs.railway.com/config-as-code (deprecation + 2026-12-01 cutoff); docs.railway.com/infrastructure-as-code (IaC GA/beta status); docs.railway.com/config-as-code/reference (`preDeployCommand` list type, `healthcheckPath`); github.com/jazzband/dj-database-url (`conn_health_checks`/`ssl_require` signature); docs.djangoproject.com/en/6.1/howto/deployment/wsgi/gunicorn (gunicorn canonical invocation).
- Plan artifact (this file): `.kilo/plans/1791220970401-railway-deploy-foundation.md` — **copy to `context/deployment/deploy-plan.md`** (canonical 10x-cli path) when executing.
- Next consumer: milestone-planning skills treat `context/deployment/deploy-plan.md` as ground truth for "what's already deployed and which secrets are already wired."
