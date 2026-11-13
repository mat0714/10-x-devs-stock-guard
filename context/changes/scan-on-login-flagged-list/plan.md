# Scan on Login Flagged List Implementation Plan

## Overview

Deliver roadmap slice **S-03** (`scan-on-login-flagged-list`): keep the watchlist auto-scan on every list-page open (login already redirects to `/`), but replace the current sequential per-row scan in `watchlist.index` with a **bounded-parallel orchestration** that resolves the whole list within a **~5 s total / ~3 s per row** budget and degrades per row. Also bound the S-02 follow-up **F1** head-and-shoulders enumeration so CPU scoring no longer consumes seconds per symbol. The PRD's single end-to-end flow test stays with **S-04**.

## Current State Analysis

- `watchlist.index` (`watchlist/views.py:51-73`) builds `items = request.user.watchlist_items.all()`, then `rows = [_build_row(item) for item in items]` — a **sequential** loop. `_build_row` (`watchlist/views.py:26-48`) calls `fetch_daily_candles(item.symbol)` then `score_formation(result)`, isolates any exception into `Row(item, None, message="analysis failed")`, and maps `PriceUnavailable` to a row message.
- The template already renders everything S-03 needs: the grade badge, the `(stale)` marker and a muted per-row `message` (`watchlist/templates/watchlist/list.html:16-35`). A row that does not finish simply needs a message — no template structure change is required.
- `fetch_daily_candles(symbol, *, bars=None)` (`marketdata/services.py:40-94`) never raises; it takes its HTTP timeout only from `settings.MARKET_DATA_HTTP_TIMEOUT` (default **10 s**, `stock_guard/settings.py:196`). It caches a rolling per-symbol window and serves it DB-only when `max(fetched_at) >= last completed NY close` (`marketdata/services.py:57-66`); provider failures with cached rows return `status="stale"`, otherwise `PriceUnavailable(reason=...)`.
- The service docstring states a **single-worker assumption**: the freshness read, provider call and upsert are not locked, so concurrent callers for the *same* symbol may both hit the provider (`marketdata/services.py:43-45`). A parallel scan relaxes this assumption for *different* symbols within one request.
- Runtime is a **single default gunicorn sync worker** (`Dockerfile:27`, no `--workers`/`--threads`); there is **no JS, no HTMX, no JSON endpoint, no `CACHES`/Redis and no background runner** (verified across the repo). Dev DB is SQLite, prod is Postgres (`stock_guard/settings.py:101-115`).
- Twelve Data Basic is **8 credits/min, 800/day, 1 credit per symbol** (`context/archive/2026-10-18-price-data-fetch-boundary/plan.md:23,308`): a **cold 12-symbol scan spends 12 credits, over the 8/min limit**, so some rows must degrade to `rate_limited` regardless of orchestration.
- **F1** (`context/archive/2026-11-08-formation-detection-service/follow-ups/review-fixes.md:5-13`): `score_head_shoulders` enumerates five nested pivot levels; on a noisy 500-bar walk (119 pivots) ~951k candidates are scored at ~2.9 s/symbol. An earlier `bisect`-slice attempt gave **1.0x** speedup and was reverted.
- Tests: `watchlist/tests.py` patches **`watchlist.views.fetch_daily_candles`** and **`watchlist.views.score_formation`** (`:22,80,126,171,...`) and asserts on `response.context["items"]` (`:97-99`). CI runs `manage.py test` (`.github/workflows/ci.yml:28-29`).

## Desired End State

A logged-in user opening `/` (which login already redirects to, `stock_guard/settings.py:75`) has the whole list scanned in a bounded-parallel pass and sees the page within roughly the scan budget: rows with a formation show their graded badge, cached/broken rows show `(stale)` or a per-row message, and rows that did not resolve in time or hit the credit limit show a clear per-row message — never a 500 and never a blanked list. A warm list resolves instantly from the per-symbol cache. A choppy list no longer spends seconds per symbol inside head-and-shoulders enumeration.

Verification: `uv run python manage.py test` is green; offline orchestration tests prove the deadline degrades unresolved rows and preserves item order; a manual cold-list benchmark against a real key shows the page returning within the budget with per-row degradation.

### Key Discoveries:

- **Moving the call sites changes the test patch target.** `watchlist/tests.py` patches `watchlist.views.fetch_daily_candles`/`watchlist.views.score_formation`; if the calls move into a service module, those patches must be retargeted or the suite will attempt real work.
- **`fetch_daily_candles` reads its timeout from settings only** (`marketdata/services.py:76`), so a shorter scan timeout needs either a settings change (affects `fetch_candles`/`score_symbol` too) or a new optional parameter.
- **Threads need per-thread DB connection hygiene and interact badly with dev SQLite writes.** Django connections are per-thread; a `ThreadPoolExecutor` worker that hits the ORM must close its connection, and SQLite serializes writes (a concurrent upsert can surface as a per-row error in dev).
- **The warm path is already fast** — a scan where every row is cache-fresh issues no HTTP, so the budget matters mainly for the cold/slow path.
- **F1 is a CPU-bound cost threads cannot fix** (single sync worker + GIL), so bounding the enumeration is the only lever that shrinks the scoring half of the budget.

## What We're NOT Doing

- No progressive render, no new JavaScript, no new JSON/fragment endpoint or URL — the scan stays server-rendered in one request.
- No 429 pacing, sleeping, retry or backoff (F-02 deliberately excluded it); the cold overflow degrades to a per-row `rate limited` message.
- No persistence of scores or scan history — scores remain computed per request.
- No change to gunicorn worker/threads or any deploy/runtime config (`Dockerfile`, Railway settings).
- No S-04 end-to-end flow test — that stays its own slice.
- No change to `fetch_daily_candles`' cache/prune/stale semantics beyond adding an optional timeout parameter.
- No change to `score_formation`'s result shape, grades or thresholds — only the enumeration cost inside `detection/patterns.py`.
- No new provider, fallback provider, cache framework, Redis or background worker.
- No change to watchlist CRUD, forms, models, privacy scoping or the add/remove flows.

## Implementation Approach

Three moves, in order: make the detection engine cheap enough that scoring is not the bottleneck, then parallelize the per-row orchestration behind a budget, then prove the behavior offline.

```
watchlist.index
      │  items
      ▼
watchlist.services.scan_watchlist(items, *, max_workers, per_row_timeout, budget_seconds)
      │  ThreadPoolExecutor (≤ WATCHLIST_SCAN_MAX_WORKERS)
      │   one task per item, bounded by WATCHLIST_SCAN_BUDGET_SECONDS
      ▼
marketdata.services.fetch_daily_candles(symbol, timeout=per_row_timeout)  ──▶  detection.services.score_formation
      │
      └─ each task isolated; per-thread DB connection closed in a finally
```

- **Phase 1** bounds the H&S (and double-top) candidate search in `detection/patterns.py` to a recent pivot window and/or makes per-candidate scoring cheaper, without changing the public result.
- **Phase 2** introduces `watchlist/services.py` (the `Row` type moved here plus `scan_watchlist`), threads an optional `timeout` through `fetch_daily_candles`, adds three scan settings, and rewires `watchlist.index` to the service while keeping the `items` context variable.
- **Phase 3** converts the existing patch targets and adds offline delay-stub orchestration tests, then verifies with a manual cold-list benchmark.

## Critical Implementation Details

- **Deadline semantics.** Submit every item, then collect each future with `future.result(timeout=<remaining budget>)`. A future that misses the deadline yields a "still scanning" row message; do **not** block on it. Shut the executor down with `wait=False` so the view returns on time — a `with ThreadPoolExecutor(...)` context manager would wait for every worker and re-introduce the stall.
- **Per-thread connections.** Each pool worker that touches the ORM must close its thread-local connection in a `finally` (`django.db.close_old_connections()`), or connections leak per request. On dev SQLite, concurrent writes may raise `database is locked`; the per-row `try/except` already converts that into a row message, which is acceptable for the dev-only path.
- **Keep `items` in the context.** `watchlist/tests.py:97-99` asserts on `response.context["items"]`; `index` must keep passing the queryset alongside `rows`.
- **Retarget the existing patches.** All three existing test classes patch `watchlist.views.*`; once the calls live in `watchlist.services`, those patches must move to `watchlist.services.fetch_daily_candles` / `watchlist.services.score_formation` or the tests will do real work.
- **Timeout parameter is additive.** Give `fetch_daily_candles` a keyword-only `timeout: float | None = None` that falls back to `settings.MARKET_DATA_HTTP_TIMEOUT`; existing callers (`fetch_candles`, `score_symbol`) are unchanged.

## Phase 1: Bound pattern enumeration (F1 perf fix)

### Overview

Reduce the CPU cost of the pattern scorers on noisy series so a dozen-symbol scan is not dominated by scoring. No result shape or grading change.

### Changes Required:

#### 1. Bound the candidate search

**File**: `detection/patterns.py`

**Intent**: Stop `score_head_shoulders` (and `score_double_top`) from scoring hundreds of thousands of geometrically-valid pivot combinations on a choppy series, so per-symbol scoring is well under the budget without suppressing a currently-forming pattern.

**Contract**: keep the public signatures — `score_double_top(pivots, *, atr_value, tolerance, min_separation) -> Candidate | None` and `score_head_shoulders(pivots, *, atr_value, tolerance, min_separation) -> Candidate | None` — and the `Candidate` / `CandidateEvidence` shapes unchanged. Restrict the enumeration to pivots relevant to a *currently forming* pattern (a bounded recent-pivot lookback expressed as a new named module constant, e.g. `MAX_PIVOT_LOOKBACK`), and/or precompute the last-confirmed-low-before each position so per-candidate scoring is O(1). Any new constant lives next to the existing tunables and is documented in the module. Do not change `sub_score` weights, stages, or the returned evidence fields.

#### 2. Enumeration-cost regression test

**File**: `detection/tests.py`

**Intent**: Guard the bound so a future edit cannot silently reintroduce the combinatorial blow-up, and confirm the bound does not drop a real forming pattern.

**Contract**: add a test using a deterministic, seeded noisy 500-bar series (many pivots) asserting `score_formation`/the scorers return within a generous time bound and still detect a planted forming head-and-shoulders; keep the existing `ScoreFormationTests` cases green and unchanged in intent.

### Success Criteria:

#### Automated Verification:

- Detection tests pass: `uv run python manage.py test detection`
- Django system checks pass: `uv run python manage.py check`

#### Manual Verification:

- A seeded noisy 500-bar series shows a measurably lower head-and-shoulders time/symbol than the ~2.9 s baseline in `review-fixes.md`, with the same detected pattern.

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 2: Bounded-parallel scan orchestration + view wiring

### Overview

Add the scan orchestration service, thread an optional timeout through the fetch boundary, add the scan settings, and rewire `watchlist.index` to use them — keeping the existing context contract and row/template behavior.

### Changes Required:

#### 1. Scan orchestration service

**File**: `watchlist/services.py` (new)

**Intent**: Own the bounded-parallel scan so the view stays thin and the orchestration is unit-testable without HTTP, and so per-row isolation is enforced in one place.

**Contract**: move the `Row` frozen dataclass here (imported by the view) and add `scan_watchlist(items, *, max_workers=None, per_row_timeout=None, budget_seconds=None) -> list[Row]`. Defaults come from settings. Behavior: one task per item via `concurrent.futures.ThreadPoolExecutor(max_workers=...)`; each task calls `fetch_daily_candles(item.symbol, timeout=per_row_timeout)` then `score_formation(...)` and returns a `Row`; results preserve the input `items` order; an exception in a task is caught and becomes `Row(item, None, message="analysis failed")`; a future that exceeds the remaining budget yields `Row(item, None, message="still scanning")`. Each worker closes its DB connection in a `finally`. The deadline-collection shape is load-bearing:

```python
with ThreadPoolExecutor(max_workers=max_workers) as pool:
    futures = {item.pk: pool.submit(_build_row, item, per_row_timeout) for item in items}
    deadline = time.monotonic() + budget_seconds
    rows = []
    for item in items:
        remaining = deadline - time.monotonic()
        try:
            rows.append(futures[item.pk].result(timeout=max(0.0, remaining)))
        except TimeoutError:
            rows.append(Row(item=item, score=None, stale=False, message="still scanning"))
return rows
```

(An item that times out must not block the loop; the `with` block's implicit wait is acceptable only because unresolved tasks are already past the budget — otherwise use an explicit `shutdown(wait=False)`.)

#### 2. Optional timeout on the fetch boundary

**File**: `marketdata/services.py`

**Intent**: Let the scan cap a single symbol's HTTP wait below the 10 s default without changing the timeout for the command-line tools.

**Contract**: add keyword-only `timeout: float | None = None` to `fetch_daily_candles` (`marketdata/services.py:40`); when provided it is passed to `twelvedata.fetch_daily(...)` in place of `settings.MARKET_DATA_HTTP_TIMEOUT` (`:76`). Default `None` preserves current behavior for `fetch_candles` and `score_symbol`.

#### 3. Scan settings

**File**: `stock_guard/settings.py`

**Intent**: Make the pool size, per-row timeout and total budget env-driven with safe defaults, following the existing `.get()` convention.

**Contract**: append, alongside the market-data settings (`stock_guard/settings.py:191-196`):

```python
WATCHLIST_SCAN_MAX_WORKERS = int(os.environ.get("WATCHLIST_SCAN_MAX_WORKERS", "8"))
WATCHLIST_SCAN_PER_SYMBOL_TIMEOUT = float(os.environ.get("WATCHLIST_SCAN_PER_SYMBOL_TIMEOUT", "3"))
WATCHLIST_SCAN_BUDGET_SECONDS = float(os.environ.get("WATCHLIST_SCAN_BUDGET_SECONDS", "5"))
```

#### 4. Wire the view

**File**: `watchlist/views.py`

**Intent**: Replace the sequential loop with the orchestration service while preserving ordering, the `items` context variable, and the add/remove behavior.

**Contract**: `index` keeps building `items = request.user.watchlist_items.all()` and keeps `{"form": form, "items": items, "rows": rows}` (`watchlist/views.py:67-73`), but `rows = scan_watchlist(items)` imported from `watchlist.services`; remove the now-moved `Row`/`_build_row` definitions. `remove` is unchanged.

### Success Criteria:

#### Automated Verification:

- Watchlist tests pass (patch targets retargeted): `uv run python manage.py test watchlist`
- Existing auth suite still passes: `uv run python manage.py test accounts`
- Django system checks pass: `uv run python manage.py check`
- No migration drift remains: `uv run python manage.py makemigrations --check --dry-run`

#### Manual Verification:

- The list page still renders grade badges, `(stale)` markers and per-row messages; a cold list renders within the budget with unresolved rows showing "still scanning".

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 3: Offline tests, benchmark & verification

### Overview

Prove the orchestration's deadline and per-row isolation offline, retarget the orchestration seam for tests, and verify end to end with a manual cold-list benchmark.

### Changes Required:

#### 1. Orchestration tests

**File**: `watchlist/tests.py`

**Intent**: Cover the new behavior deterministically without network or wall-clock flakiness.

**Contract**: keep the existing patch-then-assert style, retargeted to `watchlist.services.fetch_daily_candles`/`watchlist.services.score_formation`, and add a class (e.g. `ScanWatchlistTests`) asserting: a slow fetch stub (sleeps past `budget_seconds`) yields a "still scanning" row and never raises; one task raising still yields a `Row` for every item in input order; a `PriceUnavailable(reason="rate_limited")` yields the `rate limited` row message; a `PriceSeries(status="stale")` sets `stale=True`; the returned order matches `items`. Method names follow `test_...Returns...When...`.

#### 2. Verification & benchmark pass

**File**: (no new file — manual + CI)

**Intent**: Confirm the slice against the real provider and the responsive budget.

**Contract**: run `uv run python manage.py test`, `uv run python manage.py check`, and `uv run python manage.py collectstatic --noinput`; then, with a real `TWELVE_DATA_API_KEY`, time a cold list of ~12 symbols after clearing the `DailyCandle` cache, confirming the page returns within ~5 s and slow/rate-limited rows show per-row messages.

### Success Criteria:

#### Automated Verification:

- Full test suite passes: `uv run python manage.py test`
- Django system checks pass: `uv run python manage.py check`
- Static collection still succeeds: `uv run python manage.py collectstatic --noinput`

#### Manual Verification:

- A cold ~12-symbol list returns within ~5 s and remains usable, with unresolved/rate-limited rows showing clear per-row messages and the rest rendering normally.
- Repeated opens of a warm list resolve promptly with no outbound fetch.

---

## Testing Strategy

### Unit Tests:

- Detection: the bounded enumeration returns within a generous time bound on a seeded noisy series and still detects a planted forming head-and-shoulders; existing engine cases remain green.
- Orchestration: deadline degradation, per-row exception isolation, order preservation, `rate_limited`/`stale` row mapping, and the pool being bounded.

### Integration Tests:

- `watchlist.index` with `watchlist.services` patched: a graded row renders its badge; a stale row renders `(stale)`; an unavailable row renders its message; a slow row renders "still scanning"; one failing row does not blank the list or 500.

### Manual Testing Steps:

1. `uv lock && uv sync`, then `uv run python manage.py test`.
2. Seed a user with ~12 symbols, clear `DailyCandle`, and open `/` with a real key; time the response and confirm the budget.
3. Confirm a rate-limited/overflow row shows a message while other rows show grades.
4. Reopen `/` and confirm the list is fast (warm cache) with no new provider calls.
5. Unset `TWELVE_DATA_API_KEY` and reload; confirm per-row messages rather than an error page.

## Performance Considerations

- The budget targets two distinct costs: HTTP wait (bounded by the per-row timeout and the pool) and CPU scoring (bounded by the Phase 1 enumeration fix). In-request threads overlap the HTTP wait; they do not parallelize CPU-bound scoring under the GIL, which is why Phase 1 matters.
- The cold path is additionally capped by Twelve Data's **8 credits/min**: a cold dozen legitimately exceeds it, so the correct outcome is per-row `rate limited` messages (NFR-02), not a longer wait.
- The warm path issues no HTTP and is dominated by ~12 indexed `(symbol, date)` reads plus scoring, staying well inside the budget.
- The pool is size-capped (`WATCHLIST_SCAN_MAX_WORKERS=8`) to avoid fanning out Postgres connections and to keep the cold credit burst near the limit; each worker closes its DB connection per request.

## Migration Notes

- No schema change and no migration: no model is added or altered, so `makemigrations --check` stays clean.
- No new runtime dependency and no `uv.lock` change.
- No deploy/runtime change: gunicorn stays at its current worker configuration; the three scan settings default correctly when their env vars are absent.
- Rolling back = revert `watchlist/services.py` + `watchlist/views.py` to the sequential loop and drop the settings/param; no data to unwind.

## References

- Roadmap slice S-03: `context/foundation/roadmap.md:129-140`; S-04 boundary: `context/foundation/roadmap.md:142-152`
- PRD: FR-007 (`context/foundation/prd.md:84-85`), FR-004 (`:76`), US-01 (`:50-60`), NFR responsiveness `:95`, partial-failure `:96`, daily-candle `:98`
- Current scan path: `watchlist/views.py:26-73`, `watchlist/templates/watchlist/list.html:16-35`, `watchlist/tests.py`
- Fetch boundary: `marketdata/services.py:40-108` (timeout at `:76`, single-worker note `:43-45`), `marketdata/providers/twelvedata.py`
- Detection engine: `detection/services.py:19-27`, `detection/patterns.py`; F1: `context/archive/2026-11-08-formation-detection-service/follow-ups/review-fixes.md:5-13`
- Rate limits & cold cost: `context/archive/2026-10-18-price-data-fetch-boundary/plan.md:23,308`
- Settings conventions: `stock_guard/settings.py:191-196`; runtime: `Dockerfile:27`; CI: `.github/workflows/ci.yml:28-29`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Bound pattern enumeration (F1 perf fix)

#### Automated

- [x] 1.1 Detection tests pass — e192faa
- [x] 1.2 Django system checks pass — e192faa

#### Manual

- [ ] 1.3 Seeded noisy 500-bar series shows lower H&S time/symbol than the ~2.9 s baseline

### Phase 2: Bounded-parallel scan orchestration + view wiring

#### Automated

- [x] 2.1 Watchlist tests pass (patch targets retargeted)
- [x] 2.2 Existing auth suite still passes
- [x] 2.3 Django system checks pass
- [x] 2.4 No migration drift remains

#### Manual

- [ ] 2.5 List page renders badges, stale markers and messages; cold list renders within budget

### Phase 3: Offline tests, benchmark & verification

#### Automated

- [ ] 3.1 Full test suite passes
- [ ] 3.2 Django system checks pass
- [ ] 3.3 Static collection still succeeds

#### Manual

- [ ] 3.4 Cold ~12-symbol list returns within ~5 s with per-row messages for unresolved rows
- [ ] 3.5 Repeated opens of a warm list resolve promptly with no outbound fetch
