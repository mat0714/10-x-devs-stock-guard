# Formation Detection Service Implementation Plan

## Overview

Deliver roadmap slice **S-02** (`formation-detection-service`): a graded bearish-formation engine that turns F-02's daily-candle series into a low/medium/high "consider selling" signal for **double top** and **RGR (head-and-shoulders)**, detecting each formation **while it is still forming** and rendering the grade per watchlist row. This is the product's core hypothesis made concrete; the scan-on-login orchestration and latency budget are deliberately left to S-03.

## Current State Analysis

- The repo has three feature apps: `accounts` (auth), `marketdata` (F-02 price fetch + `DailyCandle`), and `watchlist` (S-01 list). There is no `detection` app and no formation code; `grep` for `score_formation` across tracked `*.py` finds nothing.
- The F-02 seam already exists: `fetch_daily_candles(symbol) -> PriceSeries | PriceUnavailable` (`marketdata/services.py`). `PriceSeries(symbol, candles, status, reason, message)` carries ascending `Candle` rows; `Candle` is a frozen dataclass of `date` + `Decimal` OHLC + `int | None` volume (`marketdata/providers/__init__.py:6-13`). `status` is `"ok"` or `"stale"`; `PriceUnavailable` carries a `reason` (`not_configured`, `rate_limited`, `symbol_not_found`, …).
- `watchlist.index` renders `request.user.watchlist_items.all()` (`watchlist/views.py:12-29`) into `watchlist/templates/watchlist/list.html`, which lists symbol + optional name + a Remove form only. S-01 explicitly deferred price/scan data to S-02/S-03 (`own-watchlist-crud/plan.md:33`).
- `WatchlistItem.symbol` is `CharField(max_length=16)` (`watchlist/models.py:10`), matching `DailyCandle.symbol`, so symbols need no mapping.
- Dependencies are `pyproject.toml:5-12` (django, gunicorn, dj-database-url, whitenoise, psycopg, httpx) with an **empty** `[dependency-groups].dev` (`pyproject.toml:17-18`). `numpy` is **not** present, and neither `pandas` nor `ta` is installed. `uv sync --frozen --no-dev` is used by both CI and the image build (`.github/workflows/ci.yml:20`, `Dockerfile:19`).
- CI runs `check`, `makemigrations --check --dry-run`, `collectstatic`, `check --deploy` — but **no test step** (`.github/workflows/ci.yml`). Tests are `django.test.TestCase` with `test_...Returns...When...` names and hardcoded URL strings (`watchlist/tests.py`).
- Settings expose env-driven values through `os.environ.get(...)` (`stock_guard/settings.py:193-195`); apps are registered by bare label (`stock_guard/settings.py:47-57`).

## Desired End State

A caller can write:

```python
from marketdata.services import fetch_daily_candles, PriceSeries
from detection.services import score_formation

result = fetch_daily_candles("AAPL")
if isinstance(result, PriceSeries):
    score = score_formation(result)
    # FormationScore(pattern="double_top"|"head_shoulders"|"none",
    #                stage="forming"|"confirmed"|"none",
    #                grade="low"|"medium"|"high"|"none",
    #                score=0.0..1.0, evidence=FormationEvidence | None)
```

A logged-in user opens `/` and sees each watchlist row with a graded badge — e.g. `DOUBLE TOP · FORMING · HIGH` — where a bearish formation is detectable, `RGR · CONFIRMED · HIGH` where price has already broken the neckline, a per-row `data unavailable` / `rate limited` style message where the fetch failed, and a `(stale)` marker where the series is served from cache after a provider failure. Rows with no formation and rows whose series is too short to analyse show no badge.

Verification: `uv run python manage.py test detection` and `uv run python manage.py test watchlist` pass; `uv run python manage.py score_symbol AAPL` prints a symbol's grade, stage, score, candle count and pivot/neckline evidence; the list page renders grades in a browser.

### Key Discoveries:

- `fetch_daily_candles` never raises and, with an empty `TWELVE_DATA_API_KEY` and no cached rows, returns `PriceUnavailable(reason="not_configured")` **without any network call** (`marketdata/services.py:62-64`, `:106-110`). This is why the existing `watchlist` list tests keep passing when the view starts calling it — but the new tests must still patch the seam so a developer's exported key cannot trigger live HTTP.
- A confirmed double top / H&S is the *late* case; the early value comes from scoring the still-forming geometry (`research.md` follow-up, Summary 1 and Algorithm sketch step 3). The engine therefore returns a `stage` alongside the grade.
- `Decimal`/`float` boundary: ATR, ZigZag and scoring are numeric-library work, so the engine converts `Decimal` OHLC to `float` once at the service boundary (`research.md` follow-up, step 1). Comparing `Decimal` to `float` directly is not permitted by Python.
- `ta_patterns` and every other inspected library either lag (need future bars), return a binary flag, or lack a graded result; the engine is written in-house on `numpy` (`research.md` follow-up, Libraries table).

## What We're NOT Doing

- No scan-on-login orchestration, parallel/batched fetch, progressive rendering, timeout tuning or latency budget — that is **S-03** (`roadmap.md:131`). S-02 does a straightforward synchronous per-row pass.
- No volume-based confirmation, divergence or any use of `Candle.volume` in v1.
- No chart, sparkline or pivot-annotation rendering — only the grade/stage text badge and the row message.
- No persistence of scores: they are computed per request and never stored (no `detection` model, no migration).
- No patterns beyond double top and RGR.
- No machine learning or parameter optimisation; the detector is a deterministic heuristic with named constants.
- No `mypy`/`ruff` wiring — only the Django test runner is added to CI.
- No change to F-02's fetch service or S-01's model/view contracts beyond adding the score data to the list template.
- No admin registration and no `detection` models.

## Implementation Approach

Create a new `detection` app that owns a pure, DB-free engine. Three small modules, one dependency direction (`detection` → `marketdata` for the `Candle`/`PriceSeries` types):

```
watchlist.index  ──▶  marketdata.services.fetch_daily_candles  ──▶  PriceSeries
       │                                                              │
       └──────────────────────▶  detection.services.score_formation ◀┘
                                          │
                    detection.pivots (ATR + causal ZigZag)
                    detection.patterns (double top / RGR geometry)
```

- **`detection/pivots.py`** — `atr(candles, period)` (average true range over the last `period` bars, or `None` when there are too few bars) and `find_pivots(candles, *, atr_value, deviation)`, a **causal** ZigZag: walk bars forward, track the running extreme, and confirm a swing only once price retraces from it by `deviation × ATR`. The trailing extreme after the last confirmed pivot is returned as an **unconfirmed** pivot, which is what makes early detection possible.
- **`detection/patterns.py`** — `score_double_top(pivots, ...)` and `score_head_shoulders(pivots, ...)`, each returning an internal candidate (`pattern`, `stage`, `sub_score` 0-1, evidence) or `None`.
- **`detection/services.py`** — the public `score_formation(price_series)`, the result dataclasses, the named constants, and the score→grade mapping.

The watchlist view calls F-02 then the engine per row, isolates failures per row, and passes a `rows` list to the template. Thresholds stay code constants; a `score_symbol` management command prints the evidence so they can be tuned by inspection.

## Critical Implementation Details

- **Convert `Decimal` → `float` once, inside `score_formation`.** `Decimal` and `float` do not compare or mix; the engine builds a `float` array from `candle.high/low/close/date` and never passes `Decimal` into numpy.
- **The existing `watchlist` list tests now exercise the fetch path.** With an empty key the fetch returns `not_configured` with no HTTP, so they stay green — but they must be patched with `unittest.mock.patch("watchlist.views.fetch_daily_candles", ...)` so a developer's exported `TWELVE_DATA_API_KEY` cannot make the suite hit the network. New rendering tests patch the same seam.
- **Keep the `items` context variable.** `watchlist/tests.py:79-94` asserts on `response.context["items"]`; the view must keep passing the queryset while adding a parallel `rows` structure the template iterates.
- **Isolate each row.** A failure for one symbol (fetch error, malformed series, an unexpected engine exception) must produce a row message and never raise out of the view — this is the PRD partial-failure NFR (`prd.md:96`).
- **CI installs `--no-dev`.** The test step uses the Django runner (`python manage.py test`), which needs no added dev dependency; do not add `pytest`/`mypy` to make it work.

## Phase 1: Detection app, numpy dependency & pivot primitives

### Overview

Create the `detection` app, add `numpy` to the pinned dependencies, register the app, and implement the numeric primitives (ATR + causal ZigZag). No pattern logic yet.

### Changes Required:

#### 1. New `detection` app

**File**: `detection/` (`__init__.py`, `apps.py`, `pivots.py`, `patterns.py`, `services.py`, `tests.py`, `management/__init__.py`, `management/commands/__init__.py`, `migrations/__init__.py`)

**Intent**: Give the formation engine its own domain app so detection logic stays out of views/templates and can survive a future API/SPA migration (AGENTS.md hard rule; `tech-stack.md:29`).

**Contract**: `detection.apps.DetectionConfig` with `default_auto_field = "django.db.models.BigAutoField"` and `name = "detection"`, mirroring `watchlist/apps.py`. No models in this app; the `migrations/__init__.py` placeholder is still required so Django treats it as an app package.

#### 2. Runtime dependency

**File**: `pyproject.toml`, `uv.lock`

**Intent**: Add the numeric dependency the engine is built on, without pulling in pandas/ta.

**Contract**: add `"numpy>=2.0"` to `[project].dependencies` (`pyproject.toml:5-12`) and regenerate `uv.lock` with `uv lock`. Do not add it to `[dependency-groups].dev`, because CI and the image build install with `--no-dev`.

#### 3. Register the app

**File**: `stock_guard/settings.py`

**Intent**: Make Django discover the app and its management command.

**Contract**: append `"detection"` to `INSTALLED_APPS` after `"watchlist"` (`stock_guard/settings.py:47-57`). No other settings change.

#### 4. ATR and causal ZigZag pivots

**File**: `detection/pivots.py`

**Intent**: Provide the scaled swing-detection primitive that makes early (still-forming) detection possible, plus the ATR it is scaled by.

**Contract**:

- `atr(candles: Sequence[Candle], period: int) -> float | None` — average true range over the last `period` completed bars; `None` when there are fewer than `period + 1` bars.
- `Pivot` frozen dataclass: `index: int`, `date: date`, `price: float`, `kind: str` (`"high"` | `"low"`), `confirmed: bool`.
- `find_pivots(candles: Sequence[Candle], *, atr_value: float, deviation: float) -> list[Pivot]` — walk bars forward; while direction is "up" track the provisional high and confirm it as a `"high"` pivot once price falls by `deviation × atr_value` from it, then switch direction (mirror for lows). The final, not-yet-reversed extreme is appended as a `Pivot(..., confirmed=False)`. Return pivots in chronological order.

Use `numpy` for the true-range/ATR arithmetic; convert `Decimal` fields to `float` locally in this module.

#### 5. Pivot tests

**File**: `detection/tests.py`

**Intent**: Prove the primitives in isolation, including the causality property early detection depends on.

**Contract**: `PivotTests(TestCase)` with `test_...Returns...When...` names and small hand-written candle series built by a local helper. Cases: ATR is `None` below `period + 1` bars and a finite positive value above; a rising-then-falling series yields one confirmed high and one confirmed low in order; a still-rising series ends with a single unconfirmed high pivot; a move smaller than `deviation × ATR` does not confirm a pivot.

### Success Criteria:

#### Automated Verification:

- Detection tests pass: `uv run python manage.py test detection`
- Django system checks pass: `uv run python manage.py check`
- Lockfile is current: `uv lock --check`

#### Manual Verification:

- In `uv run python manage.py shell`, building a short synthetic series and calling `find_pivots` returns the expected confirmed/unconfirmed pivots.

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 2: Formation scoring engine

### Overview

Implement the two pattern scorers, the public `score_formation`, the result types and the named constants, then prove them on synthetic double-top and RGR series.

### Changes Required:

#### 1. Pattern geometry scorers

**File**: `detection/patterns.py`

**Intent**: Turn a pivot sequence into a scored, staged candidate for each pattern, using ATR-scaled tolerances so one parameter set works across price levels.

**Contract**: an internal frozen `Candidate(pattern, stage, sub_score, evidence)` where `pattern` is `"double_top"` / `"head_shoulders"`, `stage` is `"forming"` / `"confirmed"`. `score_double_top(pivots, *, atr_value, tolerance, min_separation) -> Candidate | None` matches a confirmed high, the confirmed trough after it, and either the current unconfirmed high (forming, when within `tolerance` of the first peak and ≥ `min_separation` bars later) or a close below that trough (confirmed). `score_head_shoulders(pivots, *, atr_value, tolerance, min_separation) -> Candidate | None` matches left shoulder, higher head, the second trough, and the current unconfirmed high within `tolerance` of the left-shoulder height (forming) or a close below the trough line (confirmed). Each scorer returns the highest-scoring candidate or `None`; `sub_score` in `[0.0, 1.0]` weights peak/shoulder symmetry, prior-trend size (in ATR), retrace depth, bar separation and neckline slope.

#### 2. Public service, result types and constants

**File**: `detection/services.py`

**Intent**: Expose the single mandated entry point and map candidates to the graded result the UI consumes.

**Contract**:

- Frozen `FormationScore(pattern: str, stage: str, grade: str, score: float, evidence: FormationEvidence | None)` with `pattern` in `{"double_top", "head_shoulders", "none"}`, `stage` in `{"forming", "confirmed", "none"}`, `grade` in `{"low", "medium", "high", "none"}`.
- Frozen `FormationEvidence(pivots: tuple[PivotRef, ...], neckline: float | None)` and `PivotRef(date: date, price: float, kind: str)`.
- `score_formation(price_series: PriceSeries) -> FormationScore` — build the `float` series, compute ATR and pivots, run both scorers, take the better candidate, apply the stage boost, and map to a grade. Returns `FormationScore(pattern="none", stage="none", grade="none", score=0.0, evidence=None)` when there are fewer than `MIN_BARS` candles, when ATR is undefined, or when no candidate matches. Never raises for well-typed input.
- Named module constants (tunable in one place): `ATR_PERIOD = 14`, `PIVOT_DEVIATION = 1.5`, `PEAK_TOLERANCE = 0.03`, `SHOULDER_TOLERANCE = 0.05`, `MIN_PIVOT_SEPARATION = 5`, `MIN_BARS = 60`, `CONFIRMED_BOOST = 0.15`, `GRADE_MEDIUM = 0.45`, `GRADE_HIGH = 0.70`.
- Grade mapping: `none` for no candidate; otherwise `low` below `GRADE_MEDIUM`, `medium` up to `GRADE_HIGH`, `high` at/above it.

The signature and grade thresholds are load-bearing for the UI, so the contract is pinned:

```python
def score_formation(price_series: PriceSeries) -> FormationScore: ...

def _grade(score: float) -> str:
    if score >= GRADE_HIGH:
        return "high"
    if score >= GRADE_MEDIUM:
        return "medium"
    return "low"
```

#### 3. Engine tests

**File**: `detection/tests.py`

**Intent**: Prove both patterns, both stages, the grading and the no-signal paths on deterministic synthetic series.

**Contract**: `ScoreFormationTests(TestCase)` with a local series builder. Cases: a clean two-peak stall yields `pattern="double_top"`, `stage="forming"` and grade `medium`/`high`; a double top that has closed below the trough yields `stage="confirmed"` and grade `high`; a clean left-shoulder/head/right-shoulder series yields `pattern="head_shoulders"`, `stage="forming"`; a steady uptrend with no double top or RGR yields `pattern="none"`/`grade="none"`; a second peak outside `PEAK_TOLERANCE` yields no candidate; a series shorter than `MIN_BARS` yields the all-`none` result; a `status="stale"` `PriceSeries` is still scored (grade not `none` for a forming pattern).

### Success Criteria:

#### Automated Verification:

- Detection tests pass: `uv run python manage.py test detection`
- Django system checks pass: `uv run python manage.py check`

#### Manual Verification:

- In the shell, `score_formation` on a hand-built forming double-top series returns a `forming` grade, and on a confirmed one returns `confirmed`/`high`.

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 3: Watchlist list-page rendering

### Overview

Wire F-02 and the engine into `watchlist.index`, render the grade/stage badge and stale/unavailable messages per row, and cover the rendering with patched tests.

### Changes Required:

#### 1. Score each row in the view

**File**: `watchlist/views.py`

**Intent**: Compute a grade for every row on the list page, degrade per row on failure, and hand the template ready-to-render rows without changing the existing list contract.

**Contract**: in `index`, after building `items`, build `rows` as a list of `Row(item, score, stale, message)` (a small module-level dataclass or plain dict) by calling `fetch_daily_candles(item.symbol)` then `score_formation(result)` for a `PriceSeries`. Wrap each row in `try/except Exception` so an unexpected failure becomes `Row(item, None, message="analysis failed")` instead of a 500. Render with `{"form": form, "items": request.user.watchlist_items.all(), "rows": rows}` — `items` is retained for the existing tests. Import `fetch_daily_candles`, `PriceSeries` from `marketdata.services` and `score_formation` from `detection.services`.

#### 2. Render the badge and row messages

**File**: `watchlist/templates/watchlist/list.html`

**Intent**: Show the graded signal per row, distinguishing forming from confirmed and surfacing data problems, with no chart.

**Contract**: iterate `rows` instead of `items`. Each row keeps the symbol, optional name and Remove form, and adds: when `row.score.pattern != "none"`, a badge showing the pattern label (`Double top` / `RGR`), the stage (`forming` / `confirmed`) and the grade (`low` / `medium` / `high`) with a `grade-<grade>` CSS class; when `row.stale`, a `(stale)` marker next to the badge; when `row.score.pattern == "none"` and no message, nothing; when `row.message`, a muted per-row message. Keep `{{ request.user.email }}` rendered (`watchlist/tests.py:47`, `accounts/tests.py:91`).

#### 3. Badge styles

**File**: `accounts/static/accounts/css/auth.css`

**Intent**: Give the three grades a distinct, legible treatment without adding a stylesheet.

**Contract**: add `.badge` plus `.badge.grade-low` / `.grade-medium` / `.grade-high` and a `.row-message` muted style to the existing stylesheet (reused through `base.html`), matching the file's existing class conventions.

#### 4. Rendering tests, and patch the existing list tests

**File**: `watchlist/tests.py`

**Intent**: Prove the graded/stale/unavailable rendering offline, and keep the existing tests from ever reaching the network.

**Contract**: add `unittest.mock.patch("watchlist.views.fetch_daily_candles")` (and, where useful, `unittest.mock.patch("watchlist.views.score_formation")`) to `setUp` of the existing `AddWatchlistItemTests` / `WatchlistListTests` / `RemoveWatchlistItemTests` so the list path returns a deterministic `PriceUnavailable` or `PriceSeries`. Add a `RowRenderingTests(TestCase)` asserting: a high-grade `FormationScore` renders the grade text; a `stage="confirmed"` score renders the confirmed label; a `PriceSeries(status="stale")` renders the stale marker; a `PriceUnavailable` renders a per-row message and no badge; a no-formation score renders no badge. Method names follow `test_...Returns...When...`.

### Success Criteria:

#### Automated Verification:

- Watchlist test suite passes: `uv run python manage.py test watchlist`
- Existing auth suite still passes: `uv run python manage.py test accounts`
- Django system checks pass: `uv run python manage.py check`
- No migration drift remains: `uv run python manage.py makemigrations --check --dry-run`

#### Manual Verification:

- With a real key, the list page shows a grade badge on a symbol with a visible double top or RGR, no badge on a quiet symbol, and a per-row message when the key is removed mid-session.

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 4: Inspect command, CI test step & verification

### Overview

Add the `score_symbol` command for tuning and debugging, wire the Django test runner into CI, and verify the whole slice end to end.

### Changes Required:

#### 1. `score_symbol` management command

**File**: `detection/management/commands/score_symbol.py`

**Intent**: Give the same hand-inspection surface F-02's `fetch_candles` gave, so thresholds can be tuned and a row's grade explained.

**Contract**: `python manage.py score_symbol SYMBOL` calls `fetch_daily_candles`, prints the fetch `status`, then for a `PriceSeries` prints the candle count, `pattern`, `stage`, `grade`, the raw `score` (3 decimals) and the evidence (each pivot's date/price/kind and the neckline when present); for a `PriceUnavailable` prints the reason and exits 0. `--bars N` is forwarded to `fetch_daily_candles`. Mirrors `marketdata/management/commands/fetch_candles.py`.

#### 2. Command test

**File**: `detection/tests.py`

**Intent**: Prove the command reports a graded result and an unavailable result.

**Contract**: `ScoreSymbolCommandTests(TestCase)` patches the service seam and asserts stdout contains `grade=` with a pattern for the success case, and `reason=` for the `PriceUnavailable` case.

#### 3. CI test step

**File**: `.github/workflows/ci.yml`

**Intent**: Run the test suite — including the detection engine — on push and pull request, since detection is the core hypothesis and the only place a regression would be invisible until production.

**Contract**: add a step after the existing checks running `uv run python manage.py test` (with the same `env` as the `check` step is not required; the runner uses dev defaults). No dev dependency is added; the step uses the Django runner.

### Success Criteria:

#### Automated Verification:

- Full test suite passes: `uv run python manage.py test`
- Django system checks pass: `uv run python manage.py check`
- Static collection still succeeds: `uv run python manage.py collectstatic --noinput`

#### Manual Verification:

- `uv run python manage.py score_symbol AAPL` prints a pattern/stage/grade (or `none`) with evidence and exits 0.
- A push or PR makes the new CI test step run and pass.

---

## Testing Strategy

### Unit Tests:

- Pivots: ATR `None`/finite boundaries; confirmed high+low ordering; unconfirmed trailing pivot on a monotonic series; sub-threshold retrace does not confirm.
- Engine: both patterns, both stages, tolerance rejection, `MIN_BARS` guard, stale-series scoring, no-signal uptrend, grade-threshold boundaries.

### Integration Tests:

- View: fetch seam patched; a graded row renders its badge; a stale row renders its marker; an unavailable row renders a message; an engine failure for one row does not blank the list.
- Command: graded output and unavailable output.

### Manual Testing Steps:

1. `uv lock && uv sync`, then `uv run python manage.py test`.
2. `uv run python manage.py runserver`, log in, and add a symbol with an obvious daily double top or RGR from a charting site.
3. Confirm the row shows `Double top`/`RGR` with a stage and grade; confirm a quiet symbol shows no badge.
4. Run `uv run python manage.py score_symbol <symbol>` and confirm the printed evidence matches the visible formation.
5. Unset `TWELVE_DATA_API_KEY` and reload the list; confirm a per-row message rather than an error page.

## Performance Considerations

- The engine is pure numpy over at most `MARKET_DATA_LOOKBACK_BARS` (default 500) bars per symbol and runs in well under a second; the expensive part of the list page is F-02's per-symbol fetch, which is cache-backed after the first run per session.
- S-02 does a **sequential** per-row fetch+score pass. A cold first scan of a dozen symbols can exceed the PRD's "few seconds" budget (`prd.md:95`) and, on an uncached list, can trip Twelve Data's 8 credits/min limit; the resulting rows render as `rate limited` style messages. Reducing that latency — parallel fetch, progressive render, pre-warm — is explicitly **S-03's** job (`roadmap.md:131`), and this limitation is recorded here rather than solved.
- No database writes and no persistence: the list page adds one F-02 read path (already indexed) plus in-memory scoring per request.

## Migration Notes

- No schema change and no migration: the `detection` app has no models, so `makemigrations --check` stays clean and there is nothing to backfill.
- `uv.lock` must be committed with `numpy`; the frozen install in CI and the image build fails otherwise. The production image grows by numpy's wheel (~15-20 MB), which is acceptable on Railway Hobby.
- No new environment variables. Thresholds are code constants; retuning means a commit and redeploy.
- Dropping the feature later = remove the app, the template additions and the CI step; no data to unwind.

## References

- Research: `context/changes/formation-detection-service/research.md` (codebase contracts; early-detection algorithm; library table)
- Roadmap slice S-02: `context/foundation/roadmap.md:116-129`; S-03 boundary: `context/foundation/roadmap.md:131`
- PRD: FR-009/FR-010 (`context/foundation/prd.md:88-90`), graded example (`:58`), partial-failure NFR (`:96`), daily-candle NFR (`:98`), deferred threshold (`:110`, `:141`)
- F-02 seam: `marketdata/services.py:17-110`, `marketdata/providers/__init__.py:6-13`
- S-01 list surface: `watchlist/views.py:12-29`, `watchlist/templates/watchlist/list.html`, `watchlist/tests.py`
- Conventions to mirror: `watchlist/apps.py` (app config), `marketdata/management/commands/fetch_candles.py` (command), `stock_guard/settings.py:47-57` (app registration), `pyproject.toml:5-12` (deps)
- CI gate: `.github/workflows/ci.yml`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Detection app, numpy dependency & pivot primitives

#### Automated

- [x] 1.1 Detection tests pass
- [x] 1.2 Django system checks pass
- [x] 1.3 Lockfile is current (`uv lock --check`)

#### Manual

- [x] 1.4 `find_pivots` returns expected confirmed/unconfirmed pivots in the shell

### Phase 2: Formation scoring engine

#### Automated

- [ ] 2.1 Detection tests pass
- [ ] 2.2 Django system checks pass

#### Manual

- [ ] 2.3 `score_formation` returns forming and confirmed grades on hand-built series

### Phase 3: Watchlist list-page rendering

#### Automated

- [ ] 3.1 Watchlist test suite passes
- [ ] 3.2 Existing auth suite still passes
- [ ] 3.3 Django system checks pass
- [ ] 3.4 No migration drift remains

#### Manual

- [ ] 3.5 The list page shows a graded badge on a formation, none on a quiet symbol, and a message when the key is removed

### Phase 4: Inspect command, CI test step & verification

#### Automated

- [ ] 4.1 Full test suite passes
- [ ] 4.2 Django system checks pass
- [ ] 4.3 Static collection still succeeds

#### Manual

- [ ] 4.4 `score_symbol AAPL` prints pattern/stage/grade with evidence and exits 0
- [ ] 4.5 The new CI test step runs and passes on push/PR
