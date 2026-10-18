<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Account Auth Scaffold Implementation Plan

- **Plan**: context/changes/account-auth-scaffold/plan.md
- **Scope**: Full plan
- **Reviewed phases**: 1, 2, 3
- **Date**: 2026-10-18
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical · 2 warnings · 3 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | PASS |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | PASS |

## Findings

### F1 — Registration duplicate path can 500 on concurrent/race insert

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: accounts/forms.py:26-28, accounts/forms.py:35-36
- **Detail**: `clean_email` does a non-atomic `User.objects.filter(username__iexact=...).exists()` check, then `save()` inserts. Two concurrent registrations of the same email both pass the check; the second INSERT hits the case-sensitive DB unique index on `username` and raises an uncaught `IntegrityError` → 500. This violates the plan's own manual criterion "a duplicate email shows a form error, not a 500" (plan.md:158). Low likelihood for an MVP (single-user sign-up, no load), but the plan explicitly promised no 500.
- **Fix**: Wrap the registration save in `transaction.atomic()` and catch `IntegrityError` in `register` (accounts/views.py:12-15) to re-render the form with a duplicate error.
  - Strength: Closes the 500 path; matches the plan's stated criterion without schema churn.
  - Tradeoff: Small — a try/except around the save plus a form error.
  - Confidence: MEDIUM — sufficient for the MVP; a full fix also wants a `UniqueConstraint(Lower("username"))` DB guard.
  - Blind spot: A DB-level case-insensitive constraint would fully align app and DB, but that requires a migration and is out of this change's no-migration scope.
- **Decision**: FIXED — wrapped save in `transaction.atomic()` and caught `IntegrityError` in `register` (accounts/views.py)

### F2 — Registration ignores `?next=` while login honors it

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: accounts/views.py:15, accounts/templates/registration/register.html:7
- **Detail**: `register` hardcodes `redirect(settings.LOGIN_REDIRECT_URL)`, and `register.html` does not forward `next`. `LoginView` does honor `?next=` (plan.md:179). A user sent to `/login/?next=/x/` who clicks "Register" and signs up lands on `/` instead of `/x/`. Copying the hidden `next` into the login template (login.html:11) but not register is an inconsistency, not a spec break — the plan never requires register to carry `next`.
- **Fix**: Either forward `next` through register.html → `register` and redirect to the validated `next` (`url_has_allowed_host_and_scheme`), or accept the current behavior explicitly.
- **Decision**: FIXED — `register` now forwards a validated `next` via `_safe_next` (accounts/views.py), register.html carries a hidden `next`, and a round-trip test was added.

### F3 — Registration uniqueness check enables user enumeration

- **Severity**: ○ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: accounts/forms.py:26-27
- **Detail**: `"An account with this email already exists."` confirms whether an email is registered. Consistent with the PRD's email-based, no-verification MVP, so acceptable now; revisit if the product cares about enumeration.
- **Fix**: None now — note only.
- **Decision**: SKIPPED — acceptable for the PRD's email-based, no-verification MVP.

### F4 — `save(commit=False)` on an unvalidated form would KeyError

- **Severity**: ○ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: accounts/forms.py:31-38
- **Detail**: `save()` reads `self.cleaned_data["email"]` unconditionally. The only call site (accounts/views.py:13) saves after `is_valid()`, so there is no live bug; future callers using `save(commit=False)` without validation would raise `KeyError`.
- **Fix**: None now — note only.
- **Decision**: SKIPPED — no live caller; affects only hypothetical future `commit=False` use.

### F5 — No login-form normalization-parity test

- **Severity**: ○ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: accounts/tests.py
- **Detail**: The plan's Testing Strategy calls for "same email resolves to the same `username`" (plan.md:210). `LoginTests` covers a mixed-case login (tests.py:69-78), which exercises parity in practice, but there is no explicit case-collision test (a stored mixed-case username) and no isolated login-form normalization unit test.
- **Fix**: Optional — add a test asserting a mixed-case stored username logs in as expected.
- **Decision**: SKIPPED — mixed-case login parity is exercised by `LoginTests`; the case-collision edge is an accepted MVP gap.
