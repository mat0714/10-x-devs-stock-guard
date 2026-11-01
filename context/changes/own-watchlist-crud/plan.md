# Own Watchlist CRUD Implementation Plan

## Overview

Deliver roadmap slice **S-01** (`own-watchlist-crud`): a logged-in user can add a stock (ticker + optional name) to their own private watchlist, view that list ordered A→Z, and hard-remove a stock from it — seeing only their own data. This is the list surface the future detection/scan slices (S-02, S-03) render flags on, so it deliberately ships before any formation math.

## Current State Analysis

- The repo is a Django 6.1.1 project with two apps: `accounts` (auth; **no models** — `accounts/models.py` is a placeholder) and `marketdata` (the only model, `DailyCandle`). There is **no watchlist app, model, view, or template**; S-01 creates all of it.
- Auth is the **default `User`** with email-as-username (`accounts/forms.py:7-38`); watchlist rows must FK to `settings.AUTH_USER_MODEL`.
- `/` is currently a throwaway placeholder: `accounts/urls.py:15` maps `""` → `home`, and `accounts/views.py:39-41` is a bare `@login_required` view rendering `accounts/templates/accounts/home.html`. F-01 documented this placeholder as intended to be replaced by S-01 (`context/changes/account-auth-scaffold/plan-brief.md:61`).
- The ticker format is **already decided upstream**: store the **bare uppercase US ticker**, no provider suffix, normalizing `strip().upper()` (`context/changes/price-data-fetch-boundary/research.md:148-153`); the fetch service already normalizes the same way (`marketdata/services.py`). Add-time validation was explicitly deferred to S-01 (`price-data-fetch-boundary/plan.md:47`). `DailyCandle.symbol` is `CharField(max_length=16)` (`marketdata/models.py:5`), so the watchlist symbol must fit the same width.
- CI (`.github/workflows/ci.yml`) runs `check`, `makemigrations --check --dry-run`, `collectstatic --noinput`, and `check --deploy` — a **committed migration is mandatory**; the test suite is **not** run in CI.
- Conventions to mirror: function-based views with `@login_required`; DB writes wrapped in `transaction.atomic()` with an `IntegrityError` → form-error fallback (`accounts/views.py:11-27`, F-01 review F1); forms subclass Django built-ins and normalize inside `clean_<field>` (`accounts/forms.py:22-29`); templates extend `accounts/templates/base.html`; tests are `django.test.TestCase` with `test_...Returns...When...` names and hardcoded URL strings (`accounts/tests.py:7-151`).

## Desired End State

A logged-in user opens `/` and sees their own watchlist — an inline add form at the top and their stocks listed A→Z below, each row with a Remove button. Adding `aapl` stores `AAPL`; adding the same ticker twice (any case) shows an inline error; an invalid symbol format shows an inline error; a blank name renders the ticker only. Removing a stock takes it off the list. An unauthenticated visitor to `/` is redirected to `/login/?next=/`, and one user can never see or delete another user's row.

Verification: `uv run python manage.py test watchlist` and `uv run python manage.py test accounts` both pass, and the add → view → remove flow works in a browser.

### Key Discoveries:

- Replacing the `/` placeholder collides with an existing assertion: `accounts/tests.py:91` asserts the home page contains `marek@example.com`. Keeping the signed-in email on the watchlist page (as `accounts/templates/accounts/home.html:7` does) keeps that test green with **no edits to `accounts/tests.py`**.
- `accounts/urls.py:15` and `accounts/views.py:39-41` must be retired, and the now-unused `login_required` import removed from `accounts/views.py:3`.
- Store symbols uppercase so a plain `UniqueConstraint(user, symbol)` and `Meta.ordering = ["symbol", "id"]` deliver case-insensitive dedupe and A→Z ordering without DB expressions — and so stored symbols match what the scan layer will look up.
- The delete flow must be POST-only, mirroring the repo's existing POST-only logout contract (`accounts/tests.py:141-144`) rather than a GET link.

## What We're NOT Doing

- No position **update** (FR-005) — parked; delete + re-add covers correction in v1.
- No ticker verification against the provider (`/symbol_search` or `/quote`) — format validation only, no API credits spent on add.
- No company-name auto-fetch, no per-row price/scan data, no formation detection — that is S-02/S-03.
- No soft-delete, undo, scan history, or recovery of removed rows — FR-006 specifies hard removal only.
- No pagination, search, or filtering — the list is small (a dozen-ish).
- No CI change: the test suite is run locally, not wired into `.github/workflows/ci.yml`.
- No new CSS framework or JS toolchain; no new stylesheet (reuse the existing `accounts/css/auth.css` via `base.html`).
- No admin registration, no custom user model, no auth changes.

## Implementation Approach

Create a small `watchlist` app that owns the model, views, form, templates, and tests, keeping domain code out of `accounts`. The model is a per-user `WatchlistItem`; the form normalizes and format-validates the symbol; one `index` view serves the list (GET) and handles adds (POST) on `/`; a POST-only `remove` view deletes a user-scoped row. Template reuse keeps the diff small: the list page extends the existing `base.html`, and the signed-in email stays visible so the F-01 login test needs no change.

## Critical Implementation Details

- **The `/` swap is a cross-app change.** Retiring `accounts/urls.py:15` and `accounts/views.py:39-41` and mounting `watchlist` at `/` must land together; a half-applied swap leaves two views racing for `/` or breaks the login redirect target. Keep `LOGIN_REDIRECT_URL = "/"` (`stock_guard/settings.py:72`) untouched so login/registration still land on the list.
- **The email must remain visible on `/`.** `accounts/tests.py:91` asserts it; render `{{ request.user.email }}` in the watchlist template so `accounts`' tests keep passing unmodified.
- **Symbol normalization parity.** The form must store `strip().upper()`, identical to the fetch service, or a stored entry and the later scan lookup diverge. Uppercase storage is also what makes the plain `(user, symbol)` uniqueness and A→Z ordering behave case-insensitively.
- **Duplicate adds can race.** `clean_symbol` catches the common case; wrap the save in `transaction.atomic()` and catch `IntegrityError` to re-render with a form error instead of a 500 (the F-01 pattern at `accounts/views.py:14-21`).
- **Delete is POST-only and user-scoped.** `@require_POST` yields 405 for GET, and `get_object_or_404(WatchlistItem, pk=pk, user=request.user)` yields 404 (not 403) for another user's row — never revealing that it exists.

## Phase 1: App scaffold + model + migration

### Overview

Create the `watchlist` app, register it, define the `WatchlistItem` model with its per-user uniqueness constraint and ordering, and commit the migration. No user-visible behavior yet.

### Changes Required:

#### 1. New `watchlist` app

**File**: `watchlist/` (app package: `__init__.py`, `apps.py`, `models.py`, `views.py`, `forms.py`, `urls.py`, `admin.py`, `tests.py`, `migrations/__init__.py`, plus `templates/` and `static/` dirs created in later phases)

**Intent**: Create a domain app that owns the watchlist so it does not live inside `accounts`, giving S-02/S-03 a clean model to import.

**Contract**: `watchlist.apps.WatchlistConfig` with `name = "watchlist"` and `default_auto_field = "django.db.models.BigAutoField"`, mirroring `accounts/apps.py:4-6`.

#### 2. Watchlist model

**File**: `watchlist/models.py`

**Intent**: Store one row per (user, ticker) on the user's private list, ordered A→Z, with a name that may be blank.

**Contract**: `WatchlistItem` with `user = ForeignKey(settings.AUTH_USER_MODEL, on_delete=CASCADE, related_name="watchlist_items")`; `symbol = CharField(max_length=16)` (matching `DailyCandle.symbol`); `name = CharField(max_length=100, blank=True)`; `created_at = DateTimeField(auto_now_add=True)`. `Meta.constraints` holds `UniqueConstraint(fields=["user", "symbol"], name="uniq_watchlist_item_user_symbol")`; `Meta.ordering = ["symbol", "id"]`. `__str__(self) -> str` returns the symbol (with the name in parentheses when present). Follow `DailyCandle` style (`marketdata/models.py:4-23`): implicit `BigAutoField` PK, no `verbose_name`, no extra index.

#### 3. Register the app

**File**: `stock_guard/settings.py`

**Intent**: Make Django discover the new app, its migrations, and its app-directory templates.

**Contract**: Append `"watchlist"` to `INSTALLED_APPS` after `"marketdata"` (`stock_guard/settings.py:47-56`). No other settings change (`APP_DIRS=True` already covers app-local templates).

#### 4. Initial migration

**File**: `watchlist/migrations/0001_initial.py`

**Intent**: Commit the generated schema so CI's migration-drift check passes.

**Contract**: Generated by `uv run python manage.py makemigrations watchlist`; creates the `watchlist_watchlistitem` table with the FK, fields, unique constraint, and ordering (`Meta.ordering` is not a DB object). Do not hand-edit.

### Success Criteria:

#### Automated Verification:

- Django system checks pass: `uv run python manage.py check`
- No migration drift remains: `uv run python manage.py makemigrations --check --dry-run`
- Migration applies cleanly: `uv run python manage.py migrate`

#### Manual Verification:

- `WatchlistItem` is importable in `uv run python manage.py shell`, and the app appears in `INSTALLED_APPS`.

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 2: Add & list surface

### Overview

Add the form, the `index` view (GET list + inline POST add), the list template, and the URL restructure that retires the `accounts` `/` placeholder. After this phase a user can add stocks and see their own list.

### Changes Required:

#### 1. Add form

**File**: `watchlist/forms.py`

**Intent**: Present a ticker plus an optional name, normalize the ticker, reject malformed and duplicate symbols with inline errors, and attach the row to the acting user.

**Contract**: `WatchlistItemForm(ModelForm)` over `WatchlistItem` with `Meta.fields = ("symbol", "name")`. `__init__(self, *args, user, **kwargs)` stores `self.user`, sets `name` optional, and autofocuses `symbol`. `clean_symbol` normalizes with `strip().upper()`, rejects non-matching formats and (user-scoped) duplicates, and returns the normalized value. `save()` sets `instance.user = self.user` before saving so the view can call `form.save()` like `register` does. Validation is non-obvious, so the allowed-shape pattern is pinned here:

```python
SYMBOL_PATTERN = re.compile(r"^[A-Z][A-Z0-9.\-]{0,15}$")
```

#### 2. Index view

**File**: `watchlist/views.py`

**Intent**: Serve the user's list and handle adds on the same URL, mirroring the `register` view's POST/GET shape and its `IntegrityError` fallback; error messages stay inline (the messages framework is unused in this repo).

**Contract**: `@login_required def index(request)`: on POST build `WatchlistItemForm(request.POST, user=request.user)`, and on valid input save inside `transaction.atomic()`; on `IntegrityError` call `form.add_error("symbol", ...)`; on success `redirect("watchlist")`. On GET build an unbound `WatchlistItemForm(user=request.user)`. Always render `watchlist/list.html` with `{"form": form, "items": request.user.watchlist_items.all()}` (ordering comes from `Meta.ordering`).

#### 3. List template

**File**: `watchlist/templates/watchlist/list.html`

**Intent**: One page showing the signed-in user, an inline add form, and their stocks A→Z, with an empty-state message when the list is empty.

**Contract**: Extends `base.html`; overrides `title` and `content`. Must render `{{ request.user.email }}` (keeps `accounts/tests.py:91` green). The add form is `<form method="post" action="{% url 'watchlist' %}">` with `{% csrf_token %}`, `{{ form.non_field_errors }}`, and `{{ form.as_p }}`. Each item renders its symbol and (when present) name. Reuses the existing `accounts/css/auth.css` via `base.html` — no new stylesheet.

#### 4. Watchlist URLs

**File**: `watchlist/urls.py`

**Intent**: Expose the list/add route and the future delete route under the root mount.

**Contract**: `path("", views.index, name="watchlist")` and `path("watchlist/<int:pk>/delete/", views.remove, name="watchlist_remove")` (the `remove` view arrives in Phase 3; the route may be added then to avoid a broken reference).

#### 5. Retire the `accounts` placeholder and mount the app

**File**: `stock_guard/urls.py`, `accounts/urls.py`, `accounts/views.py`, `accounts/templates/accounts/home.html`

**Intent**: Make `/` the watchlist surface and remove the throwaway placeholder, keeping the auth routes (`/login/`, `/logout/`, `/register/`) intact.

**Contract**: In `stock_guard/urls.py:27-31` add `path('', include('watchlist.urls'))` alongside the existing `include('accounts.urls')`. In `accounts/urls.py` remove the `path("", home, name="home")` route (`:15`) and drop `home` from the `views` import (`:5`). In `accounts/views.py` delete the `home` view (`:39-41`) and the now-unused `login_required` import (`:3`). Delete `accounts/templates/accounts/home.html`. Do not change `LOGIN_URL`/`LOGIN_REDIRECT_URL`/`LOGOUT_REDIRECT_URL` (`stock_guard/settings.py:71-73`).

### Success Criteria:

#### Automated Verification:

- Django system checks pass: `uv run python manage.py check`
- No migration drift remains: `uv run python manage.py makemigrations --check --dry-run`
- Static collection succeeds: `uv run python manage.py collectstatic --noinput`

#### Manual Verification:

- A logged-in user can add a stock (ticker + optional name) from `/` and it appears in the list.
- The list shows only the acting user's stocks, ordered A→Z, with the signed-in email visible.
- An invalid ticker format and a duplicate (any case) each show an inline form error, not a 500.
- Adding a stock with a blank name displays the ticker only.

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 3: Remove flow + test suite

### Overview

Add the POST-only, user-scoped remove view with its per-row form, and prove the whole slice with the `watchlist` test suite.

### Changes Required:

#### 1. Remove view

**File**: `watchlist/views.py`

**Intent**: Let a user hard-delete one of their own rows, refusing non-POST requests and never touching another user's row.

**Contract**: `@login_required @require_POST def remove(request, pk)` — look up with `get_object_or_404(WatchlistItem, pk=pk, user=request.user)` (404 for another user's row), `item.delete()`, then `redirect("watchlist")`. Decorator order matters: `login_required` outermost so an anonymous request redirects to login, while a logged-in GET yields 405 from `require_POST`. This mirrors the logout contract (`accounts/tests.py:141-144`).

#### 2. Per-row remove form

**File**: `watchlist/templates/watchlist/list.html`

**Intent**: Give each row a CSRF-protected button that posts to the remove route.

**Contract**: Per item, a `<form method="post" action="{% url 'watchlist_remove' item.pk %}">` containing `{% csrf_token %}` and a submit button (mirroring the logout form in `base.html:16-19`).

#### 3. Watchlist tests

**File**: `watchlist/tests.py`

**Intent**: Cover the primary capability and the privacy/edge contracts using the repo's existing test conventions.

**Contract**: `django.test.TestCase` classes named `<Feature>Tests` with `test_...Returns...When...` method names, hardcoded URL strings, and a module-level `PASSWORD` constant, matching `accounts/tests.py:1-151`. Cases: a mixed-case/whitespace symbol is stored uppercase for the acting user; a duplicate symbol (different case) is rejected with a form error and no second row; an invalid symbol format is rejected; an optional blank name saves and renders the ticker only; an anonymous `GET /` redirects to `/login/?next=/`; a user's list shows only their own rows and excludes another user's; the list is ordered A→Z; an authenticated `POST` to a row's delete URL removes it and redirects to `/`; `GET` on a delete URL returns 405; deleting another user's row returns 404 and leaves it intact.

### Success Criteria:

#### Automated Verification:

- Watchlist test suite passes: `uv run python manage.py test watchlist`
- Existing auth test suite still passes: `uv run python manage.py test accounts`
- Django system checks pass: `uv run python manage.py check`

#### Manual Verification:

- Clicking a row's Remove button takes that stock off the list and keeps the user signed in.
- Navigating directly to another user's row delete URL (or its GET form) does not remove their stock.

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Testing Strategy

### Unit Tests:

- Form: symbol normalization (`strip().upper()`), format rejection, user-scoped duplicate rejection, optional blank name, invalid/empty input.
- Model: `(user, symbol)` uniqueness; `Meta.ordering` yields A→Z; `__str__` output.
- View access: `@login_required` redirect on `/`; 405 for GET on the delete route; 404 for another user's row.

### Integration Tests:

- Add → view → remove through the Django test client: the added row appears only in the actor's list and is gone after removal.
- Two users (`alice`, `bob`) each see only their own rows; alice's delete URL for bob's row returns 404 without deleting it.

### Manual Testing Steps:

1. `uv run python manage.py migrate` (dev SQLite), then `uv run python manage.py runserver`.
2. Log in, add `aapl` and `msft` (name blank for one) from `/`, confirm they appear uppercase and A→Z with the ticker-only row for the blank name.
3. Add `AAPL` again and an invalid symbol like `12` — confirm inline errors, not a 500.
4. Log in as a second account and confirm its list is empty and does not contain the first user's rows.
5. Remove a stock via its row button and confirm it disappears; confirm `GET` on the delete URL is rejected.

## Performance Considerations

Not applicable — the slice is a handful of single-table queries per request over a dozen-row list, with no scan or external-API path. Ordering and uniqueness are served by the `(user, symbol)` constraint's index.

## Migration Notes

One new table (`watchlist_watchlistitem`) via a single committed migration, applied by the existing Railway `preDeployCommand` (`migrate --noinput`); there is no data backfill and no change to the `accounts`/`auth` tables. The local `db.sqlite3` gains the table on `migrate`. No new environment variables or settings beyond the `INSTALLED_APPS` entry.

## References

- Roadmap slice S-01: `context/foundation/roadmap.md:104-114`; symbols decision: `context/foundation/roadmap.md:168-169`
- PRD FR-003/FR-004/FR-006 and privacy NFR: `context/foundation/prd.md:71-80`, `context/foundation/prd.md:45`, `context/foundation/prd.md:97`
- Symbol format decision: `context/changes/price-data-fetch-boundary/research.md:148-153`; deferred validation: `context/changes/price-data-fetch-boundary/plan.md:47`
- Placeholder to retire: `context/changes/account-auth-scaffold/plan-brief.md:61`
- Patterns to mirror: `accounts/views.py:11-27` (atomic + IntegrityError), `accounts/forms.py:22-29` (clean_<field>), `accounts/tests.py:7-151`, `marketdata/models.py:4-23`
- CI gate: `.github/workflows/ci.yml`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: App scaffold + model + migration

#### Automated

- [x] 1.1 Django system checks pass
- [x] 1.2 No migration drift remains
- [x] 1.3 Migration applies cleanly

#### Manual

- [x] 1.4 WatchlistItem is importable in the shell and the app is registered

### Phase 2: Add & list surface

#### Automated

- [ ] 2.1 Django system checks pass
- [ ] 2.2 No migration drift remains
- [ ] 2.3 Static collection succeeds

#### Manual

- [ ] 2.4 A logged-in user can add a stock from / and it appears in the list
- [ ] 2.5 The list shows only the acting user's stocks, ordered A→Z, with the email visible
- [ ] 2.6 Invalid and duplicate tickers show inline form errors, not a 500
- [ ] 2.7 A blank name displays the ticker only

### Phase 3: Remove flow + test suite

#### Automated

- [ ] 3.1 Watchlist test suite passes
- [ ] 3.2 Existing auth test suite still passes
- [ ] 3.3 Django system checks pass

#### Manual

- [ ] 3.4 Clicking a row's Remove button takes the stock off the list
- [ ] 3.5 Another user's row delete URL does not remove their stock
