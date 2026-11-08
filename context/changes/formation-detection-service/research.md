---
date: 2026-11-08T12:14:30+01:00
researcher: Mateusz Kołodziejczyk
git_commit: 5dd56babaaafff05f4922cd21175b24e5f00fdd5
branch: main
repository: 10-x-devs-stock-guard
topic: "What does the codebase already fix for formation-detection-service (S-02), and what must the plan decide?"
tags: [research, codebase, formation-detection, score_formation, marketdata, watchlist]
status: complete
last_updated: 2026-11-08
last_updated_by: Mateusz Kołodziejczyk
last_updated_note: "Follow-up: early-detection algorithm and library selection (external research)"
---

# Research: formation-detection-service (S-02) — existing contracts, integration points, open decisions

**Date**: 2026-11-08T12:14:30+01:00
**Git Commit**: 5dd56babaaafff05f4922cd21175b24e5f00fdd5 (branch `main`; working tree had only this change folder untracked)

## Research Question

No question text was supplied beyond the change-id `formation-detection-service`. The question was derived from `change.md` (empty notes) and roadmap slice S-02: what do the PRD, roadmap, tech-stack and existing code already fix for a detection service that scores a daily-candle series, and what is left for `/10x-plan` to decide?

## Summary

- **Contract is fixed in name only.** `score_formation(price_series)` is the mandated service entry point (`AGENTS.md` Hard rules; `context/foundation/tech-stack.md:29`). No code for it exists: in the inspected tree (all tracked non-`.ai`/non-archive files) `grep` for `score_formation` finds hits only in docs, none in `*.py`.
- **Input type already exists.** F-02 delivers `PriceSeries(symbol, candles: tuple[Candle,...], status, reason, message)` or `PriceUnavailable` (`marketdata/services.py:17-32`); candles are ascending by date, `Decimal` OHLC, `volume: int | None` (`marketdata/providers/__init__.py:6-13`, `marketdata/services.py:152-171`).
- **Output shape is only partly fixed.** Graded low / medium / high (`roadmap.md:118`, `prd.md:58`), not binary (FR-010, `prd.md:90`); both double top and RGR in scope (`prd.md:139`); detection of in-progress formations, not only completed ones (FR-009, `prd.md:88`).
- **Not fixed (plan must decide):** the numeric threshold(s) (PRD defers it, `prd.md:141`; roadmap marks it `Block: no`, `roadmap.md:127`), the algorithm itself, the result type, the window length, the rendering surface for S-02, and dependency/tooling choices.
- **Rendering scope ambiguity.** S-02's outcome says the user "sees each watchlist position rendered with a graded score" (`roadmap.md:118`), but S-03 owns scan-on-login orchestration and the unavailable-row message (`roadmap.md:131`). The boundary between "S-02 renders a score" and "S-03 triggers scan on login" is not spelled out.

## Detailed Findings

### Product rules binding the service

- FR-009: detect double top or RGR while forming, "when there is a high probability it will complete" (`context/foundation/prd.md:88`); the Socrates note warns of false positives on half-formed patterns (`prd.md:89`).
- FR-010: graded strength, not binary (`prd.md:90`); US-01 example grades low / medium / high (`prd.md:58`).
- Business Logic: graded output per watchlist entry; "one threshold separates 'forming' from 'high-probability forming'" (`prd.md:102-110`). So at least one cut-off is required by the PRD; the number is downstream.
- NFR: daily candles only (`prd.md:98`); per-row failure must not blank the list (`prd.md:96`).
- Roadmap S-02 prerequisites F-01, S-01, F-02 (`roadmap.md:121`); unknown: confidence cut-off, owner user, non-blocking (`roadmap.md:126-127`). Roadmap status for S-02 is still `blocked` (`roadmap.md:129`) although its prerequisites are in the tree (below); status table not re-verified against the plans' completion state.

### Stack and conventions

- Detection must live in a service module, not in views/templates (`AGENTS.md`; `tech-stack.md:29`). Type hints at service boundaries are required (`AGENTS.md` Coding style).
- `tech-stack.md:29` says Python was chosen for "pandas + ta"; neither is a dependency today. `pyproject.toml:5-12` lists django, gunicorn, dj-database-url, whitenoise, psycopg, httpx only; `[dependency-groups] dev = []` (`pyproject.toml:17-18`) and no mypy/ruff/pytest config exists there. `uv pip list` in this environment showed no pandas/numpy/scipy/ta. Whether to add pandas (or implement in pure Python on `Decimal`/`float`) is an open choice; the CI step runs `uv sync --frozen --no-dev` (`.github/workflows/ci.yml:20-21`) and runs no tests and no mypy, so tests are not CI-enforced today (this inspected workflow only).
- Tests convention: Django `TestCase` in each app's `tests.py`; marketdata tests are named `test_<subject>Returns...When...` (`marketdata/tests.py:60,317`).

### Upstream data (F-02, implemented)

- `fetch_daily_candles(symbol, *, bars=None) -> FetchResult` never raises per its docstring; returns `PriceSeries` with `status` `"ok"` or `"stale"` (stale carries `reason`), or `PriceUnavailable(symbol, reason, message)` (`marketdata/services.py:35-110`).
- Window: rolling bar count `MARKET_DATA_LOOKBACK_BARS`, default 500 (`stock_guard/settings.py:194`); the F-02 plan describes it as "a rolling two-year window" yet implements a bar count (`price-data-fetch-boundary/plan.md:5,79`) — 500 daily bars is roughly 2 years of trading days (inference, ~252 sessions/year).
- The in-progress NY session is dropped at the adapter so a detection window does not end on a half-formed candle (`price-data-fetch-boundary/plan.md:77`; adapter tests `marketdata/tests.py:105,114`).
- A series can be shorter than the lookback or contain gaps (malformed rows skipped, `marketdata/tests.py:241`); `score_formation` must define a minimum-bars behavior. A `stale` series is still scoreable; whether the UI should signal staleness is undecided.
- `Decimal` prices mean any numeric library path needs a float conversion decision.

### Integration point (S-01, implemented)

- `watchlist.index` renders `request.user.watchlist_items.all()` into `watchlist/list.html` with no price or scan data (`watchlist/views.py:12-29`); template lists `item.symbol`, name and a Remove form only (`watchlist/templates/watchlist/list.html:18-27`). S-01 explicitly deferred "per-row price/scan data, no formation detection" to S-02/S-03 (`own-watchlist-crud/plan.md:33`).
- `WatchlistItem.symbol` is `CharField(max_length=16)`, same length as `DailyCandle.symbol` (`watchlist/models.py:10`, `marketdata/models.py:5`), so keys align without mapping.
- Privacy NFR (`prd.md:97`): scoring is per-symbol and stateless, so it cannot leak across accounts as long as the caller scopes items by `request.user` (as `watchlist/views.py:29` does); persistence of scores, if chosen, would need user scoping — currently no model for scores exists.

## Code References

- `marketdata/services.py:17-32` - `PriceSeries`, `PriceUnavailable`, `FetchResult`
- `marketdata/services.py:35-110` - `fetch_daily_candles` (ok / cached / stale / unavailable)
- `marketdata/providers/__init__.py:6-13` - `Candle` dataclass (Decimal OHLC, optional volume)
- `stock_guard/settings.py:193-195` - market-data settings (lookback 500)
- `watchlist/views.py:12-29` - view that would consume scores; `watchlist/templates/watchlist/list.html:18-27` - row markup
- `pyproject.toml:5-18` - dependencies; no pandas/ta, no dev tooling
- `.github/workflows/ci.yml` - no test or mypy step

## Architecture Insights

- Established pattern: per-app service module returning frozen dataclasses, with typed failure values rather than exceptions (`marketdata/services.py`). A `score_formation` result type following the same style fits the repo; a new app (e.g. `detection/`) mirrors the `marketdata`/`watchlist` split used by earlier plans, which each created a dedicated domain app.
- Pure-function detection (candles in, score out, no DB) keeps it unit-testable without fixtures and matches the "survives an SPA migration" rationale (`tech-stack.md:29`).

## Historical Context (from prior changes)

- `context/changes/price-data-fetch-boundary/plan.md:5` - F-02 names S-02/S-03 as consumers of `fetch_daily_candles`.
- `context/changes/own-watchlist-crud/plan.md:33` - S-01 leaves scan data to S-02/S-03.
- `context/changes/price-data-fetch-boundary/research.md` - provider choice (Twelve Data); its licence caveat (Basic is "internal non-display") touches S-02/S-03 because they display derived signals; not re-verified here (the research was dated 2026-10-18).
- `context/foundation/lessons.md` - existing lessons concern deploy/infra only; none apply to detection logic.

## Related Research

- `context/changes/price-data-fetch-boundary/research.md` (provider selection).

## Open Questions

1. **Algorithm and scoring definition** (user/plan): pivot detection method, tolerance between the two peaks, neckline and head/shoulder symmetry rules, how "forming" confidence maps to 0–1 and to low/medium/high. No existing code or doc specifies these.
2. **Cut-off values**: PRD defers the number (`prd.md:141`); plan should pin a default and make it a named constant/setting for tuning.
3. **Minimum bars / window**: how many of the (up to 500) bars to analyze, and result for too-short series.
4. **Result type**: dataclass with `grade`, `score`, `formation` (double_top / rgr / none) and evidence (pivot dates/prices) for later chart rendering — not specified anywhere; FR-010 only requires a graded indication.
5. **S-02 vs S-03 boundary**: does S-02 include a view/template change and on-request scoring via `fetch_daily_candles`, leaving auto-scan-on-login and latency handling to S-03? Roadmap wording is ambiguous.
6. **Dependencies**: pandas/ta versus pure Python; adding dev tooling (mypy) is mentioned in `AGENTS.md` but not wired.
7. **Test data**: no historical fixtures exist for formations; synthetic series would have to be built, and real-world calibration is out of evidence here.
8. **Roadmap status**: S-02 shows `blocked` (`roadmap.md:129`) while F-02 and S-01 plans/code exist; confirm before planning.

---

# Follow-up (2026-11-08): best algorithm for early detection, and which libraries

**Question**: "What is the best way/algorithm to detect the formation — it is very important that it is detected at an early stage — and which libraries should be used?"

External sources checked 2026-11-08: PyPI JSON metadata, scipy 1.18 `find_peaks` docs, the `ta_patterns` PyPI README and `docs/concepts.md`, GitHub READMEs of `chart_patterns`, `TradingPatternScanner`, and a BitPredict H&S notebook. Library behavior below was not executed; nothing was installed.

## Follow-up Summary

1. **Early detection is a pivot-lag problem, not a library problem.** Standard peak finders confirm a swing only after bars exist on its right: scipy's `find_peaks` defines a peak as a sample whose two direct neighbours are smaller (scipy docs, Notes) and so needs future bars; `ta_patterns` states a pivot at bar t is flagged only at `t + pivot_n` (`docs/concepts.md`, "Pivots, confirmation delay"). A detector built on them is late by construction. Its default `mode="confirmed"` fires on a close below the intervening valley (neckline), the point after most of the move; its `forming` mode fires "at the second peak" (same doc).
2. **Recommended approach (inference from the sources, not a measured result): a causal, volatility-scaled ZigZag pivot tracker that keeps the *current provisional leg* as a first-class input, plus a rule-based geometry scorer that emits graded confidence per stage.** Early flagging comes from scoring the *incomplete* pattern (second top or right shoulder still being formed), not from waiting for the neckline break.
3. **Libraries: use `numpy` only for the core (optionally `scipy.signal` for offline calibration); write the detector in-house.** No inspected package gives graded, early, explainable output for both patterns with a maintained, typed, permissively licensed footprint (table below).

## Algorithm sketch (proposal for the plan, not an existing artifact)

All steps operate on daily bars from F-02, ascending, converted from `Decimal` to `float` at the service boundary (decision for plan; see open questions).

1. **Scale**: compute ATR(14) (or % true-range) in numpy; express every tolerance in ATR/percent units so one parameter set works across low- and high-priced tickers.
2. **Causal ZigZag**: walk bars forward; a swing high becomes *confirmed* only when price retraces by `k × ATR` (or `d %`) from it, and symmetrically for lows. Retain the *provisional extreme* since the last confirmed pivot. This is the same deviation-based approach as the PyPI `zigzag` package, but written causally so the live leg is exposed (`zigzag` is a Cython package, last release 2022-08-06, requires Cython `<0.30` per its metadata; not suitable as a dependency).
3. **Stage detection** over the last N pivots plus the provisional leg:
   - *Double top*, stage "forming": prior advance into peak 1 (min size in ATR units); confirmed peak 1 and confirmed trough T (retrace depth in range); the *current provisional high* lies within `tol` of peak 1 (candidate peak 2) and is ≥ min bars after peak 1; price has stalled or rolled over (rejection: close well below the bar high, or first lower close below the provisional high). Stage "confirmed" = close below T (neckline) — report it, but it is the late case.
   - *RGR (head and shoulders)*, stage "forming": confirmed left shoulder, head higher than it, trough 2, and the provisional high after the head is below the head and within `tol` of the left shoulder height (candidate right shoulder). Neckline = line through the two troughs; stage "confirmed" = close below it.
4. **Score** each candidate 0–1 as a weighted sum of bounded sub-scores: peak/shoulder symmetry, prior-trend strength, retrace depth vs ATR, time separation, rejection evidence on the current leg, neckline slope sanity, and (optional, volume present as `int | None`) volume divergence. Add a stage multiplier so a "forming" pattern can reach medium/high only with strong geometry; a "confirmed" pattern scores higher.
5. **Grade**: map the best of the two patterns' scores to low / medium / high via two named constants (the "forming vs high-probability forming" cut-off the PRD requires, `prd.md:110`). Return the pattern name, stage, score and the pivot evidence (dates/prices, neckline) for later charting.
6. **Calibrate offline**: replay the detector on stored history bar-by-bar (point-in-time, prefix slices) and measure, per grade, how often a flagged "forming" pattern later breaks the neckline within M bars versus not. `scipy.signal.find_peaks(prominence=…)` and `argrelextrema` are suited to this hindsight labelling step because lag does not matter there.

Trade-off to state explicitly in the plan: an earlier flag necessarily trades precision for lead time (`prd.md:89` already warns of false positives on half-formed patterns). The graded output and the stage field are the mechanism that handles that trade-off; there is no evidence in this repo or the sources inspected that quantifies the precision at each stage.

## Libraries evaluated (PyPI metadata checked 2026-11-08)

| Package | Version / last release | Python | Fit for this app |
|---|---|---|---|
| `numpy` | 2.5.4 / 2026-10-10 | >=3.12 | **Use.** Sufficient for ATR, ZigZag and scoring on <=500 bars per symbol (`settings.py:194`). Matches `requires-python >=3.12` (`pyproject.toml`). |
| `scipy` | 1.18.1 / 2026-08-21 | >=3.12 | **Optional / dev-calibration.** `find_peaks` offers prominence/distance filters but is non-causal (see Summary 1). Adds a large dependency for little runtime value. |
| `pandas` | 3.1.1 / 2026-11-04 | >=3.11 | **Optional.** Named in `tech-stack.md:29`, but the core needs no DataFrame; adds weight to the production image. If used, only for convenience at the boundary. |
| `ta` | 0.11.0 / 2023-11-02 | unspecified | **Avoid.** Last release is ~3 years old; indicators only (no pattern detection); pandas 3 compatibility not verified here. ATR is a few numpy lines. |
| `TA-Lib` | 0.8.3 / 2026-10-28 | >=3.9 | **Avoid.** Candlestick patterns only, not double top/RGR geometry (inference from its pattern scope, not re-verified this session); wraps a C library, which complicates the `Dockerfile` build. |
| `pandas-ta` | 0.4.71b0 / 2025-09-14 | >=3.12 | **Avoid.** Pre-release (beta) indicator library; no formation detection. |
| `ta-patterns` | 1.2.1 / 2026-09-22 (PyPI page excerpt lists four releases, 2026-06-09 to 2026-09-22; older ones, if any, not seen) | >=3.10 | **Reference only.** MIT, numpy-only, point-in-time-safe, has `double_top(..., mode="forming")` and `hs_top`, but returns signed `int8` (-1/0/+1), not a graded score or evidence; young (the four releases seen span about 3 months); it flags on the completing bar in `confirmed` mode. Useful to cross-check your detector's output, not as the scoring engine. |
| `chart_patterns` (GitHub only) | not on PyPI per its README ("clone the repo") | n/a | **Avoid.** Install by cloning; DataFrame-based; no point-in-time guarantee documented in the README excerpt. |
| `tradingpattern` | 2023-04-06 (PyPI page date) | >=3.10 | **Avoid.** Window-based, README itself warns small windows raise false positives; small, stale. |
| `zigzag` | 0.3.2 / 2022-08-06 | >=3.8 | **Avoid as dependency** (Cython `<0.30` pin); good conceptual reference for step 2. |
| `trendln`, `pytrendline`, `patternpy` | 2026-04-09 / 2021-06-09 / no release date | various | Not evaluated beyond metadata; none advertises graded early double-top/RGR scoring. |

Judgment on reuse: popularity/maintenance signals for the pattern-specific packages are weak (young or stale), and none returns the evidence (pivots, neckline) needed to chart or explain a grade; therefore build in-house on numpy. This weakens the earlier assumption in `tech-stack.md:29` ("pandas + ta") — that assumption is not supported by the metadata above for `ta`.

## Implications for the plan

- Settled by evidence: causality matters more than library choice; the service must expose the provisional leg and a stage.
- Genuine choices for the user: `float` vs `Decimal` math; pure numpy vs also adding pandas; tolerance defaults (`k × ATR`, `tol`, min separation); whether "confirmed" patterns are also shown (recommended: yes, as the top grade).
- Missing evidence: no labelled formation dataset, no measured false-positive rate for early stages; a calibration/replay harness (step 6) would produce that evidence and should be a plan phase or follow-up.
- Dependency housekeeping: dev tooling (mypy/ruff/tests) is still absent from `pyproject.toml`; adding numpy is a `uv lock` change per `AGENTS.md`.

## Follow-up Open Questions

1. Which ATR multiple / percent deviation defines a confirmed pivot on daily US-equity data? Unmeasured here.
2. Minimum bars between the two tops / shoulders, and the peak-similarity tolerance (the PRD pins none).
3. Should a stale `PriceSeries` (`status="stale"`) be scored and flagged as stale, or suppressed?
4. Is volume (nullable, `Candle.volume`) used at all in the first version?
