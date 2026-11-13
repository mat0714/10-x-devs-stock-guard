<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Formation Detection Service Implementation Plan

- **Plan**: context/changes/formation-detection-service/plan.md
- **Scope**: Full plan
- **Reviewed phases**: 1, 2, 3, 4
- **Date**: 2026-11-13
- **Verdict**: NEEDS ATTENTION
- **Findings**: 0 critical, 2 warnings, 3 observations

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

### F1 — Head-and-shoulders scorer is O(p⁵) over pivots (measured up to ~5.4 s/symbol)

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: detection/patterns.py:121-215
- **Detail**: `score_head_shoulders` uses five nested pivot loops plus linear `_first_low_below_neckline` scans inside them. Pivot count on a realistic 500-bar random-walk series was measured at 87–250, and a read-only benchmark measured 55 ms–5.4 s per symbol (worst seed 144 pivots → 5.4 s). This contradicts the plan's Performance Considerations ("runs in well under a second") and would block gunicorn workers under concurrency; S-03 parallelism would multiply the CPU cost.
- **Fix A ⭐ Recommended**: Precompute confirmed-high / confirmed-low index lists and iterate only those at each level, and hoist the `_first_low_below*` scan out of the innermost loop.
  - Strength: Cuts the branching factor to the few pivots of the required kind without changing thresholds or match semantics.
  - Tradeoff: More code in the scorers; engine tests must be re-run to confirm identical outcomes.
  - Confidence: MEDIUM — the nested-loop shape is the dominant cost; exact post-refactor complexity unmeasured.
  - Blind spot: Not benchmarked after a refactor.
- **Fix B**: Cap or downsample the pivot list before scanning (e.g. only the last N pivots).
  - Strength: Hard-bounds worst-case CPU.
  - Tradeoff: Can miss older valid formations; changes detection semantics.
  - Confidence: LOW — detection-quality impact unmeasured.
  - Blind spot: No labelled data to quantify missed signals.
- **Decision**: DEFERRED — Fix A was applied and benchmarked (0 output mismatches but 1.0x speedup: 37.1s → 38.0s over 120 cases), then reverted. Root cause: ~951k valid H&S candidate combinations per noisy 500-bar symbol plus O(p) per-candidate work; precomputing kind lists does not reduce matching combinations. Queued as follow-up: bound candidate enumeration (e.g. recent pivots) and/or O(1) per-candidate scoring.

### F2 — Sequential synchronous per-row fetch + scoring on the request path

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: watchlist/views.py:61-62
- **Detail**: `index` calls `fetch_daily_candles` + `score_formation` once per row, sequentially. A cold list pays N × (≤10 s HTTP + scoring) and may trip Twelve Data's 8 credits/min. Per-row failure IS isolated; this latency/orchestration concern is explicitly deferred to S-03 by the plan (plan.md:47, 347).
- **Fix**: No change in S-02 — explicitly out of scope and deferred to S-03; carry this measurement into S-03 planning (parallel fetch, progressive render, pre-warm, timeout tuning).
  - Strength: Preserves the approved S-02/S-03 boundary.
  - Tradeoff: Cold-list latency stays poor until S-03 ships.
  - Confidence: HIGH — the deferral is stated in the plan and roadmap.
  - Blind spot: None significant.
- **Decision**: DEFERRED — no code change in S-02 (explicitly S-03 scope per plan.md:47, 347); measurement queued in follow-ups/review-fixes.md for S-03.

### F3 — Broad per-row exception is swallowed without logging

- **Severity**: 🔍 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: watchlist/views.py:39-42
- **Detail**: `_build_row` catches `Exception` and degrades to `message="analysis failed"` but logs nothing, unlike `marketdata/services.py:98` (`_logger.warning`). A swallowed engine traceback is invisible in production.
- **Fix**: Add a module logger and `_logger.warning("Formation analysis failed for %s", item.symbol, exc_info=True)` in the except branch.
- **Decision**: FIXED — added `_logger = logging.getLogger(__name__)` and the warning with `exc_info=True` in `_build_row`'s except branch.

### F4 — Float arrays are rebuilt twice per score

- **Severity**: 🔍 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: detection/pivots.py:114-118
- **Detail**: `score_formation` calls `atr` (which calls `_arrays`) and then `find_pivots` (which calls `_arrays` again), converting the same candles to floats twice per symbol.
- **Fix**: Convert once in `score_formation` and pass the float arrays (or a cached conversion) to both ATR and pivots.
- **Decision**: FIXED — added `float_arrays`, `atr_from_arrays`, `find_pivots_from_arrays` to `detection/pivots.py`; `score_formation` converts once and passes the arrays. Public `atr`/`find_pivots` signatures unchanged; detection tests green.

### F5 — Confirmation is derived from a pivot low, not a literal bar close

- **Severity**: 🔍 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: detection/patterns.py:69-75, 160-162
- **Detail**: The plan words the confirmed stage as "a close below that trough", but the pinned scorer signature receives only pivots (no closes), so implementation uses the first low pivot below the trough/neckline. This can differ from a strict close-based break when a wick pierces the neckline and the close recovers. It is the feasible realization of the pinned contract.
- **Fix**: Accepted interpretation — no code change. If strict close semantics are required later, extend the scorer signature to receive closes and add a test for the wick-recovery case.
- **Decision**: ACCEPTED — pivot-low confirmation accepted as the feasible realization of the pinned pivots-only signature; revisit only if strict close semantics are required.
