# Formation Detection Service — Plan Brief

> Full plan: `context/changes/formation-detection-service/plan.md`
> Research: `context/changes/formation-detection-service/research.md`

## What & Why

Build the graded bearish-formation engine that is the product's core hypothesis: turn a stock's daily-candle series into a low/medium/high "consider selling" signal for **double top** and **RGR (head-and-shoulders)**, and show it on the watchlist. The explicit priority is **early** detection — flagging a pattern while it is still forming, not after the neckline already broke.

## Starting Point

F-02 already delivers `fetch_daily_candles(symbol)` returning a `PriceSeries` of ascending daily candles (`marketdata/services.py`). S-01 already renders the private watchlist at `/` with no price or signal data (`watchlist/views.py:12-29`). There is no detection code, no `numpy`, and CI runs no tests. S-02 is the slice that adds the math and shows the grade; the automatic scan-on-login flow is S-03.

## Desired End State

Opening `/` shows each watchlist row with a graded badge — e.g. `Double top · forming · High` or `RGR · confirmed · High` — a per-row message where price data is unavailable, a `(stale)` marker when the cached series is being used, and no badge on rows with no formation. A `score_symbol` command prints the same signal with its pivot/neckline evidence for tuning.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Slice boundary | Service + render on the list page; S-03 owns orchestration/latency | Matches S-02's "rendered per position" outcome | Plan |
| Detection approach | In-house causal ZigZag + geometry on numpy | Only approach inspected that flags a still-forming pattern with a graded, explainable result | Research + Plan |
| Dependencies | Add numpy; wire the Django test runner into CI | numpy is the only runtime need; the test step guards the core hypothesis | Plan |
| Grade model | Three levels (low/medium/high) plus a backing 0-1 score | Matches the PRD's low/medium/high example while keeping a score for tuning | Plan |
| Confirmed patterns | Report both; result carries a `stage` (forming / confirmed) | Serves the early priority without hiding a formation that completed between scans | Plan |
| Stale / unavailable rows | Score stale series but mark them; message-only when unavailable | Honours the PRD partial-failure NFR | Plan |
| Thresholds | Named constants + a `score_symbol` inspect command | Tune by inspection without env/schema churn | Plan |

## Scope

**In scope:** `detection` app; numpy; ATR + causal ZigZag pivots; double-top and RGR geometry scorers; `score_formation` with grades and stages; list-page badge rendering; stale/unavailable row handling; `score_symbol` command; CI test step.

**Out of scope:** scan-on-login orchestration, parallelism and latency budget (S-03); volume-based confirmation; charts/pivot annotation; persisting scores; extra patterns; ML/optimisation; mypy/ruff wiring; changes to F-02's fetch service or S-01's model.

## Architecture / Approach

A new `detection` app with a pure, DB-free engine. `detection/pivots.py` computes ATR and a causal ZigZag whose trailing extreme stays unconfirmed — that is what enables early detection. `detection/patterns.py` scores double-top and RGR geometry on those pivots, ATR-scaled so one parameter set works across price levels. `detection/services.py` exposes `score_formation(price_series) -> FormationScore(pattern, stage, grade, score, evidence)`. The watchlist view calls F-02 then the engine per row, isolates failures per row, and the template renders the badge.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Detection app, numpy & pivot primitives | `detection` app, numpy dep, ATR + causal ZigZag | Getting the causal (unconfirmed-trailing) pivot right |
| 2. Formation scoring engine | `score_formation` for double top + RGR, stages, grades | Threshold defaults need later calibration |
| 3. Watchlist list-page rendering | Graded badge + stale/unavailable rows | Existing list tests must be patched off the network |
| 4. Inspect command, CI test step & verification | `score_symbol` command, CI test step, E2E check | CI step must run under `--no-dev` |

**Prerequisites:** F-02 (`fetch_daily_candles`) and S-01 (watchlist) shipped — both present in the tree; `numpy` addable via `uv lock`.
**Estimated effort:** ~2-3 sessions across 4 phases.

## Open Risks & Assumptions

- A sequential per-row fetch on a cold list can exceed the "few seconds" budget and may hit Twelve Data's 8 credits/min limit; rows render a message and S-03 owns the fix.
- Threshold defaults (`PIVOT_DEVIATION`, `PEAK_TOLERANCE`, grade cut-offs, `MIN_BARS`) are unmeasured heuristics chosen from the research, not calibrated against labelled data; the `score_symbol` command is the tuning surface.
- Early flags trade precision for lead time (the PRD already warns of half-formed false positives); the stage field and grades are the mitigation.

## Success Criteria (Summary)

- Both double top and RGR are flagged while forming, with a low/medium/high grade and a distinguishing stage.
- A logged-in user sees the grade on their watchlist, with graceful per-row messages for stale or unavailable data.
- The detection engine and its rendering are covered by tests that now run in CI.
