# Price Data Fetch Boundary — Plan Brief

> Full plan: `context/changes/price-data-fetch-boundary/plan.md`
> Research: `context/changes/price-data-fetch-boundary/research.md`

## What & Why

Roadmap foundation **F-02** needs one place that turns a ticker into a daily-candle series, so detection (S-02) and scan-on-login (S-03) never touch an external API directly. This plan delivers that seam: `fetch_daily_candles(symbol)` returns a normalized series or a typed per-symbol failure, backed by Twelve Data and a rolling database cache.

## Starting Point

Django 6.1 app with working email/password auth (`accounts`) and nothing else. No HTTP client dependency, no cache configuration, no `marketdata` app, and no price data anywhere. CI installs prod dependencies frozen (`uv sync --frozen --no-dev`) and does not run tests.

## Desired End State

A caller gets `PriceSeries(status="ok")` with up to 500 ascending daily bars, `PriceSeries(status="stale")` when the provider fails but stored bars exist, or `PriceUnavailable(reason=...)` when nothing is stored. One upstream call per symbol per UTC day; every later call that day is served from Postgres. No provider, configuration or parsing problem ever raises into the caller.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Provider | Twelve Data | Only inspected free tier with deep adjusted daily history at a workable quota. | Research |
| Licence posture | Proceed on free tier, document gap | No free tier permits multi-user display; user accepted the gap for the MVP rather than paying now. | Plan |
| Cache shape | `DailyCandle` table, rolling 500 bars | ~6k rows per watchlist, survives deploys, and enables stale fallback during outages. | Plan |
| Provider breadth | Single adapter | Smallest surface; matches F-02's stated outcome. | Plan |
| Price adjustment | `adjust=all` (splits + dividends) | Removes ex-dividend gaps that a detector could misread as formation points. | Plan |
| History depth | ~2 years (`outputsize=500`) | Covers multi-month formations at the same 1-credit cost with a smaller payload. | Plan |
| 429 handling | Surface `rate_limited` to caller | Keeps the boundary fast and single-purpose; pacing belongs to S-03. | Plan |
| Session filtering | Drop today's New York bar | Only completed sessions enter the series, so a window never ends on a partial candle. | Plan |

## Scope

**In scope:** `marketdata` app, `DailyCandle` model + migration, `httpx` dependency, three settings, Twelve Data adapter, fetch service, management command, unit and integration tests.

**Out of scope:** second provider, Redis or retries, detection/scoring, watchlist models, UI, CI test-step wiring, symbol validation at add time, intraday data, scheduled refresh, licence remediation.

## Architecture / Approach

```
caller (S-02 / S-03)
   └─> marketdata.services.fetch_daily_candles   freshness · DB · prune · stale fallback
         └─> marketdata.providers.twelvedata     URL · auth · parse · error mapping
               └─> DailyCandle (Postgres/SQLite)
```

Freshness is "newest `fetched_at` is today in UTC", which avoids a market calendar and caps upstream use at one call per symbol per day. The adapter speaks HTTP and raises `ProviderError`; the service converts it to a result, so callers never handle exceptions.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. App, dependency & schema | `marketdata` app, `httpx`, settings, `DailyCandle` + migration | Frozen lockfile must be regenerated or the image build fails |
| 2. Twelve Data adapter | Request, parse, session filter, error mapping + adapter tests | Provider response shape or error codes differ from docs |
| 3. Fetch service with DB cache | Read-through cache, upsert, prune, stale/unavailable results + tests | Freshness or prune rule is subtly wrong across days |
| 4. Smoke command & verification | `fetch_candles` command and real-key checks | Rate limits or key handling behave differently in practice |

**Prerequisites:** a free Twelve Data API key; `uv` available; network access for `uv lock` and the manual real-key checks.
**Estimated effort:** roughly 2–3 focused sessions across four phases.

## Open Risks & Assumptions

- **Licence gap:** Twelve Data Basic is "internal non-display usage only"; if accounts other than the developer see flags, that is arguably outside the plan. Grow ($29/mo) is the documented escape hatch and needs no code change.
- **Cold-start rate limit:** 12 uncached symbols exceed 8 credits/min, so the first scan of a long list will return `rate_limited` for some rows until the next minute.
- **Adjustment semantics:** Twelve Data documents `adjust=all` as split+dividend but does not describe the exact calculation; values may differ slightly from another vendor.
- **Caching timeframe:** the ToS conditions caching on timeframes "specified in the Documentation", which are not published; the rolling-500 window is a defensible interpretation, not a confirmed entitlement.
- **No retries:** a transient timeout becomes a `stale`/`unavailable` result rather than a second attempt.

## Success Criteria (Summary)

- `uv run python manage.py test marketdata` passes with no network access.
- A real `fetch_candles AAPL` stores ~500 completed daily bars and a second same-day run serves them from the database.
- Provider failures, a missing key and unknown tickers produce clear typed results instead of exceptions.
