# End-to-End Flow Test Implementation Plan

## Overview

Deliver roadmap slice **S-04** (`end-to-end-flow-test`): the PRD's single explicit verification requirement — *"at least one test verifying behavior from the user's perspective — the key flow (login → add a stock → scan → flagged list)"* (`shape-notes.md:73`). Add one Django `TestCase` that drives that whole flow through the real HTTP front door and the real detection engine, stubbing only the outbound price-data HTTP call, and asserts the flagged list renders. No production code changes: the flow already exists and is wired end-to-end.

## Current State Analysis

- **The flow exists and is wired.** `POST /login/` (`accounts/urls.py:9-11`, Django `LoginView` + `EmailAuthenticationForm`) authenticates and redirects to `LOGIN_REDIRECT_URL='/'` (`stock_guard/settings.py:74`). `POST /` adds a `WatchlistItem` (`watchlist/views.py:13-24`, `WatchlistItemForm`), then PRG-redirects to `/`. `GET /` builds `items = request.user.watchlist_items.all()` and calls `rows = scan_watchlist(items)` inline (`watchlist/views.py:27-28`). The template renders a graded badge only when a formation is present (`watchlist/templates/watchlist/list.html:21-23`).
- **The scan orchestration is `watchlist/services.py`.** `scan_watchlist(items, *, max_workers, per_row_timeout, budget_seconds)` runs one `ThreadPoolExecutor` task per item; `_build_row` (`watchlist/services.py:79-103`) calls `fetch_daily_candles(item.symbol, timeout=...)` then `score_formation(result)`, mapping a `PriceSeries` → `Row(score=score_formation(...), stale=..., message=...)` and a `PriceUnavailable` → `Row(score=None, message=...)`.
- **The fetch boundary is `marketdata/services.py:fetch_daily_candles`** (never raises; returns `PriceSeries | PriceUnavailable`). On a cold symbol it checks the `DailyCandle` cache, then calls `twelvedata.fetch_daily(normalized, bars=..., timeout=..., api_key=...)` (`marketdata/services.py:82-91`), stores via upsert (`_store`, `:124-157`) and reloads via `_load` (`:160-176`). It needs `settings.TWELVE_DATA_API_KEY` non-empty or it short-circuits to `PriceUnavailable(reason="not_configured")` (`:77-79`).
- **The detection engine is `detection/services.py:score_formation`** — pure, no I/O. It returns `_NO_SIGNAL` for `< MIN_BARS` (60, `:24`) or no ATR; otherwise it runs `score_double_top`/`score_head_shoulders` and grades via `_grade` (`>=0.70` high, `>=0.45` medium, else low, `:121-126`).
- **The gap.** No test chains the steps. `accounts/tests.py:82-91` tests login-via-POST but stops at home render; `watchlist/tests.py` tests add/scan/render but authenticates with `self.client.login(...)` (`:24,93,107,138,147,155,171,264`) and stubs both `fetch_daily_candles` and `score_formation`. The PRD's named flow is never exercised as one journey.
- **Reusable fixtures exist but are module-local.** `detection/tests.py:129-160` defines `_series(legs, ...)` (builds `Candle` tuples from legs) and `FORMING_DOUBLE_TOP_LEGS` (`:163-169`) — a 65-bar planted double top whose result is `pattern="double_top"`, `stage="forming"`, `grade in ("medium","high")` (`detection/tests.py:246-253`). `_candles`/`_series` are not importable cross-module in this repo's convention (no shared `tests/` package), so the E2E test needs its own candle builder.
- **Test conventions.** Django `TestCase` only; `manage.py test` runner; mocking via `unittest.mock.patch`; no pytest, no factories, no conftest, no `override_settings` usage today. CI runs `manage.py test` (`ci.yml:29`). `MARKET_DATA_LOOKBACK_BARS=500` (`settings.py:195`) comfortably covers the 65-bar fixture.

## Desired End State

One green `TestCase` in `watchlist/tests.py` proves that a visitor can register/log in, add a stock, and — on the resulting list view — see that stock rendered with a graded bearish-formation flag produced by the real detection engine. A reviewer reading the test sees the full chain (login → add → fetch → detect → render) with exactly one seam stubbed (the outbound HTTP call), and CI keeps it green.

Verification: `uv run python manage.py test` is green including the new class; `manage.py check`, `makemigrations --check --dry-run`, and `collectstatic --noinput` all pass.

### Key Discoveries:

- **The one stub seam.** Stub `marketdata.services.twelvedata.fetch_daily` (the module already imported at `marketdata/services.py:13`), not `fetch_daily_candles`. This keeps the *real* fetch-boundary logic under test — normalization, cache-miss path, upsert into `DailyCandle`, `_load` ordering — and lets the real `score_formation` run on the stored series. Stubbing `fetch_daily_candles` (the existing `watchlist/tests.py` pattern) would skip the whole market-data boundary and the real engine.
- **`TWELVE_DATA_API_KEY` must be non-empty** during the test, else `fetch_daily_candles` returns `not_configured` before reaching the stub (`marketdata/services.py:77-79`). Use `@override_settings(TWELVE_DATA_API_KEY="test-key")` (first use of `override_settings` in the repo — still standard Django).
- **Fixture must be ≥ 60 bars.** `score_formation` needs `MIN_BARS = 60`; the canonical `FORMING_DOUBLE_TOP_LEGS` series is 65 bars (`detection/tests.py:163-169`) and grades medium/high — reuse the same leg shape.
- **The stub must return ascending `Candle`s** with `date` values in the past; `_store` upserts on `(symbol, date)` and `_load` orders by `date` (`marketdata/services.py:143-148,160-176`). A fresh test DB has an empty `DailyCandle` table, so the freshness short-circuit at `:69-75` is not hit.
- **Assert on rendered HTML, not context.** The badge is a template artifact; assert `response.content` contains `badge` and the `Double top` label (per `list.html:21-23`). Do not hard-code a grade — the engine's grade for the fixture is `medium`/`high` depending on thresholds.
- **Login must go through the view.** Use `POST /login/` with `{"username": email, "password": ...}` (username == email, `accounts/tests.py:82-91`) rather than `self.client.login(...)`, so the login step of the named flow is genuinely exercised.

## What We're NOT Doing

- No production code changes — no view, service, model, template, settings, or migration edits. The flow under test already exists (S-01/S-02/S-03).
- No new app, no new top-level test module, no `tests/` package, no pytest/conftest/factories, no new dev dependency.
- No other test classes added — existing `accounts`/`watchlist`/`detection`/`marketdata` suites are unchanged.
- No degradation-guarantee E2E case (rate-limited / stale / still-scanning through the login flow) — those stay covered by `ScanWatchlistTests` (`watchlist/tests.py:262-388`). The single new test asserts the happy path only.
- No privacy assertion beyond what the journey implies (the "only own rows" guardrail is already covered by `WatchlistListTests` and `AccessControlTests`).
- No browser-level/`LiveServerTestCase` test and no JS.
- No CI workflow change — `manage.py test` already runs the new class.

## Implementation Approach

One additive phase that writes the test, then a verification phase that runs the suite and CI-parity checks. The test mirrors the real journey:

```
POST /register/  → creates the account (email==username)
POST /login/     → LoginView authenticates → 302 to /
POST /           → WatchlistItemForm saves AAPL → 302 to /
GET  /           → index → scan_watchlist → _build_row
                     └─ fetch_daily_candles  ── stubbed seam ──▶ twelvedata.fetch_daily (returns planted Candles)
                        ├─ _store / _load  (real, into DailyCandle)
                        └─ score_formation (real engine) → FormationScore(pattern="double_top", grade∈{medium,high})
                   → list.html renders  <span class="badge grade-…">Double top · … · …</span>
assert 200 + row symbol present + "badge" + "Double top"
```

Reuse the leg shape from `detection/tests.py:163-169` (a 65-bar planted forming double top) via a small local `_double_top_candles()` builder returning `Candle` objects; stub `fetch_daily` to return it.

## Critical Implementation Details

- **Stub target.** Patch `marketdata.services.twelvedata.fetch_daily` (string path `"marketdata.services.twelvedata.fetch_daily"`). It is called as `twelvedata.fetch_daily(...)` in the service (`marketdata/services.py:82`), so patching the attribute on the imported module reference is what takes effect.
- **Delete any pre-existing cached rows is unnecessary** in a fresh `TestCase` (transaction-rolled-back DB), but be aware that if the stub returns dates that make the series "fresh", `fetch_daily_candles` would serve from cache on a second `GET`. The assertion runs on the first `GET` after add, so this does not bite.
- **Watch the response status, not the scan's internal state.** A row could theoretically degrade to a message under the ~5 s default budget, but with a single instant stub the task completes well within budget; a flaky "still scanning" is not expected. If it ever occurs, it indicates a real regression, not test flakiness.

## Phase 1: End-to-end flow test

### Overview

Add an `EndToEndFlowTests` class to `watchlist/tests.py` that walks register → login → add → scan → flagged render with only the outbound HTTP fetch stubbed and the real detection engine running.

### Changes Required:

#### 1. Reuse top-of-file imports

**File**: `watchlist/tests.py`

**Intent**: The new class needs a `Candle` type for the fixture, `date`/`timedelta`/`Decimal` for building candles, and `override_settings`. Add only what is missing rather than duplicating imports.

**Contract**: `patch` and `FormationScore`/`PriceSeries` are already imported (`watchlist/tests.py:1-12`). Add `from datetime import date, timedelta`, `from decimal import Decimal`, `from django.test import TestCase, override_settings`, and `from marketdata.providers import Candle`. Keep existing imports untouched.

#### 2. `EndToEndFlowTests`

**File**: `watchlist/tests.py`

**Intent**: Prove the PRD's named flow (`login → add a stock → scan → flagged list`) as one journey through the real views and the real detection engine, so the primary capability is demonstrably reachable.

**Contract**: Add a `TestCase` subclass (place it after `ScanWatchlistTests`) with:
- a module-level or class helper building a 65-bar planted forming-double-top candle tuple from the same leg shape as `FORMING_DOUBLE_TOP_LEGS` (10× −0.4, 20× +1.0, 20× −0.6, 20× +0.6, 5× 0.0 — `detection/tests.py:163-169`), returning ascending `Candle(date=..., open/high/low/close=Decimal, volume=None)` with `spread=0.5`;
- a `setUp` that creates the account and logs in **through the login view** (`self.client.post("/login/", {"username": email, "password": PASSWORD})`);
- one test, `test_keyFlowReturnsFlaggedRowWhenUserLogsInAddsStockAndListIsScanned`, decorated `@override_settings(TWELVE_DATA_API_KEY="test-key")` that:
  1. `POST /` with `{"symbol": "AAPL", "name": ""}` and asserts the redirect to `/`;
  2. patches `"marketdata.services.twelvedata.fetch_daily"` to return the planted candle tuple, then `GET /`;
  3. asserts `200`, the response contains `AAPL`, a `badge`, and `Double top`.
- Follow the repo naming convention `test_...Returns...When...`. Do not assert an exact grade.

### Success Criteria:

#### Automated Verification:

- The new class passes in isolation: `uv run python manage.py test watchlist.tests.EndToEndFlowTests`
- The full watchlist suite passes: `uv run python manage.py test watchlist`
- Django system checks pass: `uv run python manage.py check`

#### Manual Verification:

- Reading the test top-to-bottom, the journey (register/login → add → scan → flagged) is legible and the single stub seam is obvious; the asserted badge traces to the real engine's output for the planted series.

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 2: Full-suite verification

### Overview

Confirm the new test is green within the whole suite and that nothing regressed, running the same gates as CI.

### Changes Required:

#### 1. Verification & CI-parity pass

**File**: (no file change — commands only)

**Intent**: Prove the suite is green end to end and the repo still passes every CI gate.

**Contract**: run the commands a developer/agent can execute:
`uv run python manage.py test`, `uv run python manage.py check`,
`uv run python manage.py makemigrations --check --dry-run`,
`uv run python manage.py collectstatic --noinput`.

### Success Criteria:

#### Automated Verification:

- Full test suite passes: `uv run python manage.py test`
- Django system checks pass: `uv run python manage.py check`
- No migration drift remains: `uv run python manage.py makemigrations --check --dry-run`
- Static collection still succeeds: `uv run python manage.py collectstatic --noinput`

#### Manual Verification:

- A code reviewer confirms the new test is the only change to the repo (no production files touched) and that it asserts the flagged-list outcome from the user's perspective.

---

## Testing Strategy

### Unit Tests:

- None added. The slice is a verification slice; detection/fetch/scan unit coverage already exists (`detection/tests.py`, `marketdata/tests.py`, `watchlist/tests.py:262-388`).

### Integration Tests:

- The one new `EndToEndFlowTests` case: register → login (view) → add stock (view) → list view scan with a stubbed provider response → assert a graded `Double top` badge renders on the added row.

### Manual Testing Steps:

1. `uv lock && uv sync`, then `uv run python manage.py test`.
2. Open `watchlist/tests.py` and read the new class; confirm each step maps to a real view/route and the lone patch target is `marketdata.services.twelvedata.fetch_daily`.
3. Optionally, temporarily tighten the assertion to a specific grade and observe the engine's chosen grade for the fixture, then revert to the label-only assertion.

## Performance Considerations

- None material: the test does no network I/O (the provider call is stubbed), scoring one 65-bar series is milliseconds, and the single-row scan finishes well inside the ~5 s budget.

## Migration Notes

- No schema change and no migration: no model is added or altered, so `makemigrations --check --dry-run` stays clean.
- No new runtime or dev dependency; `uv.lock` is unchanged.
- No deploy/runtime change. Rolling back = delete the `EndToEndFlowTests` class and the added imports.

## References

- Roadmap slice S-04: `context/foundation/roadmap.md:142-152`; prerequisite S-03: `:129-140`
- PRD verification requirement: `context/foundation/shape-notes.md:73`; Primary success criterion `context/foundation/prd.md:36`; US-01 `:50-60`
- Flow code: login `accounts/urls.py:8-12`, `accounts/forms.py:41-47`; index/add `watchlist/views.py:11-33`; form `watchlist/forms.py:11-40`; scan `watchlist/services.py:30-103`; fetch boundary `marketdata/services.py:40-176`; engine `detection/services.py:61-126`; template `watchlist/templates/watchlist/list.html:18-31`
- Reusable fixture shape: `detection/tests.py:129-169,245-253`; existing mock pattern `watchlist/tests.py:173-191`
- Settings: `stock_guard/settings.py:194-203`; CI: `.github/workflows/ci.yml:28-29`
- Prior slice plan (context): `context/archive/2026-11-13-scan-on-login-flagged-list/plan.md`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: End-to-end flow test

#### Automated

- [x] 1.1 The new class passes in isolation: `uv run python manage.py test watchlist.tests.EndToEndFlowTests` — b105303
- [x] 1.2 The full watchlist suite passes: `uv run python manage.py test watchlist` — b105303
- [x] 1.3 Django system checks pass: `uv run python manage.py check` — b105303

#### Manual

- [x] 1.4 The journey reads legibly and the asserted badge traces to the real engine's output for the planted series — 0845469

### Phase 2: Full-suite verification

#### Automated

- [x] 2.1 Full test suite passes: `uv run python manage.py test` — 0845469
- [x] 2.2 Django system checks pass: `uv run python manage.py check` — 0845469
- [x] 2.3 No migration drift remains: `uv run python manage.py makemigrations --check --dry-run` — 0845469
- [x] 2.4 Static collection still succeeds: `uv run python manage.py collectstatic --noinput` — 0845469

#### Manual

- [x] 2.5 Reviewer confirms the new test is the only change and asserts the flagged-list outcome from the user's perspective — 0845469
