# Lessons Learned

> Append-only register of recurring rules and patterns. Re-read at start by /10x-frame, /10x-research, /10x-plan, /10x-plan-review, /10x-implement, /10x-impl-review.

## Verify platform feature availability against live docs before writing it into a plan

- **Context**: Any infra-research or deploy-plan phase that cites a specific platform feature (config-as-code, builder selection, start commands, env-var names) as an instruction.
- **Problem**: `infrastructure.md` (researched 2026-09-25) instructed "Use Railway's Config-as-Code" and pinned `RAILPACK_*` vars; by deploy time (2026-10-05) Config-as-Code was deprecated with a hard 2026-12-01 cutoff and unavailable to new services, and Railpack was never the active builder (Railway prefers a committed Dockerfile). The plan propagated two dead instructions; both had to be corrected mid-execution.
- **Rule**: Before a platform feature lands in a plan or infra doc, fetch the platform's live docs and confirm the feature is GA and available to a *new* resource on the target plan; record the doc URL and the date checked next to the instruction.
- **Applies to**: research, plan, plan-review

## A deployed container must bind the port the router expects — verify both sides

- **Context**: Deploying any gunicorn/uvicorn/WSGI app behind a platform router that injects `PORT` (Railway, Render, Heroku-style).
- **Problem**: On Railway, gunicorn `--bind 0.0.0.0:${PORT:-8000}` listened on the injected `PORT=8080`, but the service domain's Router `targetPort` defaulted to `8000` → healthcheck "service unavailable" → 4 consecutive failed deploys. An explicit bind alone was not sufficient; the router-side port had to match too.
- **Rule**: When deploying behind a router that injects `PORT`, set BOTH the process bind (`0.0.0.0:$PORT`) AND the service's target/container port to the same injected value, and add a DB-free `/health/` endpoint as the healthcheck so a port mismatch fails the deploy loudly instead of surfacing as prod 502s.
- **Applies to**: plan, implement, impl-review
