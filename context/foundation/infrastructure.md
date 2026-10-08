---
project: Stock Guard
researched_at: 2026-09-25
recommended_platform: Railway
runner_up: Render
context_type: mvp
tech_stack:
  language: Python
  framework: Django 6.1
  runtime: Python 3.12
  package_manager: uv
  database: PostgreSQL
---

---

> **Post-deploy correction (2026-10-08).** The recommendation (Railway) held through a live deploy, but several *mechanics* in this doc were falsified during execution and are corrected inline below (marked **[corrected 2026-10-08]**). Summary: (1) **Config-as-Code is not used** — it is deprecated with a 2026-12-01 cutoff and unavailable to new services; config now lives in Railway dashboard service settings plus a committed `Dockerfile`. (2) **The Dockerfile, not Railpack, is the active builder** — Railway auto-prefers a committed Dockerfile; `RAILPACK_*` vars are inert and were removed. (3) **Railway injects `PORT=8080`**, so the service domain `targetPort` must be set to `8080` to match the gunicorn `--bind`; the default `8000` 502s the healthcheck. (4) `ALLOWED_HOSTS` must include `healthcheck.railway.app`. See `context/deployment/deploy-plan.md` for the full execution log.

## Recommendation

**Deploy Stock Guard on Railway.**

For a Django 6.1 / Python 3.12 / uv stack whose PRD mandates a responsive scan-on-login experience (NFR: full list with results within a few seconds), Railway's always-on containers eliminate cold starts that would threaten that responsiveness guarantee — the decisive factor against Vercel ($0 but 3–7s cold starts) and Render's free tier (~60s spin-up). **[corrected 2026-10-08]** Railpack was expected to auto-detect `uv.lock` and run `uv sync --frozen` without a custom Dockerfile; in practice a committed `Dockerfile` is required because Railway auto-prefers it over Railpack — the committed Dockerfile runs `uv sync --frozen --no-dev`, matching this stack's exact package surface. The interview answers drove the choice: no persistent connections required (opens railway to full-container options), cost-minimization preferred (Hobby $5/mo + usage credit is the lowest always-on floor among container PaaS), single region is fine (Railway's Hobby single-region constraint doesn't bite), external providers acceptable (though Railway Postgres co-location keeps ops single-vendor). The decision aligns with the `deployment_target: railway` hint recorded in `tech-stack.md` from stack selection, now validated against fresh 2025–2026 research rather than training-data familiarity.

## Platform Comparison

| Platform | CLI-first | Managed/Serverless | Agent-readable docs | Stable deploy API | MCP / Integration | Verdict |
|---|---|---|---|---|---|---|
| Railway | Partial | Pass | Pass | Pass | Pass | **Shortlisted (1st)** |
| Render | Partial | Pass | Pass | Pass | Pass | Shortlisted (2nd) |
| Vercel | Pass | Partial | Pass | Pass | Partial | Shortlisted (3rd) |
| Fly.io | Pass | Pass | Pass | Partial | Partial | Cost-blocked (~$44/mo) |
| Netlify | — | — | — | — | — | **DROPPED** — no Python runtime |
| Cloudflare | — | — | — | — | — | **DROPPED** — no long-lived Django process |

### Railway (Pass / Pass / Pass / Pass / Pass — rollback Partial pulls CLI-first to Partial)

`railway` CLI (GA, npm `@railway/cli` v5.62.1) covers `up`, `link`, `logs`, `ssh`, `connect`, `service redeploy`; the one Partial is **rollback, which is dashboard-only** (Service → Deployments → ⋮ → Rollback; no CLI verb). **[corrected 2026-10-08]** Railpack (GA) can build full containers from `pyproject.toml` + `uv.lock`, but Railway **prefers a committed `Dockerfile`** whenever one exists — so this project builds via its committed Dockerfile (`uv sync --frozen --no-dev`), not Railpack. Docs are markdown on GitHub (`railwayapp/docs`) plus `docs.railway.com/llms.txt` and `.md` URL variants. `railway up` deploys deterministically. **Railway MCP server is GA** at `mcp.railway.com` (CLI ≥5.44.0; remote OAuth or `railway mcp` local proxy). Reality-checked pricing: Hobby $5/mo incl. $5 usage credit → realistic always-on low-traffic Django + Postgres ~$10–20/mo out of pocket (RAM ~$10/GB-mo, CPU ~$20/vCPU-mo metered).

### Render (Partial / Pass / Pass / Pass / Pass)

Render now ships a **GA CLI** (`render deploys create --wait --confirm`, `render logs --tail`, `render ssh`, `render psql`); like Railway, **rollback is dashboard-only** ("Instant Rollbacks", Hobby keeps 5 builds) or re-deploy a prior commit/image — no dedicated CLI verb, so CLI-first is Partial. Native Python runtime is first-class and **auto-injects `uv` when `uv.lock` is present** (pin via `UV_VERSION`), which matches this stack's exact surface most precisely of all candidates. Docs published as markdown on GitHub (`render-oss/render-docs`, `render.com/docs/*.md`). Deploy hooks + REST API (`RENDER_API_KEY`). **Render MCP server GA** at `mcp.render.com/mcp` with official plugins for Claude Code, Cursor, Codex, plus GitHub-hosted skills (`render-oss/skills`). Reality-checked pricing: Free Web Service spins down after 15 min with **~60s cold starts** (breaks the PRD's responsive NFR) and **Free Postgres expires in 30 days** (data deleted). Realistic responsive floor = Starter $7 + Postgres $6 = **~$13/mo**. Higher than Railway's floor for the same responsiveness.

### Vercel (Pass / Partial / Pass / Pass / Partial)

`vercel` CLI is GA and full-featured: `vercel --prod`, `vercel rollback <id>` (Instant Rollback CLI public beta; Hobby limited to immediately-previous prod deploy), `vercel logs --follow`, `vercel mcp`. Vercel officially auto-detects Django (resolves `WSGI_APPLICATION`/`ASGI_APPLICATION`) and builds it into a single Vercel Function — **not a persistent gunicorn/uvicorn process**, which lands Managed/Serverless at Partial. Markdown docs via `.md` URL suffix + `vercel.com/llms.txt` + `llms-full.txt`. Deterministic deploys. **Vercel MCP public beta** (`https://mcp.vercel.com`, OAuth, read-only at launch). **Vercel Postgres is deprecated/sunset** (migrated to Neon); **Vercel KV deprecated** (→Upstash). Cost: Hobby free (1M invocations/mo, 4 Active CPU-hrs) — potentially $0 for 10k–100k requests, the cheapest floor, but documented cold starts of **3–7s on idle** for Django directly conflict with the PRD's "few seconds to full scanned list" NFR, and persistent DB connections are unreliable across invocations (external pooler effectively required).

### Fly.io (Pass / Pass / Pass / Partial / Partial) — Researched but cost-blocked

`flyctl` is full and agent-friendly (`fly deploy`, `fly scale`, `fly logs`, `fly secrets`, `fly ssh console`), but **rollback has no dedicated command** — `fly releases --image` then `fly deploy --image <tag>` (stable deploy API at Partial). Docs are markdown/MDX on GitHub (`superfly/docs`). Real long-lived VMs (full Django fidelity), but **no free tier** (removed 2024-10-07; bundled plans deprecated) — only an informal, unguaranteed `<$5` invoice waiver. Always-on shared-cpu-1x 256MB ≈ $1.94/mo, but `fly launch` defaults to a 1GB VM ≈ **$5.69/mo/machine**, plus managed Postgres Basic **$38/mo** → realistic always-on Django + Postgres ≈ **$44/mo**. For a cost-minimizing solo MVP (interview Q2), this is decisively too expensive. `fly mcp` family exists but every subcommand is tagged **experimental**. Not shortlisted.

### Netlify — DROPPED (hard-filter: runtime mismatch)

Netlify Functions support **only TypeScript, JavaScript, and Go** — there is no Python runtime. Django (WSGI/ASGI persistent process) cannot run. Sync functions cap at 60s (not configurable). Background Functions run up to 15 min (GA on credit-based plans, deploys ≥2025-03-20). Netlify Database (managed Postgres on Neon) went GA week of 2026-04-20; the prior beta Neon extension was deprecated for new DBs 2026-04-13. Official Netlify MCP Server is GA (since 2025-06-03). Despite strong agent-friendly doc/MCP story, the absence of a Python runtime is a hard blocker for this stack.

### Cloudflare — DROPPED (hard-filter: execution-model mismatch)

Cloudflare announced **Python Workers GA on 2026-09-21**, running Django via `workers.wsgi`/`workers.asgi` connectors under Pyodide (CPython→WASM) in a V8 isolate. But Workers are **request-scoped with ephemeral in-memory state** — there is no long-lived gunicorn/uvicorn process; the platform *is* the server. The cost-minimizing Free tier's **10ms CPU/invocation cap is too small for Django module load** (Paid required). Postgres via Hyperdrive-in-Python-Workers is **beta** (since 2026-09-16); the Django + Hyperdrive + psycopg stack is unproven. Concrete risk areas: `@transaction.atomic` disabled on D1/DO backends, Django Admin unverified on D1, psycopg2 C-extension fails (no Pyodide socket), global-scope DB clients an anti-pattern, ephemeral filesystem lost on isolate destroy. Doc/MCP story is first-class (`llms.txt`, `llms-full.txt`, per-product markdown; managed remote MCP servers). But forcing the standard Django execution model into request-scoped WASM isolates is not a fit for an MVP whose value depends on a responsive, session-backed, ORM-driven scan.

### Shortlisted Platforms

#### 1. Railway (Recommended)

Railway won on the combination the interview weighted: always-on containers (no cold starts — directly satisfies the PRD's responsive NFR), the lowest realistic always-on cost among container PaaS for this profile (~$10–20/mo vs Render ~$13/mo vs Fly.io ~$44/mo), and exact stack surface match — **[corrected 2026-10-08]** achieved via a committed `Dockerfile` that runs `uv sync --frozen --no-dev` (not Railpack, which Railway bypasses when a Dockerfile is present), so the project's pinned `uv` workflow deploys reproducibly. Markdown docs on GitHub + `llms.txt`, deterministic `railway up`, and a GA Railway MCP server give the agent a clean operational loop. Railway Postgres co-location keeps data-layer ops single-vendor even though the interview accepted external providers. The key selection driver over Vercel was cold-start elimination (Vercel's 3–7s Django idle cold starts threaten the "few seconds to scanned list" NFR); over Render it was the ~$3/mo lower responsive floor for the same always-on guarantee; over Fly.io it was the ~$30/mo cost differential for a cost-minimizing solo MVP.

#### 2. Render

Render scored a near-tie and is the runner-up. Its edge is the **most exact stack-surface match**: native Python runtime **auto-injects `uv` when `uv.lock` is present** (pin via `UV_VERSION`), confirming `python_version = 3.12.x` precisely. It also has arguably the strongest agent story — GA Render MCP at `mcp.render.com/mcp` with official plugins for Claude Code, Cursor, Codex, and a GitHub-hosted skills repo (`render-oss/skills`) bundling deploy/debug/docker/blueprint/migration skills. Render's gap vs Railway is cost: the free tier is broken for a responsive app (~60s cold start, free Postgres expires in 30 days), so the realistic floor is Starter $7 + Postgres $6 = **~$13/mo**, ~$3/mo above Railway's floor for the same responsiveness. Render is the swap-to candidate if Railway's unmanaged-DB or usage-billing surprises prove unacceptable during deploy.

#### 3. Vercel

Vercel is the cost-floor alternative and the genuine trade-off candidate. Hobby is free (1M invocations/mo, 4 Active CPU-hrs) — a Stock Guard at 10k–100k monthly requests could genuinely run at **$0 + Neon free Postgres**. Vercel officially auto-detects Django (resolves `WSGI_APPLICATION`), and `vercel` CLI + `vercel mcp` (public beta) give a clean agent loop. The dealbreaker for this PRD is **responsiveness**: Vercel runs Django as a single Vercel Function (not a persistent process), and documented cold starts of 3–7s on idle conflict with the "few seconds to full scanned list" NFR. Persistent DB connections are unreliable across invocations, requiring an external pooler (Neon pooler/PgBouncer). Vercel Postgres itself is deprecated (→Neon), so the data path already involves a second vendor. Vercel is the swap-to candidate if absolute cost floor matters more than the 3–7s cold-start hit.

## Anti-Bias Cross-Check: Railway

### Devil's Advocate — Weaknesses

1. **No CLI rollback verb** — the agent cannot revert a bad deploy from the terminal; rollback is dashboard-only (Service → Deployments → ⋮ → Rollback). The unattended ops loop breaks at the exact moment it's most needed (a broken production deploy), forcing a manual dashboard hand-off the agent cannot perform.
2. **Usage-based pricing surprise** — the "~$7–8/mo" figure assumes a tiny footprint, but Railway meters RAM (~$10/GB-mo) and CPU (~$20/vCPU-mo) with only a $5 monthly credit. An always-on Postgres plus a leaky or second process can quietly push the bill to $20–40/mo — the opposite of a cost-minimizing profile.
3. **Co-located Postgres is unmanaged** — self-signed TLS (renewal ~820 days via redeploy), Railway offers no official DB support, customized Postgres image (`ghcr.io/railwayapp-templates/postgres-ssl:18`). A solo after-hours dev inherits DBA duties Railway won't help with.
4. **Region selection is Pro-only** — on Hobby, the app is locked to a single account-wide preferred region; latency can't be fixed without a $20/mo Pro upgrade (interview Q4 said single region is fine, but this forecloses a cheap future fix).
5. **Volume Backups are beta** ("under development"): manual backups can't exceed 50% of volume size and restore only within the same project+environment — not a reliable sole DB restore path, and cross-region restore is currently impossible.

### Pre-Mortem — How This Could Fail

Six months in, Stock Guard on Railway is a quiet disaster. The "low-traffic solo" assumption held for three weeks, but once fellow investors (the PRD's confirmed multi-user persona) signed up, the always-on gunicorn plus co-located Postgres quietly breached the $5 Hobby credit: a steady $18–25/mo bill the cost-minimizing justification never budgeted. A botched late-night deploy shipped a migration that broke `score_formation`, and because Railway's rollback is dashboard-only, the solo dev — away from a laptop — couldn't revert; users hit 500s for an hour until they got home. Meanwhile, the self-signed Postgres TLS cert silently lapsed near its ~820-day window during a busy redeploy cycle, breaking pooled connections in ways the logs barely hinted at. The unmanaged Postgres received no automatic minor-version patching, leaving a stale build that one day refused a Django upgrade. None were "bugs" — they were the operational tax of an unmanaged DB, no CLI rollback, and usage-based pricing, exactly the failure modes the tech-stack hint never stress-tested.

### Unknown Unknowns

- The $5/mo Hobby "credit" is a **usage** credit against metered usage, not a fixed always-on allowance — an idle-but-running Django + Postgres burns CPU/RAM continuously and can exceed the credit even at zero app traffic, silently charging the card.
- **Volume Backups are beta** ("under development"): manual backups can't exceed 50% of volume size and restore only within the same project+environment — not a reliable sole DB restore path; cross-region restore is currently impossible.
- The container **filesystem is ephemeral** — anything written to disk is lost on every redeploy. No uploads in this PRD, but users (and `collectstatic` surprises) catch people who assume the container FS persists; media files would silently vanish.
- **Nixpacks → Railpack migration is in flight** (Nixpacks deprecated, maintenance mode; legacy `railway.json` until 2026-12-01); the build path may shift mid-MVP, and the Railpack resolver's locking semantics are still settling — a build that works today can break on a builder/builder-version update. **[corrected 2026-10-08]** This risk does not apply here: the project builds via a committed Dockerfile, so builder-side churn cannot change the build.
- The Postgres plugin runs **Railway's customized Postgres on a container**, not a dedicated managed cluster — no automatic minor-version upgrades, and a `railway down` of the DB service briefly drops all connections; you carry your own backup discipline. The self-signed cert's ~820-day renewal window is easy to miss until pooled connections start failing.

## Operational Story

How Railway actually operates day to day for Stock Guard. One concrete answer per line — not a category.

- **Preview deploys**: Railway deploys connected branches and supports **PR environments** (auto-provisioned preview environments per open PR, same service graph) so a PR gets its own isolated URL with its own Postgres instance by referencing the service. Preview environments are **available on Hobby** but a paid plan is recommended if many PRs run concurrently (each PR environment consumes usage). Fork-PR deploys are not gated (no Vercel-style "deploy preview protection"), so repository access controls are the boundary that governs who can trigger a preview. **[corrected 2026-10-08]** A preview of this service inherits the committed `Dockerfile`; note the service domain `targetPort` (see below) is a per-environment setting that must be re-checked for any new environment.
- **Secrets**: env vars and tokens live in the **Railway Variables** vault (per-service or shared), injected as environment variables at runtime; editable via `railway variables set` (CLI) or the dashboard. Anyone who is a member of the Railway project can read them. Rotation = set the new value in the vault and trigger a redeploy (`railway up` or service redeploy). There is no per-secret audit log on Hobby; Pro adds team controls.
- **Rollback**: from the dashboard, Service → Deployments → ⋮ → Rollback to any prior deployment (Railway retains deployment history by plan; Hobby keeps enough to revert recent deploys). Typical time-to-revert is seconds for the web service, but **DB migrations do NOT roll back automatically** — a forward-only migration that ran in the `startCommand` of the bad deploy must be manually reverted with a hand-written reverse migration. This is the single dashboard-only step in the loop and the one that breaks the unattended agent ops loop.
- **Approval**: an agent may perform `railway up` (deploy), `railway variables set` for non-secret config, `railway logs`, `railway ssh`, and `service redeploy` unattended. Actions reserved for a human: **rollback** (dashboard-only, no CLI verb), rotating the `SECRET_KEY` / primary DB password, deleting the Postgres service or a project volume, changing the billing plan, and any action that requires dashboard authorization (region changes are Pro-only and require the dashboard). **[corrected 2026-10-08]** Deploy mechanics that live in dashboard settings (not version-controlled): the service domain `targetPort` must be `8080` to match Railway's injected `PORT=8080` (`preDeployCommand` runs migrations; the container start is governed by the committed Dockerfile `CMD`; `healthcheckPath=/health/`).
- **Logs**: `railway logs` streams deploy logs; `railway logs --build|--http|--network|--dns` filter by stage and `-n N` limits lines. Runtime logs are streamed through the same `railway logs` command. The Railway MCP server (`mcp.railway.com`) exposes structured read-only tools (`list-services`, deploy status, feature-flags) the agent can call instead of parsing CLI output. Log retention on Hobby is **3 days**; Pro raises this.

## Risk Register

Every risk ties back to the cross-check lens that surfaced it, making the register auditable.

| Risk | Source | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| Bad deploy cannot be reverted by the agent (rollback is dashboard-only, no CLI verb) | Devil's advocate | M | H | Keep a "last known good" commit/build on hand so the agent can re-deploy the prior image via `railway up` as a CLI fallback; document the dashboard-rollback click sequence in `deploy-plan.md` as a human-only runbook step; treat destructive deploys (migrations) as human-approved. |
| Usage-based billing exceeds the $5 Hobby credit (always-on Django + Postgres burns CPU/RAM even at zero traffic) | Devil's advocate / Unknown unknowns | M | M | Pin service resource requests low (small web replica ~0.25 vCPU / 0.5 GB; Postgres ~0.25 vCPU / 0.5 GB); enable Railway's Serverless auto-stop ONLY if acceptable (breaks always-on — not for this PRD); monitor the Railway usage meter weekly; set a billing alert. Budget ~$15-20/mo not $7 to avoid surprise. |
| Co-located Postgres is unmanaged (no official support, self-signed TLS) | Devil's advocate | M | M | Use `sslmode=require` (not `verify-ca`) in `dj-database-url`-derived `DATABASE_URL`; set a calendar reminder for self-signed cert renewal (~820 days, via redeploy); schedule manual `pg_dump` backups to external storage (S3/R2) since Volume Backups are beta and restore-limited; document the restore runbook before going live. |
| A forward-only Django migration that broke in a bad deploy cannot be auto-rolled back, extending downtime | Pre-mortem | M | H | Write reversible/reviewed migrations only; for risky migrations, run `python manage.py migrate` in a preDeploy hook (not inline in `startCommand`) so a failed migration fails the deploy before it serves traffic; keep a reverse migration stub for any non-additive schema change. |
| Railpack resolver / uv handling drifts during MVP as Railway completes the Nixpacks → Railpack migration | Unknown unknowns | L | M | **[corrected 2026-10-08]** The project does NOT use Railpack — a committed `Dockerfile` is the active builder (Railway prefers it over Railpack), so builder-version drift cannot affect the build; dependencies are pinned in `uv.lock` and installed by `uv sync --frozen --no-dev` inside a pinned `python:3.12-slim` base. To restore Railpack, delete the Dockerfile — but that reintroduces this risk. |
| Region immutability / Pro-only region selection forecloses a cheap latency fix if users spread | Devil's advocate | L | L | Interview confirmed single region is fine for the MVP; if user geography spreads, the remedy is a $20/mo Pro plan or migrating the Postgres + app together — capture this as a post-MVP decision, not a current blocker. |
| Volume Backups are beta (restore limited to same project+env, manual backup ≤ 50% volume size) | Unknown unknowns | L | M | Don't rely on Volume Backups as the sole DB restore path; run nightly `pg_dump` to an external bucket (S3/R2) via a Railway Cron Job; verify a test restore from the external dump before relying on it. |
| Ephemeral filesystem losses (if any file storage is added) silently disappear on redeploy | Unknown unknowns | L | L | Serve static via WhiteNoise (`CompressedManifestStaticFilesStorage`) from the Django process; if media is ever added, use an external object store (S3/R2) or an attached Railway Volume on a single-instance pinned service — never the container FS. |
| `DATABASE_URL` self-signed TLS causes connection failures with `verify-ca`/`verify-full` | Research finding | M | L | Use `sslmode=require` in the `DATABASE_URL` (Railway Postgres self-signed certs don't support verify modes without extra config); document the `sslmode` choice in the settings module. |

## Getting Started

Concrete first steps to deploy Stock Guard to Railway, validated against the exact stack (Django 6.1 / Python 3.12 / `uv` / Postgres). All commands current as of 2026-09-25; CLI version `@railway/cli` v5.62.1. **[corrected 2026-10-08]** Steps 1, 4, and 5 updated to the build path actually used (committed Dockerfile, dashboard settings, `targetPort`).

1. **Pin the Python version in the repo (not via a Railpack var).** This stack pins `requires-python = ">=3.12"`; commit a `.python-version` file containing `3.12`. **[corrected 2026-10-08]** Do **not** rely on `RAILPACK_PYTHON_VERSION` — the project builds via a committed Dockerfile (`python:3.12-slim`), not Railpack, so a Railpack var is inert.

2. **Install the Railway CLI and link the project.**
   ```bash
   npm i -g @railway/cli          # or: bash <(curl -fsSL cli.new)
   railway login
   railway link                    # link this repo to a Railway project
   ```

3. **Provision Postgres and wire `DATABASE_URL`.** Add a PostgreSQL service and let Railway auto-provision `DATABASE_URL`, `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE`:
   ```bash
   railway add                     # choose PostgreSQL
   ```
   In `stock_guard/settings.py`, read it with `dj-database-url` and set `sslmode=require` (Railway Postgres uses self-signed TLS):
   ```python
   import dj_database_url
   DATABASES = {"default": dj_database_url.config(conn_max_age=600, ssl_require=True)}
   ```
   Add `dj-database-url` to `pyproject.toml` deps via `uv add dj-database-url`.

4. **Set the required Django env vars and configure the service via the dashboard.** Via `railway variables set`:
   ```
   DJANGO_SETTINGS_MODULE=stock_guard.settings
   SECRET_KEY=<generated>          # generate with: uv run python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
   ALLOWED_HOSTS=<your-app>.up.railway.app,healthcheck.railway.app,<service>.railway.internal
   ```
   **[corrected 2026-10-08]** Config-as-Code is deprecated (2026-12-01 cutoff) and unavailable to new services. Instead, in the service's dashboard Settings → Deploy panel set: `preDeployCommand = ["uv run python manage.py migrate --noinput"]`, `healthcheckPath = /health/`, and leave `startCommand` empty so the committed **Dockerfile `CMD`** governs. The Dockerfile runs `uv sync --frozen --no-dev` and `collectstatic --noinput` at build time, then starts `uv run gunicorn --bind 0.0.0.0:${PORT:-8000} stock_guard.wsgi:application`. **Also set the service domain `targetPort = 8080`** to match Railway's injected `PORT=8080` — otherwise the Router's default `8000` 502s the healthcheck (verified failure mode, 2026-10-07). `ALLOWED_HOSTS` must include `healthcheck.railway.app` or the internal probe gets a 400 with `DEBUG=False`. Do **not** set `RAILPACK_*` vars — the build is Dockerfile-based.

5. **Deploy and verify.**
   ```bash
   railway up                       # deploys; block until complete
   railway logs --tail              # stream deploy + runtime logs
   ```
   Verification: the deploy URL (`https://<your-app>.up.railway.app`) should reach the login screen; `migrate` output appears in logs; `collectstatic` completes with no errors. If a migration fails, the deploy fails before serving traffic (safer than serving a half-migrated schema).

6. **Agent ops baseline (read-only).** With the GA Railway MCP server configured (`mcp.railway.com` via Remote OAuth, or `railway mcp` local proxy; CLI ≥5.44.0), the agent can call `list-services`, deploy status, `redeploy`, and `railway-agent` for multi-step ops. Rollback remains a human dashboard action — document the click sequence (Service → Deployments → ⋮ → Rollback) in `deploy-plan.md` as a runbook step, and keep a "last known good" commit/build tag so a CLI re-deploy of the prior image is the agent's fallback when a human isn't immediately available.

## Out of Scope

The following were not evaluated in this research:
- Docker image configuration (**[corrected 2026-10-08]** originally out of scope; in execution a minimal committed `Dockerfile` became the active build path because Railway prefers it over Railpack — it is small and single-stage, not a hand-tuned image)
- CI/CD pipeline setup (GitHub Actions auto-deploy-on-merge is the intended `tech-stack.md` hand-off and is configured in the deploy phase, not here)
- Production-scale architecture (multi-region HA, DR, read replicas, dedicated support tiers) — explicitly out of scope per the skill's MVP focus; the PRD's scale is `small` users / `low` qps / `small` data
