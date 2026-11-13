# Scan on Login Flagged List — Plan Brief

> Full plan: `context/changes/scan-on-login-flagged-list/plan.md`

## What & Why

Roadmap slice **S-03** makes the north-star flow real: after logging in, the user's whole watchlist is auto-scanned and shown with graded bearish-formation flags. The list page already scans each row (`watchlist.index`), but it does so **sequentially**, so a cold or slow list can blow the PRD's "within a few seconds" responsiveness NFR and trip the price provider's rate limit. S-03 replaces that loop with a bounded-parallel scan behind a time budget and makes the CPU scoring cheap enough that it is not the bottleneck.

## Starting Point

- Login already redirects to `/` (`settings.LOGIN_REDIRECT_URL`), and `watchlist.index` already calls `fetch_daily_candles` + `score_formation` per row, isolating failures and rendering badges, a `(stale)` marker and per-row messages (`watchlist/views.py:26-73`, `list.html:16-35`).
- `fetch_daily_candles` caches a rolling per-symbol window in Postgres and never raises; its HTTP timeout is a fixed 10 s from settings. Twelve Data Basic allows **8 credits/min** (1/symbol), so a cold 12-symbol scan legitimately exceeds the limit and must degrade per row.
- No JS/HTMX/JSON endpoints, no cache framework or background runner exist; the runtime is a single sync gunicorn worker; dev is SQLite, prod is Postgres.
- The deferred **F1** follow-up shows head-and-shoulders enumeration taking ~2.9 s/symbol on noisy series.

## Desired End State

Opening `/` scans the list in parallel and returns within roughly the budget. Formation rows show graded badges, cached/broken rows show `(stale)` or a message, and rows that did not resolve in time or hit the credit limit show a clear per-row message — never a 500, never a blanked list. Warm lists resolve instantly from cache.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) |
| -------- | ------ | ---------------- |
| Scan trigger | Every list-page open (keep current) | Matches PRD FR-007 wording and needs no session state; warm repeats are cache-only. |
| Orchestration strategy | Bounded parallel + deadline | Attacks cold/slow-row latency within one request with no new JS or endpoint; per-row degradation already exists. |
| Responsiveness budget | ~5 s total / ~3 s per row | Sits inside "few seconds" and bounds one slow symbol within the sync worker's expectations. |
| Cold overflow (8/min) | Per-row "rate limited" message | Matches F-02's no-pacing design and NFR-02; honest per-row degradation. |
| F1 perf fix | In scope for S-03 | Threads can't speed up CPU-bound scoring under the GIL, so bounding enumeration is the only lever for the scoring half of the budget. |
| Pool / runtime | In-request pool ≤8, gunicorn config unchanged | I/O overlap cuts cold latency; pool size matches the 8/min ceiling; no deploy changes. |
| Scope vs S-04 | Orchestration + view tests here; e2e stays S-04 | Preserves the roadmap slice boundary. |
| Verification | Offline delay-stub tests + manual benchmark | Deterministic and CI-safe; the wall-clock budget is confirmed by hand. |

## Scope

**In scope:** bounding the H&S/double-top enumeration in `detection/patterns.py`; a new `watchlist/services.py` bounded-parallel scan (`scan_watchlist`); an optional `timeout` on `fetch_daily_candles`; three scan settings; rewiring `watchlist.index`; retargeted plus new offline tests; a manual cold-list benchmark.

**Out of scope:** progressive render / new JS / JSON endpoint; 429 pacing/retry/backoff; score persistence; gunicorn or deploy-config changes; the S-04 end-to-end flow test; provider changes; score-shape/grade changes; watchlist CRUD/privacy changes.

## Architecture / Approach

```
watchlist.index → watchlist.services.scan_watchlist(items, max_workers, per_row_timeout, budget_seconds)
                        │ ThreadPoolExecutor (≤8), one task per item, overall deadline
                        ▼
        fetch_daily_candles(symbol, timeout=per_row_timeout) → score_formation → Row
```

Each task is isolated and closes its own DB connection; results preserve item order; a task past the deadline becomes a "still scanning" row. The template is unchanged.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| ----- | ---------------- | -------- |
| 1. Bound pattern enumeration (F1) | Cheaper H&S/double-top search, no result-shape change | Over-tightening the window could drop a legitimate forming pattern. |
| 2. Bounded-parallel orchestration + view wiring | `scan_watchlist`, timeout seam, settings, thin view | Thread/DB connection hygiene and dev-SQLite write locking; retargeting existing test patches. |
| 3. Offline tests, benchmark & verification | Delay-stub tests, manual cold-list benchmark | Real provider timing varies; budget confirmed manually. |

**Prerequisites:** S-01 and S-02 are done (list surface + detection engine exist); a real `TWELVE_DATA_API_KEY` only for the manual benchmark.
**Estimated effort:** ~2-3 sessions across 3 phases.

## Open Risks & Assumptions

- A cold scan of >8 symbols will still show `rate limited` on the overflow rows — this is accepted, not a defect (NFR-02 permits per-row degradation).
- Dev SQLite may surface `database is locked` on concurrent row writes; acceptable on the dev-only path since each row already degrades to a message.
- The pool overlaps HTTP I/O but not CPU scoring; Phase 1 is required for the budget to hold on choppy lists.
- The 3 s per-row timeout may turn legitimate slow fetches into `unavailable` rows until the next session close.

## Success Criteria (Summary)

- A logged-in user opening `/` sees the whole list scanned and rendered within ~5 s, with flags on formation rows and clear messages for stale/rate-limited/slow rows.
- No cold or slow list produces a 500 or a blanked list.
- Warm lists resolve promptly with no outbound fetch.
