# Account Auth Scaffold Implementation Plan

## Overview

Deliver roadmap foundation **F-01** (`account-auth-scaffold`): per-account sign-up and login screens backed by Django's auth, so an unauthenticated visitor lands on the login screen and every later view can resolve `request.user`. This is the gate that unblocks the private-watchlist chain (S-01, S-02, S-03).

## Current State Analysis

- The repo is a pure Django 6.1.1 scaffold: `stock_guard/urls.py` serves only `/health/` and `/admin/` (`stock_guard/urls.py:27-30`). There is no feature app, no `templates/`, and no product static asset.
- `django.contrib.auth` is installed (`stock_guard/settings.py:49`), `AuthenticationMiddleware` is wired (`stock_guard/settings.py:62`), the four password validators are configured (`stock_guard/settings.py:113-126`), and `sessions` + `messages` are installed.
- `TEMPLATES.OPTIONS.APP_DIRS=True` (`stock_guard/settings.py:73`) and the default static finders mean app-local templates/static need **no** settings change; the only settings deltas are `INSTALLED_APPS` plus the auth URL settings.
- Auth-related defaults to override (Django `global_settings.py:539-543`): `LOGIN_URL="/accounts/login/"`, `LOGIN_REDIRECT_URL="/accounts/profile/"`, `LOGOUT_REDIRECT_URL=None`.
- Verified against the installed Django 6.1.1 in `.venv`: the auth app ships **no** `login.html` (only `password_reset_subject.txt`), and `LoginView.template_name = "registration/login.html"` (`django/contrib/auth/views.py:84`); `LogoutView.http_method_names = ["post", "options"]` (`django/contrib/auth/views.py:134`); `UserCreationForm`/`AuthenticationForm` key on `USERNAME_FIELD` (`django/contrib/auth/forms.py:213`, `:305`); the default `username` field is `unique` with `max_length=150` (`django/contrib/auth/models.py:461`).
- Prod Postgres is already migrated (built-in auth tables applied by Railway's `preDeployCommand`), and the CI gate runs `check`, `makemigrations --check`, `collectstatic`, and `check --deploy` (`.github/workflows/ci.yml`).

## Desired End State

A visitor who opens `/` while anonymous is redirected to `/login/`. They can register an account with email + password, are signed in automatically, land on a minimal placeholder home, and can log out (returning to `/login/`). Every later view can call `request.user`. Verification: `uv run python manage.py test accounts` passes and the register → login → logout flow works in a browser.

### Key Discoveries:

- Email-based login is required by the PRD (FR-002, `context/foundation/prd.md:112-125`), but Django's default `User` keys on `username`. Resolved by storing the normalized email as `username` — no `AUTH_USER_MODEL` change against an already-migrated live database.
- `accounts/templates/registration/login.html` is the exact path `LoginView` expects; a missing template is a hard 500 on first use.
- `LogoutView` is POST-only in Django 6.1, so logout must be a CSRF-protected `<form>`.
- No template/static **settings** change is needed — app directories are already discovered.

## What We're NOT Doing

- No custom user model / `AUTH_USER_MODEL` (decision: default `User`, email-as-username).
- No password reset, email verification, "remember me", social/OAuth login, or rate limiting — none are in the PRD.
- No watchlist models, views, or scan logic (that is S-01 and later); `/` is only a placeholder.
- No profile page and no admin-role changes (the model is flat).
- No CI wiring of pytest/mypy/ruff, and not the S-04 end-to-end test — recorded as a follow-up; the existing CI gate stays as-is.
- No styling framework and no JS toolchain.

## Implementation Approach

Create a thin `accounts` app that owns the auth surface, reusing Django's built-in `LoginView`/`LogoutView` and adding two form subclasses: `EmailUserCreationForm` (collects email + password, derives `username = email`) and `EmailAuthenticationForm` (relabels the identifier field to "Email"). Templates are plain Django templates with one small stylesheet, and `/` is a `login_required` placeholder home. Settings gain `INSTALLED_APPS` plus the three URL settings; the root URLconf includes the app's routes and the home view.

## Critical Implementation Details

- **Email normalization is the correctness hinge.** Both the sign-up form and the login form must apply the same normalization (`email.strip().lower()`) so a stored account and its later login hash to the same `username`. If the two diverge, login silently fails for every account.
- **Logout must be a POST form.** With Django 6.1 a `GET /logout/` returns 405; the UI must submit `<form method="post">` with `{% csrf_token %}`.
- **The 150-char `username` cap bounds stored email length.** Reject over-long emails as a form validation error rather than letting the value fail later as a raw save/DB error.

## Phase 1: App scaffold & auth settings wiring

### Overview

Create the `accounts` app, register it, and point Django's auth at the project's URLs — a booting scaffold with no user-visible behavior yet.

### Changes Required:

#### 1. New `accounts` app

**File**: `accounts/` (app package: `apps.py`, `__init__.py`, `models.py`, `views.py`, `forms.py`, `urls.py`, `admin.py`, `migrations/__init__.py`, `tests.py`)

**Intent**: Create the app that owns registration/login/logout so auth wiring does not live in the project package; keep `models.py` empty because the default `User` is used.

**Contract**: `accounts.apps.AccountsConfig` with `name = "accounts"` and `default_auto_field = "django.db.models.BigAutoField"`.

#### 2. Register the app and configure auth URLs

**File**: `stock_guard/settings.py`

**Intent**: Add the app to `INSTALLED_APPS` and replace the three auth-redirect defaults with project URLs.

**Contract**: append `"accounts"` to `INSTALLED_APPS`; set `LOGIN_URL = "/login/"`, `LOGIN_REDIRECT_URL = "/"`, `LOGOUT_REDIRECT_URL = "/login/"`.

#### 3. Root URL wiring

**File**: `stock_guard/urls.py`

**Intent**: Mount the app's auth routes and keep `/health/` + `/admin/` untouched.

**Contract**: `path("", include("accounts.urls"))`, keeping the existing `health/` and `admin/` entries.

### Success Criteria:

#### Automated Verification:

- Django system checks pass: `uv run python manage.py check`
- No migration drift is introduced: `uv run python manage.py makemigrations --check --dry-run`
- Static collection still succeeds: `uv run python manage.py collectstatic --noinput`

#### Manual Verification:

- Server boots and `/health/` returns `ok` while `/admin/` still loads.

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 2: Registration + login/logout flow

### Overview

Email-based sign-up plus login/logout with templates, so a user can create an account and sign in and out through the UI.

### Changes Required:

#### 1. Forms

**File**: `accounts/forms.py`

**Intent**: Present and validate **email** as the identifier for both sign-up and login, layered on the default `User`.

**Contract**: `EmailUserCreationForm(UserCreationForm)` exposes `email`, `password1`, `password2`. Because `UserCreationForm` is a `ModelForm` with `Meta.fields = ("username",)` bound to `User.USERNAME_FIELD`, `username` stays a required bound field: keep it in `Meta.fields` and render it as a hidden input (never shown to the user), and populate it from the normalized email. `clean_email` normalizes and enforces uniqueness (case-insensitive) plus the 150-char limit; `save()` sets both `username` and `email` to the normalized value. `EmailAuthenticationForm(AuthenticationForm)` relabels `username` to "Email" and normalizes the submitted identifier in a `clean_username` override (which runs before `clean()` reads `cleaned_data["username"]` and calls `authenticate(username=...)`) — not inside `clean()` before delegating. The shared normalization contract, which both forms must use:

```python
normalized_email = self.cleaned_data["email"].strip().lower()
```

#### 2. Views

**File**: `accounts/views.py`

**Intent**: Add a registration view that signs the new user in on success and redirects to the login redirect target, plus a `login_required` placeholder home; reuse built-in `LoginView`/`LogoutView` for the rest.

**Contract**: `register(request)` → on valid form, `login(request, user)` then redirect to `settings.LOGIN_REDIRECT_URL`; `home(request)` decorated with `@login_required`, rendering `accounts/home.html`. `views.py` owns `register` and `home` only; the `LoginView` subclass wiring (`authentication_form=EmailAuthenticationForm`) belongs to `accounts/urls.py` (Contract #3).

#### 3. URLs

**File**: `accounts/urls.py`

**Intent**: Expose the four routes the project and tests resolve.

**Contract**: routes `login/` (`LoginView.as_view(authentication_form=EmailAuthenticationForm)`, `name="login"`), `logout/` (`LogoutView`, `name="logout"`), `register/` (`register`, `name="register"`), and `""` (`home`, `name="home"`), mounted under the root `include` so final paths are `/login/`, `/logout/`, `/register/`, `/`.

#### 4. Templates

**File**: `accounts/templates/` — `base.html`, `registration/login.html`, `registration/register.html`, `registration/logged_out.html`, `accounts/home.html`

**Intent**: Minimal server-rendered pages sharing one base; surface field errors and the `next` round-trip; logout is a POST form.

**Contract**: `registration/login.html` is the path `LoginView` requires; it renders `form.non_field_errors`, carries a hidden `next` input, and posts to the login URL. Logout is `<form method="post" action="{% url 'logout' %}">{% csrf_token %}<button>Log out</button></form>`. `registration/logged_out.html` is what `LogoutView` renders when it does not redirect.

#### 5. Stylesheet

**File**: `accounts/static/accounts/css/auth.css`

**Intent**: Small hand-written styling for the auth pages, with no framework.

**Contract**: Linked from `base.html` and discovered by the default app static finder (no `STATICFILES_DIRS` change).

### Success Criteria:

#### Automated Verification:

- Django system checks pass: `uv run python manage.py check`
- Static collection succeeds and includes the auth stylesheet: `uv run python manage.py collectstatic --noinput`

#### Manual Verification:

- Registering a new email lands the user signed-in on `/`.
- Logging out via the button returns to `/login/`.
- Logging in with the same email and password returns to `/`.
- A duplicate email at sign-up shows a form error, not a 500.
- An over-long (more than 150 characters) email shows a form error, not a 500.

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 3: Protected landing & access control + tests

### Overview

Lock down `/` for anonymous visitors and prove the whole flow with Django `TestCase`s.

### Changes Required:

#### 1. Route protection and redirect behaviour

**File**: `accounts/views.py` and `stock_guard/settings.py`

**Intent**: Ensure anonymous access to `/` redirects to login and returns the user to `/` after authenticating.

**Contract**: `home` carries `@login_required`; `LOGIN_URL="/login/"` (set in Phase 1) drives the redirect; `LoginView`'s built-in `?next=` handling (`RedirectURLMixin`) is authoritative — it returns to `next` when present and falls back to `LOGIN_REDIRECT_URL` otherwise, so no custom redirect view is needed.

#### 2. Auth tests

**File**: `accounts/tests.py`

**Intent**: Cover the primary capability — log in, resolve the current user, log out — and the access-control guard.

**Contract**: `TestCase` subclasses with method names of the form `...Returns...When...`. Cases: registration creates exactly one user whose `username` and `email` both equal the normalized email; duplicate email is rejected; an anonymous `GET /` redirects to `/login/?next=/`; valid login reaches `/`; invalid login re-renders with an error; `GET /logout/` returns 405 while an authenticated `POST /logout/` logs the user out and redirects to `LOGOUT_REDIRECT_URL` (`/login/`); two users each resolve only their own `request.user`.

### Success Criteria:

#### Automated Verification:

- Django test suite passes: `uv run python manage.py test accounts`
- Django system checks pass: `uv run python manage.py check`
- Migration drift check is clean: `uv run python manage.py makemigrations --check --dry-run`

#### Manual Verification:

- Visiting `/` logged out shows the login screen; logging in shows the placeholder home with the user's email.
- The logout button returns to `/login/`, and browser Back does not re-show the authenticated home.
- `/register/` is reachable while logged out and `/` is not.

---

## Testing Strategy

### Unit Tests:

- Registration form: normalization, duplicate rejection, password validators, 150-char guard.
- Login form: normalization parity with registration (same email resolves to the same `username`).
- View access: `login_required` redirect and the `next` round-trip.

### Integration Tests:

- A `register → login → logout` HTTP flow through the Django test client, asserting only the acting user is resolved.

### Manual Testing Steps:

1. `uv run python manage.py migrate` (dev SQLite), then `uv run python manage.py runserver`.
2. Register `marek@example.com` and confirm the auto-login landing on `/`.
3. Log out, then log in again, and confirm the landing.
4. Confirm `/` redirects while logged out and `/register/` is reachable while logged out.
5. Try a duplicate email and an over-long email.

## Performance Considerations

Not applicable — the auth pages are a single form over a single query each, with no scan or external-API path in this change.

## Migration Notes

No new models and therefore **no migrations**; the default `auth.User` tables already exist in prod. The local `db.sqlite3` stays empty of auth rows until a test or registration run. Deploying this change requires no Railway environment variable or `preDeployCommand` change.

## References

- Roadmap item F-01: `context/foundation/roadmap.md:74-85`
- PRD FR-001/FR-002 and Access Control: `context/foundation/prd.md:66-69`, `context/foundation/prd.md:112-125`
- Existing scaffold: `stock_guard/urls.py:27-30`, `stock_guard/settings.py:47-73`
- Installed Django auth: `.venv/lib/python3.12/site-packages/django/contrib/auth/views.py:84`, `forms.py:213`, `models.py:461`
- CI gate: `.github/workflows/ci.yml`
- Deploy foundation: `context/deployment/deploy-plan.md`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: App scaffold & auth settings wiring

#### Automated

- [x] 1.1 Django system checks pass
- [x] 1.2 No migration drift introduced
- [x] 1.3 Static collection succeeds

#### Manual

- [x] 1.4 Server boots and /health/ and /admin/ respond

### Phase 2: Registration + login/logout flow

#### Automated

- [ ] 2.1 Django system checks pass
- [ ] 2.2 Static collection succeeds and includes the auth stylesheet

#### Manual

- [ ] 2.3 Registering a new email lands the user signed-in on /
- [ ] 2.4 Logging out via the button returns to /login/
- [ ] 2.5 Logging in with the same email and password returns to /
- [ ] 2.6 A duplicate email at sign-up shows a form error, not a 500
- [ ] 2.7 An over-long email shows a form error, not a 500

### Phase 3: Protected landing & access control + tests

#### Automated

- [ ] 3.1 Django test suite passes
- [ ] 3.2 Django system checks pass
- [ ] 3.3 Migration drift check is clean

#### Manual

- [ ] 3.4 Visiting / logged out shows the login screen; logging in shows the placeholder home with the user's email
- [ ] 3.5 The logout button returns to /login/, and browser Back does not re-show the authenticated home
- [ ] 3.6 /register/ is reachable while logged out and / is not
