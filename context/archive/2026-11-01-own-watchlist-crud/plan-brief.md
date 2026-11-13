# Own Watchlist CRUD — Plan Brief

> Full plan: `context/changes/own-watchlist-crud/plan.md`
> Research: upstream symbol decision in `context/changes/price-data-fetch-boundary/research.md:148-153`

## What & Why

Build roadmap slice **S-01**: a logged-in user can add a stock (ticker + optional name) to their own private watchlist, see it listed A→Z, and hard-remove it. It is the list surface that the later detection/scan slices (S-02, S-03) render graded flags on, so it deliberately ships before any formation math. PRD refs FR-003, FR-004, FR-006, US-01.

## Starting Point

Django 6.1.1 project with two apps: `accounts` (email-as-username auth, no models) and `marketdata` (the only model, `DailyCandle`). There is no watchlist app, model, view, or template. `/` is currently a throwaway `@login_required` placeholder (`accounts/urls.py:15`, `accounts/views.py:39-41`) that F-01 documented as meant to be replaced by this slice. The bare-uppercase ticker format is already decided upstream; add-time validation was explicitly deferred to S-01.

## Desired End State

A logged-in user opens `/` and sees an inline add form plus their own stocks A→Z, each with a Remove button. `aapl` is stored as `AAPL`; a duplicate (any case) or a malformed symbol shows an inline error; a blank name renders the ticker only; an anonymous visitor to `/` is redirected to `/login/?next=/`; no user can see or delete another user's row.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| App/model structure | New `watchlist` app, model `WatchlistItem` | Keeps domain code out of `accounts` and gives S-02/S-03 a clean import target. | Plan |
| Ticker validation | Format regex only (`^[A-Z][A-Z0-9.\-]{0,15}$`), no API call | Zero API credits, offline-testable, matches the upstream bare-uppercase decision. | Research + Plan |
| Duplicate handling | DB `UniqueConstraint(user, symbol)`, reject with form error | Mirrors the F-01 duplicate pattern; case-normalization makes `aapl`/`AAPL` collide. | Plan |
| Name field | Optional free text; blank renders ticker only | Honors FR-003's "e.g., ticker + name" with no provider call. | Plan |
| Delete method | POST-only per-row form with CSRF | Matches the repo's POST-only logout pattern; blocks prefetch/cross-site GET deletes. | Plan |
| List surface / URLs | `/` renders list + inline add; delete at `/watchlist/<pk>/delete/` | Matches FR-007's "list view opened" trigger and F-01's intent to replace the `/` placeholder. | Plan |
| List ordering | Symbol A→Z, `id` tiebreak | Answers FR-004's rejection of a "bare unsorted view"; scannable and stable. | Plan |
| Cross-user access | User-scoped lookup → 404 | Never reveals another user's row exists; satisfies the PRD privacy NFR. | Plan |
| CI tests | Leave `.github/workflows/ci.yml` unchanged; run tests locally | Keeps the diff focused, consistent with F-01's "no CI wiring" stance. | Plan |
| Symbol width | `CharField(max_length=16)` | Matches `DailyCandle.symbol` so a watchlist entry maps to a fetchable symbol. | Research |

## Scope

**In scope:** `watchlist` app + `WatchlistItem` model + migration; add form with symbol normalization/format validation; list view (GET + inline POST add) on `/`; POST-only user-scoped remove; list/empty-state UI extending `base.html`; retiring the `accounts` `/` placeholder; `watchlist/tests.py`.

**Out of scope:** position update (FR-005, parked); provider ticker verification; company-name fetch; detection/scan data (S-02/S-03); soft-delete/undo/scan history (FR-006); pagination/search/filtering; CI changes; new CSS framework/JS; admin registration; auth changes.

## Architecture / Approach

A small `watchlist` app owns the model, form, views, templates, and tests. `WatchlistItem` FKs to `settings.AUTH_USER_MODEL` with a per-user unique symbol and A→Z ordering. One `index` view serves the list (GET) and handles adds (POST) on `/`, reusing the `register` view's `transaction.atomic()` + `IntegrityError` form-error shape; a POST-only, user-scoped `remove` view deletes a row and redirects back. The list template extends the existing `base.html` and keeps the signed-in email visible, so `accounts`' tests pass unmodified.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. App scaffold + model + migration | `watchlist` app, `WatchlistItem`, committed migration, `INSTALLED_APPS` entry | Migration must be committed or CI's drift check fails. |
| 2. Add & list surface | Form, `index` view, list template, URL restructure replacing `/` | The cross-app `/` swap must land atomically with the placeholder retirement. |
| 3. Remove flow + test suite | POST-only scoped delete, per-row form, `watchlist` tests | Cross-user delete must 404 without leaking row existence. |

**Prerequisites:** F-01 (account auth scaffold) is implemented and `extends`-ready; a migrated dev DB.
**Estimated effort:** ~2–3 sessions across three phases; small surface, no external dependencies.

## Open Risks & Assumptions

- Symbol validation is format-only, so a well-formed but wrong ticker (`APLE` for `AAPL`) is accepted and only surfaces later as `symbol_not_found` during the scan — an accepted MVP gap the roadmap flags.
- The plain `(user, symbol)` constraint is case-insensitive only because the form uppercases on write; a direct ORM write bypassing the form could store lowercase (mirrors F-01's known normalization debt).
- Retiring the `/` placeholder is a cross-app edit; if applied partially, `/` could 404 or conflict with the auth routes.
- `accounts/tests.py:91` asserts the home page shows the user's email; the plan keeps it visible on the watchlist page rather than editing that test.

## Success Criteria (Summary)

- A logged-in user can add a stock, see their own list A→Z, and remove a stock — the complete S-01 flow.
- Invalid and duplicate tickers are rejected inline; a user never sees or deletes another user's rows.
- `uv run python manage.py test watchlist` and `uv run python manage.py test accounts` both pass.
