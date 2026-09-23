---
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
---

## Why this stack

Custom path even though Django is the recommended default for (web-app, python): the user signaled a JS frontend preference plus a backend language with strong financial-analysis libraries. Backend locked to Python for pandas + ta (double-top/RGR detection per FR-009), then Django chosen over FastAPI+React and FastAPI+Jinja because auth is a confirmed must-have (FR-001/FR-002) and Django's batteries (auth + ORM + admin + migrations) minimize assembly in a 3-week after-hours solo MVP. Detection logic stays in a service module (`score_formation(price_series)`) so a future Django-templates-to-SPA migration is bounded — add Django Ninja/DRF for the API, swap session auth for JWT, keep models and detection intact. Django fails the typed agent-friendly gate (duck-typed at runtime); user accepted (quality_override: true) with compensation via AGENTS.md: type hints at boundaries + Pydantic for request validation + mypy in CI. Deployment lands on Railway Hobby — single vendor for Django app + managed Postgres, ~$7-8/mo realistic for low-traffic solo, no cold starts; picked over Render Free + Neon to skip the 60s Render cold starts and over Fly.io's ~$38/mo to save ~$30/mo. GitHub Actions with auto-deploy-on-merge is the default for solo + small. Bootstrapper confidence: verified.
