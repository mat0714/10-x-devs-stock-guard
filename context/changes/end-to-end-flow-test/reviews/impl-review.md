<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: End-to-End Flow Test Implementation Plan

- **Plan**: context/changes/end-to-end-flow-test/plan.md
- **Scope**: Full plan
- **Reviewed phases**: 1, 2
- **Date**: 2026-11-13
- **Verdict**: APPROVED
- **Findings**: 0 critical, 1 warning, 4 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | PASS |
| Safety & Quality | PASS |
| Architecture | PASS |
| Pattern Consistency | WARNING |
| Success Criteria | PASS |

## Findings

### F1 — Test base class is `TransactionTestCase`, not the planned `TestCase`

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: watchlist/tests.py:433
- **Detail**: The plan specified a Django `TestCase` (plan.md:5,15,70,88) but the class subclasses `TransactionTestCase`, diverging from every sibling class in the suite. Reviewers split: one marked it DRIFT (undocumented vs. plan), another recommended reverting to `TestCase`. Direct verification settles it: with `TestCase`, the scan's worker thread writes `DailyCandle` on a separate SQLite connection while the test holds a wrapping transaction, and the row degrades to `database table is locked` — the test fails (`assertContains "badge"` → False). With `TransactionTestCase` the flow is deterministically green (5/5 runs). The deviation is therefore REQUIRED, not a defect; the plan's "transaction-rolled-back DB" rationale (plan.md:63) no longer applies.
- **Fix**: Keep `TransactionTestCase` and record the rationale — add a one-line comment above the class (or amend the plan) explaining the SQLite worker-thread write requires a committing test class. Optionally note it is the only non-`TestCase` class in the suite.
- **Decision**: FIXED — added a one-line comment above `EndToEndFlowTests` explaining the worker-thread SQLite write requires a committing test class.

### F2 — `assertRedirects(..., fetch_redirect_response=False)` deviates from the plan's bare "asserts the redirect"

- **Severity**: ⚠️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: watchlist/tests.py:448
- **Detail**: The plan said "asserts the redirect to `/`" (plan.md:92) without specifying the follow behavior. Without `fetch_redirect_response=False`, `assertRedirects` follows the redirect to `GET /` and triggers `scan_watchlist` OUTSIDE the stubbed patch — a real, un-stubbed `twelvedata.fetch_daily` network call (observed as a logged `Market data fetch failed for AAPL: auth_failed`). The flag keeps the single-stub-seam guarantee. Status 200 is still asserted at :459 on the explicitly stubbed GET.
- **Fix**: Keep as-is; the flag is necessary to honor the plan's "exactly one seam" intent.
- **Decision**: FIXED (kept as-is) — flag is required; no code change.

### F3 — Fixture stub returns a `list`, sibling fixtures use tuples

- **Severity**: ⚠️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: watchlist/tests.py:453
- **Detail**: `fetch.return_value = list(_planted_double_top(...))` wraps a tuple into a list. Sibling fixtures (`detection/tests.py`) use tuples. Harmless — the real provider returns `list[Candle]`, so the stub is faithful — but inconsistent with the local builder's tuple return.
- **Fix**: Optionally drop the `list(...)` wrap. Non-blocking.
- **Decision**: FIXED — dropped the `list(...)` wrap; the stub now returns the tuple directly.

### F4 — `@override_settings` is the repo's first use; siblings use `self.settings`

- **Severity**: ⚠️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: watchlist/tests.py:445
- **Detail**: `marketdata/tests.py` uses the `self.settings(...)` context manager; this test uses `@override_settings`. The plan explicitly authorized `@override_settings` (plan.md:26,91), so it is intended, but it is a convention divergence.
- **Fix**: Acceptable per plan; consider `self.settings` only if harmonizing later.
- **Decision**: FIXED (kept as-is) — `@override_settings` is plan-authorized and standard; no code change.

### F5 — Plan's isolated-test command does not resolve

- **Severity**: ⚠️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: plan.md:101,190
- **Detail**: The plan's Phase 1 automated command `uv run python manage.py test watchlist.EndToEndFlowTests` fails with `ModuleNotFoundError`. For a class defined inside `watchlist/tests.py`, the correct label is `watchlist.tests.EndToEndFlowTests`. The command in Progress row 1.1 is therefore not literally runnable; the equivalent correct command was run and passed. The other gates are unaffected.
- **Fix**: Correct the plan's command label (plan defect, informational). No code change needed.
- **Decision**: FIXED — corrected the plan's command label in the Phase 1 block and Progress row 1.1 to `watchlist.tests.EndToEndFlowTests`.

## Environmental note

`context/foundation/roadmap.md` is modified in the working tree (S-04 → in-progress) and was intentionally left unstaged because it was pre-dirty on entry. Not part of the reviewed diff; commit it separately.
