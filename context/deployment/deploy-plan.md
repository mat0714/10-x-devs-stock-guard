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

1. **"Use Railway's Config-as-Code"** — Config-as-Code (`railway.json`/`railway.toml`) is **deprecated with a hard 2026-12-01 cutoff, and new services CANNOT opt into it at all.** A fresh Railway service created today has no CaC path. The replacement (Infrastructure as Code, `.railway/railway.ts`) is GA but requires a Node SDK (`npm install railway`) — toolchain contamination for a deliberately-Python repo; the Python variant (`.railway/railway.py`) is beta. **This plan uses dashboard service settings + the committed `Dockerfile` instead** (see D13; `infrastructure.md` Getting Started step 4 patched 2026-10-08).
2. **Railpack's default Django start command** (verified from railpack.com/languages/python) is `python manage.py migrate && gunicorn {appName}:application` — with **no `--bind` flag**. Gunicorn defaults to `127.0.0.1:8000`, which Railway's router cannot reach. Compare Railpack's Flask default (`gunicorn --bind 0.0.0.0:${PORT:-8000} main:app`), which binds correctly. **Any Django deploy on Railway must bind `0.0.0.0:$PORT` explicitly** — the infra doc's literal startCommand omits it and would produce a deploy that "runs" but 502s. (This plan ultimately built via Dockerfile rather than Railpack, but the explicit bind applies equally — see D9 and finding #2: the bind AND the domain `targetPort` must both match Railway's injected `PORT=8080`.)

## Decisions (locked during planning)

| # | Decision | Choice |
|---|---|---|
| D1 | Deploy scope | Productionize scaffold + deploy foundation (no feature code) |
| D2 | Deploy trigger | Railway native GitHub auto-deploy on `main` push; GitHub Actions = pre-merge gate only (no `RAILWAY_TOKEN` in CI) |
| D3 | Settings split | Single `settings.py`, env-driven (no settings package, no `--settings` flag) |
| D4 | Static files | WhiteNoise + `CompressedManifestStaticFilesStorage`, served by gunicorn |
| D5 | Postgres driver | `psycopg[binary]` (v3). **Rationale (corrected):** Railpack auto-provides `libpq-dev`+`libpq5`, so libpq is NOT the reason; `[binary]` bundles the precompiled C extension, avoiding any compiler-toolchain dependency during build. Bare `psycopg` would also work (libpq is present) but couples the build to the toolchain. |
| D6 | Python pin | `.python-version` = `3.12` is the **active** pin (consumed by the Dockerfile via `uv sync`, which resolves 3.12; also honored by local `uv`). The `RAILPACK_PYTHON_VERSION=3.12` var was **deleted 2026-10-08** — inert under Dockerfile-as-builder (D7). If Railpack is ever restored (delete the Dockerfile), re-add this var. |
| D7 | Builder | **RESOLVED 2026-10-08: the `Dockerfile` IS the builder — retracted as a "dormant fallback."** Original intent was Railpack-primary with a dormant Dockerfile hedge; live deploys falsified it (finding #1, Phase 2–4 log): Railway auto-detects and prefers a committed Dockerfile regardless of the service `builder=RAILPACK` setting, so every deployment reports `builder: DOCKERFILE`. Decision: **accept the Dockerfile as the canonical, version-controlled build path** (it works, and unlike Railpack it can't silently regress on a builder update). The committed `Dockerfile` is therefore load-bearing, not a hedge. The Railpack-specific vars (`RAILPACK_*`) are inert and have been **deleted** from the Railway service (2026-10-08). To ever switch to Railpack, delete `Dockerfile` from the repo — cannot have both. |
| D8 | CI gate content | `uv sync --frozen --no-dev` + `manage.py check` + `makemigrations --check --dry-run` + **`collectstatic --noinput`** + **`check --deploy`** (all on SQLite — no Postgres service container). The last two close the CI/prod parity gap for static-config and deploy-checklist failures that would otherwise pass CI green and ship to prod on the first `main` merge. Postgres-specific migration/SSL surface is intentionally NOT covered in CI — the scaffold has only Django built-in migrations (identical on SQLite/Postgres); revisit when feature migrations land. No ruff/mypy/tests yet (no feature code). |
| D8a | Dev-dep group convention | Add an empty `[dependency-groups] dev = []` to `pyproject.toml` now. Future test/lint/type deps (pytest, mypy, ruff) go in `dev`, NEVER in `dependencies`. Makes the `--no-dev` flag (CI + Railpack build) meaningful from day-1 and prevents the latent trap of shipping test tooling into the prod runtime image. |
| D9 | Migrate pattern | `preDeployCommand` (Railway field, takes a **list**) runs `migrate --noinput`; the container start is governed by the Dockerfile `CMD`. **RESOLVED 2026-10-08 (see finding #2):** the Railway `startCommand` override was **cleared** (empty) so the Dockerfile `CMD` governs; the `CMD` is shell-form `uv run gunicorn --bind 0.0.0.0:${PORT:-8000} stock_guard.wsgi:application`. The `--bind 0.0.0.0:${PORT:-8000}` is load-bearing **and** Railway injects `PORT=8080`, so the service domain `targetPort` must be `8080` to match — the explicit bind alone is NOT sufficient (the Router defaulted to `8000` and 502'd the healthcheck). `collectstatic` runs as a Dockerfile build step, not in the start command. |
| D10 | `ALLOWED_HOSTS` | Env var comma-list (`ALLOWED_HOSTS=stock-guard-*.up.railway.app`); dev default `[]` |
| D11 | Backups | Deferred — ship `sslmode=require` only; nightly `pg_dump`→external bucket is a follow-up milestone (DB empty after scaffold deploy) |
| D12 | Agent ops/MCP | CLI-only now; Railway MCP wiring deferred (no recurring query pattern yet to justify MCP schema cost) |
| D13 | Railway config source | **Dashboard service settings + committed `Dockerfile`** (no `railway.json`/`railway.toml`/`.railway/*`). CaC is unavailable to new services. IaC (`.railway/railway.ts`) would contaminate the Python repo with Node; the Python variant is beta — not adopted. Note: because the Dockerfile (D7) is the real build path, the *build* is version-controlled; only the *deploy settings* (`preDeployCommand`, `healthcheckPath`, domain `targetPort`) live in the dashboard — drift risk is narrower than originally stated. Exact values recorded in Phase 2.5. |
| D14 | Healthcheck | Add a `/health/` view (200, no DB/auth) to `urls.py`; point Railway `healthcheckPath` at `/health/`. Catches the "up-but-unreachable" bind-bug failure mode and drives deploy-success / auto-restart. |
| D15 | DB connection robustness | `dj_database_url.config(conn_max_age=600, conn_health_checks=True, ssl_require=True)`. `conn_health_checks=True` is the current dj-database-url README recommendation whenever `conn_max_age` is non-zero; mitigates Railway's "DB service restart briefly drops connections" unknown-unknown. |
| D16 | WSGI app resolution | ~~Set `RAILPACK_DJANGO_APP_NAME=stock_guard.wsgi` as a Railway var.~~ **RETRACTED 2026-10-08:** inert once D7 resolved to Dockerfile-as-builder (the var only affects Railpack). Deleted from the Railway service; the Dockerfile `CMD` names `stock_guard.wsgi:application` explicitly. |

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

Pin `3.12` so local `uv sync` resolves 3.12 (uv honors this file). The Dockerfile's `uv sync` consumes this file, so it is the active Python pin (the Railpack `RAILPACK_PYTHON_VERSION` var was dropped — D6/D7).

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

**1.5 `Dockerfile` — canonical build path (new file)**

> **As-executed note (2026-10-08):** originally written as a "dormant fallback" with Railpack primary; finding #1 showed Railway always prefers a committed Dockerfile, so this file IS the builder (D7 resolved). Kept small: `python:3.12-slim` base, uv copied from `ghcr.io/astral-sh/uv`, `uv sync --frozen --no-dev`, `DJANGO_SETTINGS_MODULE`, `collectstatic --noinput` as a build step, shell-form `CMD uv run gunicorn --bind 0.0.0.0:${PORT:-8000} stock_guard.wsgi:application`. No multi-stage complexity.

**1.6 `.github/workflows/ci.yml` — pre-merge gate (new file)**

Trigger: `pull_request` to `main` (and optionally `push` to `main` for a non-deploying sanity check — Railway-native handles the actual deploy).

Steps:
1. `actions/checkout@v4`
2. `actions/setup-python@v5` with `python-version: "3.12"`
3. Install `uv` (official `astral-sh/setup-uv@v5` action).
4. `uv sync --frozen --no-dev`
5. `uv run python manage.py check` (Django system checks — catches config/static/middleware errors)
6. `uv run python manage.py makemigrations --check --dry-run` (fails if model migration drift exists — guards against a merge shipping unmigrated schema)
7. `uv run python manage.py collectstatic --noinput` (D8 parity — catches `CompressedManifestStaticFilesStorage` misconfig pre-merge; the Dockerfile build runs the same command)
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
DJANGO_SETTINGS_MODULE=stock_guard.settings
ALLOWED_HOSTS=<your-app>.up.railway.app,healthcheck.railway.app,<service>.railway.internal
```
`DEBUG` is intentionally **not set** (defaults to `False`).

> **Corrected 2026-10-08:** `RAILPACK_PYTHON_VERSION` / `RAILPACK_DJANGO_APP_NAME` are NOT set — the Dockerfile is the builder (D7), so they are inert. Python version comes from `.python-version` via the Dockerfile. `ALLOWED_HOSTS` must include `healthcheck.railway.app` and the private domain or Railway's internal healthcheck probe gets a 400 (finding #3, Phase 2–4 log).

**2.4 Set Railway variables (secrets — human generates/pastes, not the agent)**
```bash
uv run python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
railway variables set SECRET_KEY=<pasted-generated-value>
```

**2.5 Configure service settings via dashboard (D13 — NOT a committed config file)**

Set these in the service's Settings → Deploy panel (these are the audit-trail values; record them here since they're not version-controlled). **Values below are the as-deployed reality (2026-10-08), corrected from the original plan:**
- `builder` = **DOCKERFILE** (Railway auto-detects the committed `Dockerfile` and prefers it over the `RAILPACK` service setting — D7 resolved; see finding #1)
- `preDeployCommand` = `["uv run python manage.py migrate --noinput"]` (this field takes a **list** per Railway docs)
- `startCommand` = **empty** — cleared so the Dockerfile `CMD` governs. The `CMD` is shell-form `uv run gunicorn --bind 0.0.0.0:${PORT:-8000} stock_guard.wsgi:application`.
- `healthcheckPath` = `/health/` (D14)
- `healthcheckTimeout` = 100 (seconds)
- domain `targetPort` = **8080** (must match Railway's injected `PORT=8080`; the Router default `8000` 502'd the healthcheck — finding #2)

> **PB (D7):** the Dockerfile is the real build path — it runs `uv sync --frozen --no-dev` and `collectstatic` at build time. `collectstatic` therefore does NOT run in the start command. To switch to Railpack, delete `Dockerfile` from the repo.

### Phase 3 — Connect Railway's GitHub auto-deploy

- In the Railway dashboard: connect the GitHub repo to the Railway service, branch = `main`. Every push to `main` triggers a deploy automatically. This **is** the `auto-deploy-on-merge` contract from `tech-stack.md` — no `RAILWAY_TOKEN` in GitHub Actions.

**2.6 First deploy**
```bash
railway up                       # blocks until complete
railway logs --tail              # stream build + runtime logs
```

### Phase 4 — Verification (definition of done)

- [ ] `railway up` completes (Dockerfile builds `uv sync --frozen --no-dev` green; logs show Python 3.12 resolved, not 3.13).
- [ ] `preDeployCommand` migrate hook shows Django migration output in logs (applies `auth`/`admin`/`contenttypes`/`sessions` built-in tables to Postgres).
- [ ] `collectstatic --noinput` completes with no errors in the **build** log (it is a Dockerfile build step, not a start-command step).
- [ ] **Reachability (the bind/port regression test):** `curl -i https://<your-app>.up.railway.app/health/` returns `200 ok`. If this 502s/timeout while logs show gunicorn running, check BOTH the `--bind 0.0.0.0:$PORT` AND the domain `targetPort` (= 8080) — the healthcheck should have caught this first (finding #2).
- [ ] Railway service shows "healthy" (healthcheck passing on `/health/`).
- [ ] `/admin/` loads **with CSS** (visually confirm a styled login form — confirms WhiteNoise static serving, not just a 200 with broken assets).
- [ ] `manage.py check --deploy` surfaces no critical warnings (one-off `railway ssh` + `uv run python manage.py check --deploy`; `SECRET_KEY` notices clean since env-injected).
- [ ] Confirm `DEBUG=False` in prod: request a non-existent URL → production 404 template, not the yellow debug page.
- [ ] Postgres TLS: Django connects without error (`ssl_require=True` enforces; a TLS failure shows in logs at first request).
- [ ] **Builder check (D7 resolved):** service Settings shows `builder = DOCKERFILE` and the committed `Dockerfile` is the active build path — this is now the *expected* state, not a failure. The `RAILPACK_*` vars are absent.

---

## Execution log — Phase 1 completed (2026-10-07)

Branch renamed `master` → `main` (and remote default updated) to match D2/Phase 3 and the CI trigger. Phase 1 landed as commit `Productionize scaffold for Railway deploy (Phase 1)`; CI run `success` (14s).

**Two deviations from the written Phase 1, both required to keep the gate green:**

1. **`pyproject.toml` dependency versions pinned with floors** (`gunicorn>=23.0.0`, `dj-database-url>=3.0.0`, `whitenoise>=6.8.0`, `psycopg[binary]>=3.2.0`). Resolved to gunicorn 26.2.0, dj-database-url 3.1.2, whitenoise 6.12.0, psycopg 3.3.6 in `uv.lock` — the plan's "gunicorn 26.x is compatible with Python 3.12" note held.
2. **`check --deploy` hard-fails on `mail.E001`.** Django 6.1 promotes "console email backend in the default MAILERS entry" from a warning to an **ERROR**, so the plan's "leave console for now / tolerate env-gated warnings" (1.3, CI step 8) would have failed the gate. Resolution: `settings.py` now selects an **SMTP backend when `EMAIL_HOST` is set**, else console. CI step 8 runs with production-shaped env (`DEBUG=0`, dummy `SECRET_KEY`/`ALLOWED_HOSTS`/`DATABASE_URL`, `EMAIL_HOST`) so the deploy checklist reflects production; only `security.W004` (HSTS) and `security.W008` (SSL redirect) remain — warnings, exit 0, both already in the plan's deferred hardening list.

Local verification (Phase 1.7) all green: `check` clean, `makemigrations --check` clean, `collectstatic` 130 files OK, `check --deploy` exit 0 under prod-shaped env, `/health/` → 200 `ok`, `/admin/` → 302.

**Railway CLI** installed to `~/.local/npm-global/bin` (version 5.63.4) because the system npm prefix is root-owned.

---

## Execution log — Phase 2–4 completed (2026-10-07)

Live URL: **https://stock-guard-production.up.railway.app** — `/health/` → 200, `/admin/` → 302, `/static/admin/css/base.css` → 200 `text/css`, `/nonexistent` → production 404 (DEBUG off). Service status `SUCCESS`.

Railway artifacts: project `stock-guard` (`36f63c7f-…`), environment `production` (`c778649a-…`), app service `stock-guard` (`55c4eb5b-…`, GitHub-sourced from `mat0714/10-x-devs-stock-guard`@`main`), Postgres service (`81b3efa8-…`, image `ghcr.io/railwayapp-templates/postgres-ssl:18`, region `iad`).

### Material findings — the plan's assumptions were wrong in three places

> **Close-out (2026-10-08): all three findings resolved.** #1: accepted the Dockerfile as the canonical build path; `RAILPACK_PYTHON_VERSION` + `RAILPACK_DJANGO_APP_NAME` deleted from the Railway service. #2: domain `targetPort=8080` set (deployed). #3: `ALLOWED_HOSTS` includes `healthcheck.railway.app` + private domain (deployed). D7/D9/D13/D16 updated above; Phase 2.3/2.5/4 corrected to the as-deployed values.

1. **D7 is falsified: Railpack is NOT the active builder.** Every deployment (GitHub and local) reports `builder: DOCKERFILE` — Railway auto-detects and prefers the committed `Dockerfile` regardless of the service `builder: RAILPACK` setting. The "dormant fallback" premise does not hold: the Dockerfile **is** the builder. Consequence: the plan's Railpack-specific `RAILPACK_*` vars are inert, and the `startCommand` override should be treated as Dockerfile-CMD-equivalent. **Resolution (2026-10-08):** accepted the Dockerfile as the real, version-controlled build path; deleted the `RAILPACK_*` vars. To ever use Railpack, delete `Dockerfile` — cannot have both.

2. **`startCommand` with `${PORT:-8000}` bound the wrong port.** Railway injects `PORT=8080`, so gunicorn listened on `0.0.0.0:8080`, but the service's Router target port defaulted to `8000` → healthcheck "service unavailable" → deploy FAILED (4 consecutive attempts). Resolved by setting the service domain `targetPort = 8080` to match `$PORT`. This was not in the plan; the plan assumed `--bind 0.0.0.0:${PORT:-8000}` was sufficient.

3. **`ALLOWED_HOSTS` blocked the healthcheck.** Railway's internal healthcheck probes with a Host header not in the plan's allowlist (`stock-guard-production.up.railway.app` pattern). With `DEBUG=False`, Django returns **400 Bad Request** to the probe → healthcheck fails. Resolved by adding `healthcheck.railway.app` and the private domain: final value `ALLOWED_HOSTS=stock-guard-production.up.railway.app,healthcheck.railway.app,stock-guard.railway.internal`.

### Phase 3 blocker (RESOLVED 2026-10-07): Railway GitHub App not authorised

Initial `deploymentTriggerCreate` for `mat0714/10-x-devs-stock-guard` returned **"Cannot create deployment trigger … because no one in the project has access to it"** — the Railway GitHub App was not installed/authorised for the repo, so no auto-deploy trigger existed and pushes to `main` did NOT deploy.

**Resolved:** the repo owner authorised the Railway GitHub App. `deploymentTriggerCreate` then succeeded (trigger `d64a28ae-…`, provider `github`, repo `mat0714/10-x-devs-stock-guard`, branch `main`). **Verified end-to-end:** an empty commit (`6311782`) pushed to `main` auto-triggered deployment `f0961361` from that commit, which reached `SUCCESS`; `/health/` → 200. **D2's "Railway native GitHub auto-deploy on `main`" contract is now in effect** — pushes to `main` deploy without `railway up`.

### Deviations applied during Phase 2–4

- Cleared the `startCommand` override (set to `""`) so the Dockerfile `CMD` governs; the CMD was corrected to shell-form `gunicorn --bind 0.0.0.0:${PORT:-8000}` so `$PORT` expands.
- Set service domain `targetPort = 8080` (Railway's injected `PORT`) — required for Router/healthcheck reachability.
- Added `healthcheck.railway.app` + private domain to `ALLOWED_HOSTS`.
- `SECRET_KEY` generated and set via `--stdin` (value never printed/logged).
- `DATABASE_URL` set as a reference variable `${{Postgres.DATABASE_URL}}` on the app service.
- Registered an SSH key with Railway; **in-container `check --deploy` (Phase 4 item) NOT run** — `railway ssh` needs interactive host-key confirmation (askpass unavailable in this environment). Covered by the local prod-shaped `check --deploy` (exit 0).

### Phase 4 verification results

| Check | Result |
|---|---|
| `railway up` completes | ✅ SUCCESS (`0366c589`, and the `railway up` that first passed) |
| `preDeployCommand` migrate hook | ✅ logs show "Apply all migrations: admin, auth, contenttypes, sessions" |
| `collectstatic` in build log | ✅ "130 static files copied / 0 unmodified" |
| Reachability `/health/` → 200 ok | ✅ |
| Service shows "healthy" | ✅ status SUCCESS |
| `/admin/` loads with CSS | ✅ 302 → login, `base.css` served 200 `text/css` |
| `check --deploy` in prod | ⚠️ not run in-container (SSH gate); local prod-shaped run exit 0 |
| `DEBUG=False` in prod | ✅ clean 404, no debug page |
| Postgres TLS (`ssl_require=True`) | ✅ migrate ran against Postgres with no TLS error |
| Builder check (D7) | ✅ RESOLVED 2026-10-08 — builder is `DOCKERFILE`; accepted as canonical build path, `RAILPACK_*` vars deleted (finding #1 accepted, not a defect) |

**Phase 3 outcome:** ✅ auto-deploy trigger created and verified — push to `main` → deployment `f0961361` → SUCCESS.

---

## Execution log — Close-out of open findings (2026-10-08)

Resolved the one failed Phase 4 verification and the infra-doc staleness item, so the foundation contracts match the running system.

- **D7 builder contradiction — resolved by accepting the Dockerfile.** Took the plan's "accept the Dockerfile as the real build path" branch (not "delete Dockerfile to force Railpack"): the Dockerfile is version-controlled and immune to builder-version drift, and it already deploys green. Actions:
  - Deleted the two inert Railpack vars from the Railway `stock-guard` service: `RAILPACK_PYTHON_VERSION`, `RAILPACK_DJANGO_APP_NAME` (`railway variable delete …`, both exit 0; re-verified absent). These only affect Railpack, which is not the builder.
  - Rewrote D6, D7, D9, D13, D16; corrected Phase 2.3, 2.5, 4; updated the Dockerfile header comment ("Canonical build path", not "dormant fallback"); flipped the Phase 4 builder row ❌ → ✅.
- **Infra-doc staleness — patched in place** (`context/foundation/infrastructure.md`): Getting Started steps 1 and 4 (drop Config-as-Code + `RAILPACK_PYTHON_VERSION`, document the Dockerfile path + `targetPort`), the Recommendation paragraph, the Railpack risk-register row, and the Operational Story approval/rollback lines.
- **`deploy-plan.md` remains the audit trail**; no Railway service behavior changed except removing dead vars (next deploy rebuilds identically via the Dockerfile).

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
- **Infra-doc patch**: ✅ DONE 2026-10-08 — `context/foundation/infrastructure.md` Getting Started (Config-as-Code startup, Railpack startCommand, RAILPACK_PYTHON_VERSION), Operational Story, and Risk Register patched in place to reflect the Dockerfile build path + dashboard settings + the `targetPort` requirement. Git history preserves the original research.

## Reference paths

- Plan inputs: `context/foundation/infrastructure.md`, `context/foundation/tech-stack.md`, `context/foundation/prd.md`
- Verified external docs (2026-10-05): railpack.com/languages/python (Python version order, Django start command, `RAILPACK_DJANGO_APP_NAME`, libpq auto-install); docs.railway.com/config-as-code (deprecation + 2026-12-01 cutoff); docs.railway.com/infrastructure-as-code (IaC GA/beta status); docs.railway.com/config-as-code/reference (`preDeployCommand` list type, `healthcheckPath`); github.com/jazzband/dj-database-url (`conn_health_checks`/`ssl_require` signature); docs.djangoproject.com/en/6.1/howto/deployment/wsgi/gunicorn (gunicorn canonical invocation).
- Plan artifact (this file): `.kilo/plans/1791220970401-railway-deploy-foundation.md` — **copy to `context/deployment/deploy-plan.md`** (canonical 10x-cli path) when executing.
- Next consumer: milestone-planning skills treat `context/deployment/deploy-plan.md` as ground truth for "what's already deployed and which secrets are already wired."
