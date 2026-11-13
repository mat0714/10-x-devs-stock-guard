# End-to-End Flow Test — Plan Brief

> Full plan: `context/changes/end-to-end-flow-test/plan.md`

## What & Why

Add the PRD's single explicit verification requirement (`shape-notes.md:73`): one test proving the key user flow from the user's perspective — **login → add a stock → scan → flagged list**. The whole product wedge (a per-watchlist formation detector surfacing a graded "consider selling" flag) only counts as proven if that journey is demonstrably reachable in one pass.

## Starting Point

The flow already exists and is fully wired across three landed slices: `POST /login/` redirects to `/` (F-01), `POST /` adds a `WatchlistItem` (S-01), and `GET /` auto-scans via `scan_watchlist` → `fetch_daily_candles` → `score_formation` and renders a graded badge (S-02/S-03). But no test chains the steps — `accounts/tests.py` stops at login, and `watchlist/tests.py` bypasses the login view and stubs both the fetch and the detector. This slice adds no production code; it closes the verification gap.

## Desired End State

One green `TestCase` drives register → login → add → scan → flagged render through the real views and the real detection engine, stubbing only the outbound HTTP price fetch. A reviewer can read it and see the entire chain with a single, obvious seam; CI keeps it green.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Test placement | `EndToEndFlowTests` class in `watchlist/tests.py` | The flow terminates in the watchlist view/route, and CI already discovers this file. | Plan |
| Mock fidelity | Real detection engine; stub only `marketdata.services.twelvedata.fetch_daily` | Exercises the true chain (fetch boundary → detection math → grade → template) with one seam, which is what "proves the flow" means. | Plan |
| Flagged assertion | Pin `badge` + `Double top` label; grade read from engine output | Proves a real formation is surfaced as a visible flag without coupling the test to a specific grade threshold. | Plan |
| Coverage scope | Happy path only | The PRD asks for one test of the named flow; degradation rows stay covered by existing `ScanWatchlistTests`. | Plan |

## Scope

**In scope:** one `TestCase` (plus its local candle-fixture helper and a few imports) in `watchlist/tests.py`; `@override_settings(TWELVE_DATA_API_KEY)` so the fetch boundary reaches the stub; full-suite verification with CI-parity commands.

**Out of scope:** any production change (views, services, models, templates, settings, migrations); new apps/modules/packages/dependencies; `LiveServerTestCase` or JS; degradation-guarantee E2E cases (covered by unit tests); extra privacy assertions; CI workflow edits.

## Architecture / Approach

```
POST /register/  → account (email == username)
POST /login/     → LoginView authenticates → 302 /
POST /           → WatchlistItemForm saves AAPL → 302 /
GET  /           → index → scan_watchlist → _build_row
                     ├─ fetch_daily_candles ─ ─ ─▶ twelvedata.fetch_daily   (STUB: planted 65-bar Candles)
                     │     └─ _store/_load (real, into DailyCandle)
                     └─ score_formation (real engine) → pattern="double_top", grade∈{medium,high}
                   → list.html renders <span class="badge grade-…">Double top · … · …</span>
assert 200 · "AAPL" present · "badge" · "Double top"
```

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. End-to-end flow test | `EndToEndFlowTests` walking the real journey with one stub seam | Fixture must be ≥ 60 bars and the stub must return ascending `Candle`s, or the engine returns no signal / the scan degrades. |
| 2. Full-suite verification | Green suite + `check` + drift check + `collectstatic` (CI parity) | Low — additive test only; any failure signals a genuine regression. |

**Prerequisites:** S-03 landed (it has); a working local env for `uv run python manage.py test`.
**Estimated effort:** one short session — a single test file addition plus a verification run.

## Open Risks & Assumptions

- **Grade fragility is avoided by design**, but if the engine's thresholds change such that the planted series no longer grades `medium`/`high` with `pattern="double_top"`, the label assertion would fail — which is the correct signal that the flow's flag disappeared.
- **Assumes the planted 65-bar double-top leg shape remains detectable**; it is the same shape asserted in `detection/tests.py:246-253`, so a drift there would surface in both suites.
- **Single stub seam assumption:** `fetch_daily_candles` reaches `twelvedata.fetch_daily` only when `TWELVE_DATA_API_KEY` is set and the cache is cold — both hold in a fresh `TestCase` with the override.

## Success Criteria (Summary)

- `uv run python manage.py test` is green, including the new `EndToEndFlowTests`.
- Reading the test shows the full login → add → scan → flagged chain through real code, with exactly one stubbed seam.
- No production file is modified; CI parity commands (`check`, drift check, `collectstatic`) all pass.
