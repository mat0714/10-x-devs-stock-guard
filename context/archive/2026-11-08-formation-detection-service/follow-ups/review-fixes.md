# Review Fixes (queued)

Follow-ups from `reviews/impl-review.md` that were not fixed during triage.

## F1 — Bound head-and-shoulders candidate enumeration

- **Source**: reviews/impl-review.md F1 (WARNING, Safety & Quality / performance)
- **Location**: `detection/patterns.py:104-214`
- **Context**: `score_head_shoulders` enumerates five nested pivot levels. On a noisy 500-bar random walk (119 pivots) ~951k geometrically-valid candidate combinations are scored, each doing O(p) work (`_prior_trend`, `_first_low_below_neckline`), taking ~2.9 s/symbol.
- **What was tried**: precomputing confirmed-high/confirmed-low/high/low position lists and `bisect`-slicing each level. Benchmark: 0 output mismatches but 1.0x speedup (37.1 s → 38.0 s over 120 cases). Reverted; the change reduced only cheap skipped pivots, not matching combinations.
- **Why it matters**: contradicts the plan's "well under a second" performance note; a watchlist of choppy symbols can block gunicorn workers, and S-03 parallelism multiplies the CPU cost.
- **Suggested action**: bound the candidate set (e.g. restrict `left`/`head` to a recent pivot window appropriate to "currently forming" detection) and/or make per-candidate scoring O(1) (precompute last-confirmed-low-before per position, avoid repeated neckline scans). Re-measure before/after and re-run the engine + full suite.

## F2 — Scan-orchestration latency deferred to S-03

- **Source**: reviews/impl-review.md F2 (WARNING, Safety & Quality / performance)
- **Location**: `watchlist/views.py:61-62`
- **Context**: `index` makes one `fetch_daily_candles` + `score_formation` call per row, sequentially. A cold list pays N × (≤10 s HTTP + scoring) and may hit Twelve Data's 8 credits/min. Per-row failure is isolated (row message, no 500).
- **Decision**: Accepted/deferred — S-02 explicitly excludes orchestration and the latency budget (`plan.md:47`, `plan.md:347`); S-03 owns parallel fetch, progressive rendering, pre-warm and timeout tuning.
- **Action for S-03**: carry this measurement into S-03 planning; add a cold-list latency benchmark and consider bounded concurrency / pre-warm.
