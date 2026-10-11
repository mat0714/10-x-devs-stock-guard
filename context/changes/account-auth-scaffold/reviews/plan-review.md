<!-- PLAN-REVIEW-REPORT -->
# Plan Review: Account Auth Scaffold Implementation Plan

- **Plan**: context/changes/account-auth-scaffold/plan.md
- **Mode**: Deep
- **Date**: 2026-10-11
- **Verdict**: REVISE → SOUND (after fixes)
- **Findings**: 1 critical · 4 warnings · 2 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| End-State Alignment | PASS |
| Lean Execution | PASS |
| Architectural Fitness | WARNING |
| Blind Spots | WARNING |
| Plan Completeness | FAIL |

## Grounding
7/7 paths ✓, 9/9 symbols ✓, brief↔plan ✓. Progress↔Phase contract well-formed (3 phases matched by number, every Success Criteria bullet has a matching `N.M` step, no `- [ ]` outside Progress). `docs/reference/contract-surfaces.md` absent — check skipped. Django 6.1.1 claims verified against `.venv` (`LoginView.template_name`, `LogoutView` POST-only, `USERNAME_FIELD`, 150-char unique username, `TEMPLATES.APP_DIRS=True`). Neither `lessons.md` rule applies (both deploy-time infra).

## Findings

### F1 — EmailUserCreationForm contract omits the required `username` field

- **Severity**: ❌ CRITICAL
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 2 — Forms
- **Detail**: `UserCreationForm` → `BaseUserCreationForm` is a `ModelForm` with `Meta.fields = ("username",)` bound to `User.USERNAME_FIELD` (`forms.py:218-226`, `models.py:461`). `username` remains a required bound field that must be present and filled or the form never validates. The plan said the form "exposes `email`, `password1`, `password2`" and `save()` sets both — but never stated `username` stays in `Meta.fields` (hidden) and is populated.
- **Fix**: State that `EmailUserCreationForm` keeps `username` in `Meta.fields`, renders it hidden, and fills it in `clean_email`/`save()`.
- **Decision**: FIXED

### F2 — Normalization must run in clean_username, not "before delegating"

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Blind Spots
- **Location**: Phase 2 — Forms / Critical Implementation Details
- **Detail**: "normalizes the submitted identifier identically before delegating" was ambiguous. `AuthenticationForm` is a plain `Form` whose `clean()` reads `cleaned_data["username"]` then calls `authenticate(username=...)` (`forms.py:305-347`). Normalization must happen in a `clean_username` override, which runs before `clean()`.
- **Fix**: Specify `EmailAuthenticationForm.clean_username` returns the normalized value via the same helper as the creation form.
- **Decision**: FIXED (folded into F1 edit)

### F3 — Login redirect mechanism (?next= vs LOGIN_REDIRECT_URL) undecided

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Blind Spots
- **Location**: Phase 3 — Route protection and redirect behaviour
- **Detail**: `LoginView` → `RedirectURLMixin` uses `?next=` when present, else `LOGIN_REDIRECT_URL` (`views.py:36-101`). The plan never stated which wins, risking redundant custom `next` handling.
- **Fix**: One line: `LoginView`'s built-in `?next=` handling is authoritative; no custom redirect view.
- **Decision**: FIXED

### F4 — Logout test asserts 405 but not the redirect target

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Architectural Fitness
- **Location**: Phase 3 — Auth tests
- **Detail**: The test contract listed the 405/GET and POST-logout cases but gave no redirect-target assertion, so a wrong-redirect regression would pass. `LogoutView.http_method_names = ["post","options"]` (`views.py:139`).
- **Fix**: Assert the POST redirects to `LOGOUT_REDIRECT_URL` (`/login/`).
- **Decision**: FIXED

### F5 — "LoginView instantiated with authentication_form" appears in two phases

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 2 — Views / URLs
- **Detail**: Phase 2 Contract #2 (views.py) claimed the `authentication_form=` wiring, but the route lives in `accounts/urls.py`. Two files claiming the wiring risks duplication or misplacement.
- **Fix**: Attribute the wiring to `accounts/urls.py` only; `views.py` owns `register` + `home`.
- **Decision**: FIXED

### F6 — Registration tests should not assume a specific validator message

- **Severity**: ○ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Blind Spots
- **Location**: Testing Strategy
- **Detail**: `UserAttributeSimilarityValidator` compares the password against `username`, now the full email; a password resembling the email is rejected with an email-referencing message. Tests should use a strong password unrelated to the email.
- **Fix**: None — note only.
- **Decision**: SKIPPED

### F7 — New users are active by default; no action needed

- **Severity**: ○ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 3 — Auth tests
- **Detail**: `register` auto-logins without an `is_active` check; Django's default `User.is_active=True` makes this correct. No change required.
- **Fix**: None — default is correct.
- **Decision**: SKIPPED
