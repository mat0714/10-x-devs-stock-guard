# Price Data Fetch Boundary Implementation Plan

## Overview

Deliver roadmap foundation **F-02** (`price-data-fetch-boundary`): one service module, `fetch_daily_candles(symbol)`, that returns a normalized daily-candle series for a US ticker from Twelve Data, caches a rolling two-year window in the database, and reports a typed per-symbol failure instead of raising. This is the seam that S-02 (detection) and S-03 (scan-on-login) consume.

The provider choice and its licence caveat come from `context/changes/price-data-fetch-boundary/research.md`. The short version: Twelve Data Basic is the only inspected free tier that returns deep adjusted daily history at a workable quota, but its Basic plan is labelled "internal non-display usage only". The user accepted that gap for the MVP and it is recorded here as a launch-time risk, not solved by code.

## Current State Analysis

- The project is a Django 6.1.1 scaffold with one feature app, `accounts`. `stock_guard/settings.py:47-55` registers apps by bare label; `stock_guard/urls.py:27-31` mounts `/health/`, `/admin/` and `accounts.urls`.
- There is **no HTTP client dependency**. `pyproject.toml:5-11` lists Django, gunicorn, dj-database-url, whitenoise and psycopg only; `uv.lock` contains no `httpx`, `requests`, `urllib3` or `certifi` even transitively.
- Both CI and the image build install prod deps frozen: `Dockerfile:19` and `.github/workflows/ci.yml:20` run `uv sync --frozen --no-dev`. A new runtime dependency therefore requires `[project].dependencies` plus a regenerated `uv.lock`.
- No `CACHES`, no `LOGGING`, and no Redis service are configured (`stock_guard/settings.py`); the deploy docs provision only the app and Postgres (`context/deployment/deploy-plan.md:160-163`, `:236`). The container filesystem is ephemeral (`context/foundation/infrastructure.md:92`).
- The Gunicorn `CMD` sets no `--workers` (`Dockerfile:27`), so the default single sync worker runs. Per-process memory caches would still be lost on every restart.
- Settings read env vars with `os.environ.get(...)` and branch on presence, e.g. `DATABASE_URL` at `stock_guard/settings.py:98` and `EMAIL_HOST` at `:169`. There is no mandatory-env (`os.environ[...]`) pattern.
- Tests are plain Django `TestCase` in `<app>/tests.py` with method names like `test_xReturnsYWhenZ` (`accounts/tests.py:8`, `:116`). No mocking or HTTP-stubbing precedent exists. CI does not run tests.
- `makemigrations --check --dry-run` and `migrate` are already part of the local/dev workflow; Railway's `preDeployCommand` runs `migrate --noinput` (`context/deployment/deploy-plan.md:184`).

Verified provider facts (2026-10-18, see research doc):

- `GET https://api.twelvedata.com/time_series` with `interval=1day`, `outputsize` capped at 5000, `order` default `desc`, `adjust` default `splits`.
- `/time_series` costs **1 credit per symbol** regardless of row count; Basic allows **8 credits/min and 800/day**, resets at 00:00 UTC.
- Errors are `{"code": int, "message": str, "status": "error"}` with 401 (bad key), 404 (unknown symbol), 429 (credit exhaustion), 500.
- ToS permits storing data for Internal Use and creating non-reversible Derived Data; caching is conditioned on "permitted timeframes specified in the Documentation", which are not published.

## Desired End State

A caller can write `from marketdata.services import fetch_daily_candles` and receive either a `PriceSeries` (`status="ok"` or `"stale"`) with ascending daily candles, or a `PriceUnavailable` carrying a stable `reason`. The first call for a symbol after each completed New York session hits Twelve Data, stores up to 500 bars, prunes older ones, and every later call before the next close is served from Postgres without a network request. When Twelve Data fails but stored bars exist, the result is `stale` with the failure reason; when nothing is stored, it is `unavailable`. The function never raises for provider, configuration or data problems.

Verification: `uv run python manage.py test marketdata` passes, `uv run python manage.py migrate` creates `marketdata_dailycandle`, and `uv run python manage.py fetch_candles AAPL` prints 500 bars of status `ok` and a second run before the next session close prints `cached`.

### Key Discoveries:

- `bulk_create(update_conflicts=True, unique_fields=[...], update_fields=[...])` is available (`django/db/models/query.py:780`) and SQLite 3.46.1 supports it, so the upsert works on both dev SQLite and prod Postgres with one code path.
- `auto_now=True` is **not** applied by `bulk_create`, so `fetched_at` must be a plain `DateTimeField` written explicitly by the service.
- A `UniqueConstraint(fields=["symbol", "date"])` already creates the index used by "newest 500 for symbol" queries; a separate index would duplicate it.
- Twelve Data returns OHLCV as strings and newest-first by default; `order=asc` changes ordering but parsing still validates and sorts defensively.
- `outputsize=500` costs the same 1 credit as `outputsize=5000`, so lookback length is a payload/latency choice, not a quota choice.

## What We're NOT Doing

- No second provider adapter and no fallback provider (user decision: single adapter).
- No Redis, no distributed cache, no retry/backoff queue, and no internal pacing or sleeping on 429 — the caller sees `rate_limited`.
- No detection, scoring, watchlist models, views, templates or UI (S-01/S-02/S-03).
- No scheduled refresh, cron job, Celery task or background worker.
- No `/symbol_search` validation of tickers at add time (that belongs to S-01) and no provider-specific symbol rewriting.
- No intraday, real-time or quote endpoints; daily bars only.
- No CI test-step wiring; the existing CI gate is unchanged, matching `account-auth-scaffold`'s precedent.
- No resolution of the Twelve Data display-licence gap; it is documented as a launch-time risk.

## Implementation Approach

Create a new `marketdata` app that owns the model, the provider adapter and the service. The service is the only public entry point; the adapter is an implementation detail that speaks HTTP and raises a typed `ProviderError`, which the service converts into a result object.

Three layers, one direction of dependency:

```
caller (future S-02/S-03)
        │
        ▼
marketdata.services.fetch_daily_candles   ← freshness, DB read/write, prune, stale fallback
        │
        ▼
marketdata.providers.twelvedata.fetch_daily  ← URL, auth, parsing, HTTP→reason mapping
```

The cache freshness rule is calendar-light: a symbol is fresh when its newest `fetched_at` is at or after the most recent completed New York session close. That means one upstream fetch per symbol per completed session while users keep scanning, which is 12 credits/day for a 12-symbol list against an 800/day cap (at most one extra refetch per symbol on a UTC day when the first call precedes the close). The current New York session is dropped at parse time only while it is incomplete, so the stored series contains only completed daily bars.

**Licence constraint (recorded, not solved):** Twelve Data's Basic plan is "internal non-display usage only", and no inspected free tier permits several accounts to see derived flags. Proceeding on Basic is a conscious MVP decision. Switching to Grow ($29/mo) later changes only `TWELVE_DATA_API_KEY` and the plan on the account — no code change.

**Scope deviation (recorded):** `context/foundation/roadmap.md:99` tells F-02 not to complete caching machinery, but `research.md:167` shows caching is a functional requirement here: without a per-symbol cache the 8 credits/min limit forces pacing and breaks the few-seconds scan budget. This plan therefore owns the `DailyCandle` cache and prune, and the roadmap's F-02 note is updated to match.

## Critical Implementation Details

- **Freshness is keyed to the newest `fetched_at`, compared against the last completed New York session close.** Using the candle date would refetch all weekend and holiday requests; using a short TTL would multiply credit use. "Fresh" means `max(fetched_at) >= last_completed_close(now)`: the most recent weekday 16:00 ET whose close has passed, converted to UTC (weekends fall back to Friday). Evening calls after the close refetch once to pick up that session; morning calls reuse the prior close's data.
- **Only the in-progress New York session is dropped.** Before 16:00 ET, drop bars dated today in America/New_York; at or after 16:00 ET, keep today's completed bar and drop only future dates. That keeps a detection window from ending on a half-formed candle without hiding a session that has already closed.
- **`bulk_create` bypasses `auto_now`.** Set `fetched_at` explicitly to one `timezone.now()` value shared by every row in the batch.
- **Prune by the effective lookback's Nth-newest date, not by "delete older than two years".** The contract is a rolling bar count (`bars`, default `MARKET_DATA_LOOKBACK_BARS`), which stays correct across market closures and holidays and stays consistent with a `--bars` override.

## Phase 1: App, dependency & schema

### Overview

Create the `marketdata` app, add the HTTP client dependency, add the three settings, and land the `DailyCandle` model with its migration. No network code yet.

### Changes Required:

#### 1. New `marketdata` app

**File**: `marketdata/` (`__init__.py`, `apps.py`, `models.py`, `admin.py`, `migrations/__init__.py`, `tests.py`)

**Intent**: Create the app that owns price fetching and its storage, keeping it separate from `accounts` and from the future detection service.

**Contract**: `marketdata.apps.MarketDataConfig` with `default_auto_field = "django.db.models.BigAutoField"` and `name = "marketdata"`; register `"marketdata"` in `INSTALLED_APPS` next to `"accounts"`.

#### 2. Runtime dependency

**File**: `pyproject.toml`, `uv.lock`

**Intent**: Add the HTTP client used by the adapter without pulling in an SDK.

**Contract**: add `"httpx>=0.28.1"` to `[project].dependencies` (current PyPI release 0.28.1) and regenerate `uv.lock` with `uv lock`. Do not add it to `[dependency-groups].dev`, because CI and the image install with `--no-dev`.

#### 3. Settings

**File**: `stock_guard/settings.py`

**Intent**: Expose the key, lookback and timeout as env-driven settings using the existing `.get()` convention, so local dev, CI and Railway need no settings-module split.

**Contract**: append three module-level settings:

```python
TWELVE_DATA_API_KEY = os.environ.get("TWELVE_DATA_API_KEY", "")
MARKET_DATA_LOOKBACK_BARS = int(os.environ.get("MARKET_DATA_LOOKBACK_BARS", "500"))
MARKET_DATA_HTTP_TIMEOUT = float(os.environ.get("MARKET_DATA_HTTP_TIMEOUT", "10"))
```

#### 4. `DailyCandle` model and migration

**File**: `marketdata/models.py`, `marketdata/migrations/0001_initial.py`

**Intent**: Store a deduplicated rolling window of completed daily bars, keyed by symbol and trading date, so repeat scans between session closes need no network call.

**Contract**: `DailyCandle` fields: `symbol` (`CharField(max_length=16)`), `date` (`DateField`), `open`/`high`/`low`/`close` (`DecimalField(max_digits=18, decimal_places=6)`), `volume` (`BigIntegerField(null=True)`), `fetched_at` (`DateTimeField()`, no `auto_now`). `Meta.constraints` contains `UniqueConstraint(fields=["symbol", "date"], name="uniq_daily_candle_symbol_date")`; no extra index, because the constraint already supplies it. `__str__` returns `f"{symbol} {date}"`.

### Success Criteria:

#### Automated Verification:

- Lockfile is current: `uv lock --check`
- Django system checks pass: `uv run python manage.py check`
- No migration drift remains: `uv run python manage.py makemigrations --check --dry-run`
- Migration applies locally: `uv run python manage.py migrate`
- Static collection still succeeds: `uv run python manage.py collectstatic --noinput`

#### Manual Verification:

- `marketdata_dailycandle` exists in `db.sqlite3` with the unique `(symbol, date)` constraint visible in `uv run python manage.py sqlmigrate marketdata 0001`.

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 2: Twelve Data adapter

### Overview

Implement the single provider adapter that builds the request, parses the payload into `Decimal` candles, and translates every failure into a typed reason. No database involvement in this phase.

### Changes Required:

#### 1. Provider error and candle types

**File**: `marketdata/providers/__init__.py`

**Intent**: Give the service a provider-independent vocabulary for candles and failures so the adapter can raise and the service can convert.

**Contract**: a frozen `Candle` dataclass with `date: date`, `open/high/low/close: Decimal`, `volume: int | None`; and `ProviderError(reason: str, message: str)` where `reason` is one of `auth_failed`, `symbol_not_found`, `rate_limited`, `provider_error`, `invalid_response`, `no_data`. `not_configured` is produced by the service, not the provider.

#### 2. Twelve Data request and parse

**File**: `marketdata/providers/twelvedata.py`

**Intent**: Fetch up to N daily bars for one symbol and return them ascending, with only completed sessions, or raise `ProviderError`.

**Contract**: `fetch_daily(symbol: str, *, bars: int, timeout: float, api_key: str, transport: httpx.BaseTransport | None = None, now_ny: datetime | None = None) -> list[Candle]`. Builds `GET https://api.twelvedata.com/time_series` with params `symbol`, `interval=1day`, `outputsize=bars`, `order=asc`, `adjust=all`, and header `Authorization: apikey <key>` (the key must not appear in the URL or in log lines). When `transport` is supplied, construct `httpx.Client(transport=transport, timeout=timeout)`; otherwise construct a plain client. Parse `payload["values"]` into `Candle`, `date.fromisoformat(value["datetime"])`, and `Decimal` for the four prices; a missing/blank `volume` becomes `None`. Sort ascending by date and drop the current New York bar only while it is incomplete: when `now_ny` (default `datetime.now(ZoneInfo("America/New_York"))`) is before 16:00 ET drop `date >= now_ny.date()`, otherwise drop `date > now_ny.date()`. Map a body with `status == "error"` or a `code` field to the reason by code: 401/403 → `auth_failed`, 404 → `symbol_not_found`, 429 → `rate_limited`, 400 and any other 4xx → `provider_error`, 5xx/other → `provider_error`; JSON decode errors and structurally invalid values → `invalid_response`; an empty `values` array → `no_data`. Network timeouts and connection errors → `provider_error`. No retries.

#### 3. Adapter tests

**File**: `marketdata/tests.py`

**Intent**: Prove parsing, ordering, session filtering and error mapping without any network access.

**Contract**: `TwelveDataAdapterTests(TestCase)` using `httpx.MockTransport` handlers that assert the outgoing query params and auth header. Cases: ascending order with `Decimal` prices and integer volume; newest-first input is re-sorted ascending; a bar dated today in New York is dropped before 16:00 ET and retained after 16:00 ET; `volume` absent yields `None`; each of 400/401/403/404/429/500 maps to the documented reason; an `httpx.ConnectError`/timeout raises `provider_error`; a non-JSON body raises `invalid_response`; an empty `values` list raises `no_data`. Method names follow `test_fetchReturns...When...`.

### Success Criteria:

#### Automated Verification:

- Adapter tests pass: `uv run python manage.py test marketdata.tests.TwelveDataAdapterTests`
- Django system checks pass: `uv run python manage.py check`

#### Manual Verification:

- One real request against a free key for `AAPL` returns 500 ascending daily bars whose last close matches the provider's own displayed close for the last completed session.

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 3: Fetch service with DB cache

### Overview

Implement `fetch_daily_candles`, the single public entry point: read-through cache, upsert, rolling prune, and the `stale`/`unavailable` fallback that keeps provider failures out of the caller's exception path.

### Changes Required:

#### 1. Result types and service

**File**: `marketdata/services.py`

**Intent**: Turn per-symbol fetching into a total function that always returns a result and never raises for provider, config or data problems.

**Contract**: frozen dataclasses `PriceSeries(symbol: str, candles: tuple[Candle, ...], status: str, reason: str | None = None, message: str = "")` with `status` in `{"ok", "stale"}`, and `PriceUnavailable(symbol: str, reason: str, message: str = "")`; `FetchResult = PriceSeries | PriceUnavailable`. Public function `fetch_daily_candles(symbol: str, *, bars: int | None = None) -> FetchResult`, where `bars` defaults to `settings.MARKET_DATA_LOOKBACK_BARS` and is the effective window for both the provider request and the prune:
- Normalize the symbol with `strip().upper()`; empty input returns `PriceUnavailable(reason="invalid_symbol")`.
- Read `max(fetched_at)` for the symbol. If it is at or after `_last_completed_close(timezone.now())` (most recent weekday 16:00 ET already passed, converted to UTC), return stored candles as `PriceSeries(status="ok", reason="cached")` without any HTTP call.
- Otherwise call `twelvedata.fetch_daily(...)` with `bars`, `settings.MARKET_DATA_HTTP_TIMEOUT` and `settings.TWELVE_DATA_API_KEY`. An empty key skips the call and produces `not_configured`.
- On success, upsert and prune to `bars` inside `transaction.atomic()`, then return the stored series as `PriceSeries(status="ok")`.
- On `ProviderError` or an empty key, load any stored candles: if present return `PriceSeries(status="stale", reason=<reason>, message=<message>)`, otherwise `PriceUnavailable(reason=<reason>, message=<message>)`.
- Log one `warning` per failed fetch with symbol and reason, never the key or the raw URL.

#### 2. Persistence helpers

**File**: `marketdata/services.py`

**Intent**: Keep upsert and prune in one place, with one `fetched_at` per batch.

**Contract**: `_store(symbol, candles, fetched_at, lookback)` uses `bulk_create(..., update_conflicts=True, unique_fields=["symbol", "date"], update_fields=["open", "high", "low", "close", "volume", "fetched_at"])` and then, when the symbol has more than `lookback` rows, deletes every row older than the `lookback`-th newest date (keep exactly the newest `lookback` dates). `_load(symbol)` returns ascending `Candle` tuples ordered by `date`.

#### 3. Service tests

**File**: `marketdata/tests.py`

**Intent**: Prove the cache, upsert, prune and fallback behaviour without touching the network.

**Contract**: `FetchServiceTests(TestCase)` patching `marketdata.services.twelvedata.fetch_daily` and `django.utils.timezone.now`. Cases: rows fetched after the last completed close are served without calling the provider; rows fetched before the last close trigger exactly one refetch even on the same UTC day; no rows triggers one provider call and stores them; a previous-session cache triggers a refetch; overlapping dates update in place and leave row count unchanged; 520 fetched bars with `bars=500` leave exactly 500 stored and keep the newest; `bars=200` leaves exactly 200 stored; a provider failure with stored rows returns `stale` carrying the reason; a provider failure with no rows returns `unavailable`; an empty API key with no rows returns `not_configured`; an empty key with rows returns `stale`; an empty or whitespace symbol returns `invalid_symbol` without a provider call; the function returns a result rather than raising for every mapped reason.

### Success Criteria:

#### Automated Verification:

- Service tests pass: `uv run python manage.py test marketdata.tests.FetchServiceTests`
- Full app suite passes: `uv run python manage.py test marketdata`
- Migration drift check is clean: `uv run python manage.py makemigrations --check --dry-run`
- Django system checks pass: `uv run python manage.py check`

#### Manual Verification:

- With a real key, fetch `AAPL` twice in a row; the second call returns `status="ok"`, `reason="cached"`, and makes no outbound request before the next session close (confirm by removing the key between calls and still getting `ok`).

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 4: Smoke command & verification

### Overview

Add the management command that makes the boundary testable by hand and gives S-03 a debugging surface, then verify the whole boundary against the real provider.

### Changes Required:

#### 1. `fetch_candles` management command

**File**: `marketdata/management/__init__.py`, `marketdata/management/commands/__init__.py`, `marketdata/management/commands/fetch_candles.py`

**Intent**: Fetch one symbol from the command line, print the result status and the stored date range, and exit non-zero only for an unexpected exception.

**Contract**: `python manage.py fetch_candles SYMBOL` calls `fetch_daily_candles`, prints `status`, `reason` when present, candle count, first and last date, and stored row count. `--bars N` is passed as `fetch_daily_candles(..., bars=N)` and therefore also sets the prune window for that run. `unavailable` prints a clear line and exits 0, because unavailability is a normal result.

#### 2. Command test

**File**: `marketdata/tests.py`

**Intent**: Prove the command reports both a successful and an unavailable result.

**Contract**: `FetchCandlesCommandTests(TestCase)` patches the service and asserts stdout contains `status=ok` with a count, and `status=unavailable reason=symbol_not_found` for the failure case.

### Success Criteria:

#### Automated Verification:

- Full suite passes: `uv run python manage.py test marketdata`
- Django system checks pass: `uv run python manage.py check`

#### Manual Verification:

- `uv run python manage.py fetch_candles AAPL` prints about 500 stored bars and an `ok` status.
- A second run before the next session close prints `cached` and the same date range.
- `uv run python manage.py fetch_candles NOTAREALTICKER` prints `symbol_not_found` and exits 0.
- With `TWELVE_DATA_API_KEY` unset, a symbol with no stored rows prints `not_configured`, and a symbol with stored rows prints `stale`.

---

## Testing Strategy

### Unit Tests:

- Adapter: ordering, session filtering, `Decimal` parsing, absent volume, every documented error code, malformed JSON, empty values.
- Service: freshness by last completed session, provider called at most once per session, upsert idempotence, prune to the effective lookback, stale vs unavailable fallback, empty-key behaviour, symbol normalization.

### Integration Tests:

- Service + real ORM against the test database: first fetch populates 500 rows, a second fetch before the next session close adds none, and a simulated previous-session cache triggers exactly one provider call. The provider is stubbed at the `twelvedata.fetch_daily` seam, so no network is used in CI or locally.

### Manual Testing Steps:

1. `uv lock && uv sync`, set `TWELVE_DATA_API_KEY`, then `uv run python manage.py migrate`.
2. `uv run python manage.py fetch_candles MSFT` and confirm an `ok` status with ~500 bars and a plausible date range.
3. Re-run immediately and confirm `cached` with identical dates.
4. Run with an invalid ticker and confirm `symbol_not_found`, not a traceback.
5. Unset the key and confirm `not_configured` for an unfetched symbol and `stale` for a fetched one.

## Performance Considerations

- One HTTP call per symbol per completed session. A 12-symbol watchlist costs 12 credits/day against the 800/day cap, plus at most one refetch per symbol on days when the first call precedes the close; a **cold** 12-symbol scan spends 12 credits against the 8/min limit. F-02 surfaces `rate_limited`; S-03 decides whether to stagger, cache pre-warm or reduce parallelism.
- `outputsize=500` keeps each payload at roughly 500 rows instead of up to 5,000, with no credit difference.
- The read path is a `MAX(fetched_at)` plus one indexed `(symbol, date)` range read; the write path is one bulk upsert plus one delete. Both are negligible at ~6,000 rows per watchlist.
- The HTTP timeout defaults to 10 seconds so one slow symbol cannot hold a caller indefinitely.

## Migration Notes

- One new table and one migration; `marketdata_dailycandle` is created by the existing `preDeployCommand` (`migrate --noinput`) on Railway, so no deploy-plan change is needed.
- `uv.lock` must be committed with `httpx`; a frozen install fails the build otherwise.
- No data migration, no backfill, and no changes to `accounts` tables. Dropping the feature later means dropping the table.
- Railway needs a new `TWELVE_DATA_API_KEY` variable. Its absence is not fatal: the service returns `not_configured`/`stale` rather than crashing, which matches the PRD's partial-failure guardrail.

## References

- Research: `context/changes/price-data-fetch-boundary/research.md`
- Roadmap F-02: `context/foundation/roadmap.md:87-100`
- PRD FR-008 and the daily-candle NFR: `context/foundation/prd.md:86-87`, `:98`
- PRD partial-failure and latency guardrails: `context/foundation/prd.md:95-96`
- Settings conventions: `stock_guard/settings.py:98`, `:169`
- App conventions: `accounts/apps.py:4-6`, `stock_guard/settings.py:54`
- Test conventions: `accounts/tests.py:8`, `:116`
- Twelve Data `/time_series`: `https://twelvedata.com/docs/market-data/time-series`
- Twelve Data errors: `https://twelvedata.com/docs/introduction/errors`
- Twelve Data credits: `https://support.twelvedata.com/en/articles/5615854-credits`
- Twelve Data terms: `https://twelvedata.com/terms`
- Twelve Data pricing: `https://twelvedata.com/pricing.md`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: App, dependency & schema

#### Automated

- [x] 1.1 Lockfile is current (`uv lock --check`) — dfeca81
- [x] 1.2 Django system checks pass — dfeca81
- [x] 1.3 No migration drift remains — dfeca81
- [x] 1.4 Migration applies locally — dfeca81
- [x] 1.5 Static collection still succeeds — dfeca81

#### Manual

- [x] 1.6 `marketdata_dailycandle` exists with the unique `(symbol, date)` constraint — dfeca81

### Phase 2: Twelve Data adapter

#### Automated

- [x] 2.1 Adapter tests pass
- [x] 2.2 Django system checks pass

#### Manual

- [x] 2.3 A real AAPL request returns ~500 ascending bars matching the provider's last completed close

### Phase 3: Fetch service with DB cache

#### Automated

- [ ] 3.1 Service tests pass
- [ ] 3.2 Full app suite passes
- [ ] 3.3 Migration drift check is clean
- [ ] 3.4 Django system checks pass

#### Manual

- [ ] 3.5 Second fetch before the next NY close returns `cached` with no outbound request

### Phase 4: Smoke command & verification

#### Automated

- [ ] 4.1 Full suite passes
- [ ] 4.2 Django system checks pass

#### Manual

- [ ] 4.3 `fetch_candles AAPL` prints ~500 bars with status `ok`
- [ ] 4.4 A second run before the next session close prints `cached` with the same date range
- [ ] 4.5 An invalid ticker prints `symbol_not_found` and exits 0
- [ ] 4.6 An unset key prints `not_configured` for an unfetched symbol and `stale` for a fetched one
