# Account Auth Scaffold — Plan Brief

> Full plan: `context/changes/account-auth-scaffold/plan.md`

## What & Why

Build roadmap foundation **F-01**: per-account sign-up and login screens backed by Django's auth, so an unauthenticated visitor lands on the login screen and every later view can resolve the current user. It exists because the confirmed persona is multi-user with private watchlists (FR-001/FR-002, Access Control), so account separation is load-bearing before any per-user data can exist.

## Starting Point

The repo is a bare Django 6.1.1 scaffold: `stock_guard/urls.py` serves only `/health/` and `/admin/`; there is no feature app, no templates, and no product static assets. `django.contrib.auth`, `AuthenticationMiddleware`, sessions, and the password validators are already installed and wired, and prod Postgres is already migrated with the built-in auth tables — so this change adds the app and the UI surface, not the auth machinery.

## Desired End State

An anonymous visitor to `/` is redirected to `/login/`. They can register with email + password, are signed in automatically onto a minimal placeholder home, and can log out back to `/login/`. Every later view can call `request.user`, and the S-01 watchlist can replace the placeholder without touching auth.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| -------- | ------ | ---------------- | ------ |
| User / login model | Default `auth.User`, normalized email stored in both `username` and `email` | Delivers the PRD's email login with zero schema churn against an already-migrated prod DB | Plan |
| App & URL structure | New `accounts` app; `/login/`, `/logout/`, `/register/` | Matches the repo's "feature apps in `INSTALLED_APPS`" convention and keeps the project package thin | Plan |
| Post-login landing | Minimal `login_required` placeholder home at `/` | Gives S-01 a single drop-in point and proves the session works today | Plan |
| Sign-up session flow | Auto-login after a successful registration | Fewest steps for the MVP and consistent with the "authenticated = sees own data" model | Plan |
| Logout | Included, via a POST-only form | Django 6.1 `LogoutView` is POST-only and account separation needs it | Plan |
| Templates / assets | Plain Django templates + one small stylesheet, no framework | No JS toolchain exists in the repo to justify adding one | Plan |
| Tests vs CI | `accounts/tests.py` `TestCase`s now; pytest/mypy/ruff CI wiring deferred | Keeps this change focused; CI wiring is tracked as a follow-up item | Plan |
| Email login identifier | PRD-mandated email + password; open self-registration | Settled upstream by the PRD's Access Control section | PRD (F-01) |

## Scope

**In scope:**
- `accounts` app registered in `INSTALLED_APPS`; `LOGIN_URL`/`LOGIN_REDIRECT_URL`/`LOGOUT_REDIRECT_URL` settings.
- Email sign-up (normalized), login, logout; base + auth templates; minimal stylesheet.
- `login_required` placeholder home at `/`; anonymous `/` → `/login/?next=/`.
- `accounts/tests.py` covering the auth flow and access control.

**Out of scope:**
- Custom user model, password reset, email verification, "remember me", social login, rate limiting.
- Watchlist models/views/scan (S-01+); the `/` page is a placeholder only.
- Profile page, admin-role changes, CI wiring of pytest/mypy/ruff, and the S-04 end-to-end test.

## Architecture / Approach

A thin `accounts` Django app owns the auth surface and reuses built-in `LoginView`/`LogoutView`, adding `EmailUserCreationForm` (collects email + password, derives `username = email`) and `EmailAuthenticationForm` (relabels the identifier to "Email", same normalization). The root URLconf includes the app; `settings.py` gains the app and three URL settings. Everything is server-rendered; `/` is a `login_required` placeholder.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| ----- | ---------------- | -------- |
| 1. App scaffold & auth settings wiring | Booting `accounts` app + auth URL settings | No user-visible outcome yet; wiring errors surface only through checks |
| 2. Registration + login/logout flow | Email sign-up (auto-login) + login/logout UI | Email normalization parity between sign-up and login; POST-only logout |
| 3. Protected landing & access control + tests | `login_required` home + auth tests | Access-control regressions; keeping the placeholder narrow enough for S-01 to replace |

**Prerequisites:** None — F-01 has no prerequisites and runs in parallel with F-02 (price-data fetch boundary).
**Estimated effort:** ~2-3 sessions across the three phases.

## Open Risks & Assumptions

- Storing email in `username` assumes account emails fit Django's 150-char `username` cap; over-long emails are rejected as a form error rather than failing later.
- The placeholder `/` page is intentionally throwaway and will be replaced by S-01's watchlist.
- Without email verification, any well-formed email string can register — accepted for the MVP, whose email backend is console-only.
- CI does not yet run tests or mypy/ruff, so this change's tests (including any that land early) are local-only until a follow-up wires them into `ci.yml`.
- No Railway env or `preDeployCommand` change is needed; the built-in `auth` tables already exist in prod.

## Success Criteria (Summary)

- Anonymous `/` lands on login; register → auto-signed-in → placeholder home → logout returns to login.
- Every subsequent view resolves `request.user`, and two accounts see only their own identity.
- `uv run python manage.py test accounts` is green with no migration drift.
