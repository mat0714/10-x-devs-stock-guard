<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Scan on Login Flagged List

- **Plan**: context/changes/scan-on-login-flagged-list/plan.md
- **Scope**: Full plan
- **Reviewed phases**: 1, 2, 3
- **Date**: 2026-11-13
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 4 warnings, 4 observations

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

### F1 — Unvalidated `max_workers` hard-500s the list page

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: watchlist/services.py:42,48; stock_guard/settings.py:201
- **Detail**: `max_workers` comes from an env-overridable setting and is passed straight into `ThreadPoolExecutor`, which raises `ValueError` for 0 or negative. A misconfigured `WATCHLIST_SCAN_MAX_WORKERS=0` therefore 500s every list load at the request boundary instead of degrading per row — inconsistent with the module's "never raise, degrade per row" contract.
- **Fix**: Clamp before constructing the pool (`max_workers = max(1, int(max_workers))`), ideally also at settings load.
- **Decision**: FIXED

### F2 — `close_old_connections()` does not release fresh prod connections

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: watchlist/services.py:94-95
- **Detail**: The worker `finally` calls `close_old_connections()`, which only closes a connection whose `close_at` has passed. Dev SQLite (`CONN_MAX_AGE=0`) closes, but production sets `conn_max_age=600` (stock_guard/settings.py:103-107), so a worker's fresh connection is NOT closed and lingers until thread GC. Under load this can accumulate Postgres connections, contradicting the plan's "each worker closes its DB connection per request" (plan.md:68).
- **Fix A ⭐ Recommended**: Use `from django.db import connection` and `finally: connection.close()` to explicitly release the worker's thread-local connection.
  - Strength: Exactly matches the plan's per-worker-close intent; deterministic release.
  - Tradeoff: Slightly deviates from the familiar `close_old_connections()` idiom used elsewhere.
  - Confidence: HIGH — `connection.close()` is the documented per-thread release primitive.
  - Blind spot: Have not load-tested connection count under concurrent requests.
- **Fix B**: Keep `close_old_connections()` and accept GC-timed release.
  - Strength: Minimal change, standard Django idiom.
  - Tradeoff: Bounded-but-real connection accumulation in prod under concurrency.
  - Confidence: MEDIUM — depends on GC/thread-death timing.
  - Blind spot: No measurement of peak connection count.
- **Decision**: FIXED via Fix A

### F3 — `shutdown(wait=False)` does not cancel queued work

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: watchlist/services.py:67
- **Detail**: `pool.shutdown(wait=False)` returns the response on time but leaves not-yet-started futures running. In the 12-symbol/8-worker cold case, the queued overflow still hits the provider (spending the tracked 8-credits/min quota) and opens DB connections, yet its results are discarded because the user already saw "still scanning".
- **Fix**: `pool.shutdown(wait=False, cancel_futures=True)` (Python 3.9+, fine on 3.12) so unstarted tasks are dropped; in-flight ones still finish.
- **Decision**: FIXED

### F4 — `MAX_PIVOT_LOOKBACK` bound and its comment over-claim

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality / Plan Adherence
- **Location**: detection/patterns.py:18-23,58,131
- **Detail**: The bound restricts only the OPENING pivot to the last 20 pivots, but the module comment says it "keeps every forming pattern". That is not provable: a forming pattern is anchored only by its trailing pivot being last, so its opening peak / left shoulder can sit arbitrarily far back. On a 500-bar noisy series a >20-pivot-back opening pivot is realistic and would now be silently dropped (recall regression for forming and confirmed patterns). The single regression test only proves the one planted pattern falls inside the window; it does not prove exhaustiveness. The plan said Phase 1 should change enumeration COST, not which patterns are returned.
- **Fix A ⭐ Recommended**: Correct the constant's comment to state it is a deliberate recall-vs-cost bound (not lossless), and add a test/note documenting the intended limit.
  - Strength: Honest; keeps the perf win the plan asked for; no behavior change beyond what already shipped.
  - Tradeoff: Accepts the recall tradeoff explicitly rather than removing it.
  - Confidence: HIGH — matches the plan's "currently forming" intent and time budget.
  - Blind spot: No field evidence that a real scenario needs a deeper opening pivot.
- **Fix B**: Widen or make the bound adaptive (price/ATR distance, or extend while still forming) so opening pivots are not dropped by raw pivot count.
  - Strength: Removes the recall risk.
  - Tradeoff: Larger diff; must re-benchmark to keep the cost win (the earlier bisect attempt only reached 1.0x).
  - Confidence: MEDIUM — the perf/cost re-tradeoff is unproven.
  - Blind spot: Have not measured cost of an adaptive bound.
- **Decision**: FIXED via Fix A (comment reframed; bound unchanged)

### F5 — Futures keyed by `item.pk`

- **Severity**: 👁 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: watchlist/services.py:49-51,54-57
- **Detail**: Keying futures by `item.pk` assumes unique, non-None pks. An unsaved item or a duplicated object would collapse two items onto one future, returning the wrong `Row`. Cannot trigger from a DB queryset today, but is unnecessary fragility when the list is already ordered.
- **Fix**: Zip positionally, e.g. `futures = [pool.submit(...) for item in items]` then `zip(items, futures)`.
- **Decision**: FIXED

### F6 — Executor shutdown not in `try/finally`

- **Severity**: 👁 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: watchlist/services.py:67,87-93
- **Detail**: `pool.shutdown` sits after the collection loop, not in a `finally`, so an unexpected raise from `future.result()` would leak the executor. (Normal task failures are already caught in `_build_row`; a `BaseException` could still escape.)
- **Fix**: Wrap the collection loop in `try/finally: pool.shutdown(wait=False, cancel_futures=True)`.
- **Decision**: FIXED

### F7 — `timeout` parameter unvalidated

- **Severity**: 👁 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: marketdata/services.py:44,80-90
- **Detail**: The new `timeout` is additive and backward-compatible (verified), but unlike `bars` just above it is not validated; httpx accepts 0/negative and the result maps to a `provider_error` row, so impact is low but inconsistent.
- **Fix**: Optionally reject/clamp a non-positive timeout, mirroring the `bars` guard.
- **Decision**: FIXED

### F8 — Per-request, unbounded-executor thread fan-out

- **Severity**: 👁 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality / Performance
- **Location**: watchlist/services.py:48; stock_guard/settings.py:201-203
- **Detail**: A fresh `ThreadPoolExecutor` (up to `WATCHLIST_SCAN_MAX_WORKERS` threads) is created per request with no upper bound. Fine on the documented single sync worker; total thread count scales with concurrent requests if the runtime later adopts threads.
- **Fix**: Acceptable as-is for the single-sync-worker target; consider a shared/bounded pool if the runtime changes.
- **Decision**: FIXED (added MAX_SCAN_WORKERS = 32 upper cap)

### F9 — Test gap: default pool bound not asserted; quote convention

- **Severity**: 👁 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency / Success Criteria
- **Location**: watchlist/tests.py:261-367; watchlist/services.py:19-23
- **Detail**: The plan's testing strategy names "the pool being bounded" (plan.md:235), but `ScanWatchlistTests` only passes explicit `max_workers`; nothing asserts the default worker count. Separately, `watchlist/services.py` uses single quotes while sibling service modules (`detection/services.py`, `marketdata/services.py`) use double quotes — defensible, since the whole `watchlist/` app is single-quoted.
- **Fix**: Add a small assertion that the default `max_workers` is a positive bounded value; quote-style left as-is (app-local convention).
- **Decision**: FIXED (added bounded-pool test)
