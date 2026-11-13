<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Price Data Fetch Boundary Implementation Plan

- **Plan**: context/changes/price-data-fetch-boundary/plan.md
- **Scope**: Full plan
- **Reviewed phases**: 1, 2, 3, 4
- **Date**: 2026-10-18
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 3 warnings, 6 observations
- **Triage**: complete — 9 FIXED (2026-10-18)

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | PASS |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | WARNING |
| Success Criteria | PASS |

## Findings

### F1 — HTTP status errors with a non-JSON body lose their reason

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: marketdata/providers/twelvedata.py:46-47
- **Detail**: `_decode_payload(response)` runs before `_raise_for_error(payload, response.status_code)`. When the provider or an edge/CDN returns 429/500/404 with an HTML (non-JSON) body, `response.json()` raises `ValueError` → `ProviderError("invalid_response", ...)` at `:57`, so the status-code reason (`rate_limited`, `symbol_not_found`, `provider_error`) is lost. The plan maps a failure by code/status; this path defeats it. The only status-failure test (`tests.py:160-166`) uses a valid-JSON body, so it does not cover this.
- **Fix**: Check `response.status_code >= 400` before parsing the body and raise the mapped reason from the status code; only fall through to JSON decode for 2xx responses.
  - Strength: Restores the plan's own mapping contract and is covered by one new test; small, local change.
  - Tradeoff: A 4xx with a JSON `code` would then use the status code rather than the body code — acceptable, since they agree in practice.
  - Confidence: HIGH — the mapping helper `_reason_for_code` already exists.
  - Blind spot: Twelve Data's real 429 body format was not re-verified here.
- **Decision**: FIXED — `_decode_payload` maps the HTTP status on JSON-decode failure; added `test_fetchRaisesMappedReasonWhenHttpStatusFailsWithNonJsonBody`.

### F2 — `--bars N` drives the destructive prune window

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: marketdata/services.py:118-125, marketdata/management/commands/fetch_candles.py:14,23
- **Detail**: `_store` deletes every row older than the `lookback`-th newest date, and the command forwards `--bars N` straight through as `lookback`. A debugging `fetch_candles AAPL --bars 50` permanently destroys ~450 cached bars of the default 500 window. This is explicitly accepted by the plan (`plan.md:79`, `:261`), so it is by-design, not drift — recorded so the tradeoff is visible.
- **Fix**: Decouple the prune window from the request window (prune to `max(lookback, settings.MARKET_DATA_LOOKBACK_BARS)`), or gate destructive pruning behind an explicit flag.
- **Decision**: FIXED — prune window is now `max(bars, MARKET_DATA_LOOKBACK_BARS)`. **Plan deviation**: this changes the plan's documented `--bars` semantics (`plan.md:79,:261` said `bars=200` prunes to 200); `test_fetchPrunesToCustomLookback…` was replaced by `test_fetchKeepsConfiguredCacheWindowWhenBarsOverrideIsSmaller`.

### F3 — zero/negative `bars` raises an unhandled `ValueError`

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: marketdata/services.py:118-125
- **Detail**: With `bars=0` (e.g. `manage.py fetch_candles AAPL --bars 0`), `count() <= 0` is false for existing rows and `values_list(...)[lookback - 1]` slices `[-1]`/negative index, which Django rejects (`ValueError: Negative indexing is not supported`). This is not a `ProviderError`, so it escapes `fetch_daily_candles`, breaking the "never raises" contract. Flagged as an open uncertainty during Phase 3; the plan defines no lower bound.
- **Fix**: Validate `bars >= 1` in `fetch_daily_candles` and return `PriceUnavailable(reason="invalid_symbol")` (or add `type=`/`choices` on the `--bars` argparse argument).
- **Decision**: FIXED — `bars < 1` returns `PriceUnavailable(reason="invalid_symbol")` before any provider call; added `test_fetchReturnsInvalidSymbolWithoutProviderCallWhenBarsIsNotPositive`.

### F4 — only `ProviderError` is caught at the service boundary

- **Severity**: OBSERVATION
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: marketdata/services.py:63-71, 73-75
- **Detail**: The service catches only `ProviderError`. A non-`HTTPError` from httpx (e.g. `httpx.InvalidURL`) or any DB error from `_store`/`_load` propagates, so `fetch_daily_candles` is not strictly total for every failure the plan implies ("never raises for provider, configuration or data problems").
- **Fix**: Broadly guard the fetch/persist boundary and convert unexpected failures to a typed `PriceUnavailable`/stale result (mirroring `accounts/views.py:15-21`'s catch-at-the-boundary pattern).
- **Decision**: FIXED — unexpected fetch and persistence exceptions are converted to typed `provider_error` results; added `test_fetchReturnsTypedResultWhenProviderRaisesUnexpectedError` and `test_fetchReturnsTypedResultWhenPersistenceFails`.

### F5 — concurrent fetch/upsert is unguarded (TOCTOU)

- **Severity**: OBSERVATION
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: marketdata/services.py:48-75
- **Detail**: The read of `max(fetched_at)`, the HTTP fetch and the upsert are not locked. Two callers (multi-worker gunicorn, or a command racing a request) both see a stale cache, both spend a provider credit, and concurrent `bulk_create(update_conflicts=True)` + `delete` can raise `IntegrityError`/deadlock on Postgres (uncaught).
- **Fix**: Accept and document for the single-worker MVP; for S-03 consider `select_for_update` on a per-symbol cache row or catch `IntegrityError` and re-read.
- **Decision**: FIXED (documented) — `fetch_daily_candles` docstring records the single-worker, no-locking assumption.

### F6 — freshness is blind to market holidays and half-days

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: marketdata/services.py:147-154
- **Detail**: `_last_completed_close` skips Sat/Sun only. On a holiday it returns that weekday's 16:00 as "last completed close" though no session occurred (one wasted refetch); on a half-day it treats the session as incomplete until 16:00 ET. This matches the plan's acknowledged "calendar-light" rule (`plan.md:68`, `:76`), so it is by-design.
- **Fix**: Document the exact failure mode, or add a market-holiday calendar when S-02 relies on freshness for correctness.
- **Decision**: FIXED (documented) — `_last_completed_close` docstring describes the weekday-only rollback and its holiday/half-day behaviour.

### F7 — untrusted provider message surfaced downward unescaped

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: marketdata/providers/twelvedata.py:70 → marketdata/services.py:83-88 → marketdata/management/commands/fetch_candles.py:32
- **Detail**: `payload["message"]` (untrusted external data) is copied into `ProviderError.message`, returned as `PriceSeries.message`, and written to stdout. Harmless today, but S-03 will render per-row reasons in a template — if this string is ever rendered as HTML it becomes a stored/reflected XSS vector.
- **Fix**: Treat `reason` as the display contract and keep `message` for logs only, or escape at render time.
- **Decision**: FIXED — `fetch_candles` no longer writes the provider `message` to stdout (reason-only line); added `test_fetchCandlesCommandOmitsProviderMessageWhenUnavailable`.

### F8 — all-or-nothing candle parsing

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: marketdata/providers/twelvedata.py:83-91
- **Detail**: A single malformed row field raises `invalid_response` and discards all otherwise-valid rows, turning the symbol fully stale/unavailable rather than degrading.
- **Fix**: Skip/flag individual bad rows, or tolerate a bounded number of parse failures.
- **Decision**: FIXED — malformed rows are skipped; the symbol only fails when no row parses; added `test_fetchSkipsMalformedRowsWhenOtherRowsAreValid`.

### F9 — intra-app imports differ from `accounts` convention

- **Severity**: OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: marketdata/services.py:11-13, marketdata/providers/twelvedata.py:7, marketdata/management/commands/fetch_candles.py:5-6
- **Detail**: `accounts` uses app-relative imports within the app (`accounts/views.py:8`, `accounts/urls.py:4-5`); `marketdata` uses absolute intra-app imports. Not harmful — one consistent style within the new app — but a substantive convention divergence.
- **Fix**: Switch intra-app imports to relative, or leave as-is (absolute is unambiguous and the new app is internally consistent).
- **Decision**: FIXED — intra-app imports in `services.py`, `providers/twelvedata.py` and `commands/fetch_candles.py` switched to relative.

## Triage summary (2026-10-18)

| Finding | Decision |
|---------|----------|
| F1 | FIXED — status-code mapping before JSON decode |
| F2 | FIXED — prune window floored at the configured default (**plan deviation**) |
| F3 | FIXED — `bars < 1` → `invalid_symbol` |
| F4 | FIXED — boundary converts unexpected fetch/persistence exceptions to typed results |
| F5 | FIXED (documented) — single-worker assumption in the `fetch_daily_candles` docstring |
| F6 | FIXED (documented) — holiday/half-day behaviour in the `_last_completed_close` docstring |
| F7 | FIXED — provider `message` no longer written to stdout |
| F8 | FIXED — malformed rows skipped instead of failing the whole symbol |
| F9 | FIXED — intra-app imports made relative |

Post-fix verification: `uv run python manage.py test marketdata` → 32 tests OK; `manage.py check` clean; `makemigrations --check` clean.

### Plan deviations to fold back

1. **F2** changes the `--bars` prune semantics the plan documented at `plan.md:79` and `:261` (a smaller `--bars` no longer shrinks the cache).
2. **F8** softens the plan's "structurally invalid values → `invalid_response`" rule to per-row skipping (`plan.md:167`).

Both are deliberate, triaged decisions — the plan text should be reconciled before `/10x-archive`.
