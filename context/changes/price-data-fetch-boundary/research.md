---
date: 2026-10-18T13:53:53+02:00
researcher: mkolodziejczyk@atsi.zab
git_commit: 66ba6bf
branch: main
repository: 10-x-devs-stock-guard
topic: "Which free API should be used to fetch stock price data for the price-data-fetch-boundary slice?"
tags: [research, external-api, market-data, price-fetch, fr-008, f-02, licensing]
status: complete
last_updated: 2026-10-18
last_updated_by: mkolodziejczyk@atsi.zab
---

# Research: Which free stock price API should back F-02 (price-data-fetch-boundary)?

**Date**: 2026-10-18T13:53:53+02:00
**Researcher**: mkolodziejczyk@atsi.zab
**Git Commit**: 66ba6bf
**Branch**: main
**Repository**: 10-x-devs-stock-guard

## Research Question

> I want to do research before price-data-fetch-boundary. I need to research which free API should be used to get stocks price data.

User-confirmed scope (asked and answered during this research, 2026-10-18):

- Ticker universe: **US-listed stocks only**.
- Use/licence posture: **personal, no display rights to third parties** — the app is for the developer and a few fellow investors, no revenue.

This document is research only. It does not approve a plan and does not edit the roadmap. Provider terms were read on the date above; re-check volatile terms before the plan is implemented.

## Summary

The decision is **not** driven by quota. At a dozen symbols per watchlist and a few users, most free tiers are large enough once daily candles are cached. It is driven by three constraints, in order:

1. **Data depth must be "whole history", not "100 bars" or "1 year".** FR-009 requires detecting a double top / RGR *while it is forming*, and a daily-candle pattern spans weeks to months. Alpha Vantage's free tier returns 100 points unless you buy premium (`outputsize=full` and `TIME_SERIES_DAILY_ADJUSTED` are premium-gated), and EODHD's free tier is limited to 1 year of history. Both were verified on the providers' own pages.
2. **The provider's licence must permit the app to exist as a multi-user web app.** Every candidate's current terms limit data use to the individual subscriber's own personal, non-business use. This is a structural conflict with this app's persona (`context/foundation/prd.md:30` describes several investors each with their own account and list).
3. **The access path must survive running on Railway.** Yahoo/yfinance is rejected for a *hosted* app: Yahoo's ToS forbids automated collection (`https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html`, §2.4), and the documented failure mode on datacenter IPs is HTTP 429.

Verified vendor facts (checked 2026-10-18):

| Provider | Free quota | Daily OHLC on free tier | History depth on free | Verdict for this app |
|---|---|---|---|---|
| Twelve Data | 8 credits/min, 800 req/day | Yes (`interval=1day`, split/dividend adjusted, up to 5000 rows/req) | Back to first trading date | **Best technical fit; licence blocks display.** Basic is "internal non-display usage only" |
| FMP | 250 calls/day | Yes (End of Day Historical Data) | 5 years | Quota and depth OK; §2.2.2 forbids multi-user display |
| Massive (ex-Polygon.io) | 5 calls/min, unlimited daily volume | Yes (End of Day, aggregates) | **2 years** | 2-year cap is the tightest usable depth; §2/§1 forbid apps for other end users |
| Alpaca Basic | 200 calls/min | Yes, 1Day bars from IEX | Since 2016 | Batched multi-symbol call is the fastest path; IEX-only on free; no redistribution |
| Tiingo | 1,000 req/day, 50 req/hour, 500 symbols/month | Yes, 30+ years adjusted EOD | 30+ years | **Disqualified**: ToS §1.6(a) forbids persisting free-plan data *and derived products* |
| Tradier | Rate limits unspecified in the public FAQ | Yes (`/markets/history`, interval `daily`) | Lifetime of company | Quota workable; **requires a Tradier brokerage account** |
| Alpha Vantage | 25 req/day | Yes, but unadjusted; adjusted + `full` are premium | **100 points** without premium | **Rejected**: depth too shallow for pattern detection at 25 req/day |
| Finnhub | 60 calls/min | **No** — daily candles are paid | — | **Rejected**: wrong tier |
| EODHD | 20 calls/day | Yes | **1 year** | **Rejected**: depth too shallow for free tier |
| yfinance / Yahoo | No key, no published limit | Yes | Full | **Rejected for hosted use**: ToS forbids automated collection; datacenter 429 risk |

**Recommended direction for `/10x-plan`**: build F-02 behind a provider-agnostic seam (`fetch_daily_candles(symbol) -> series | Unavailable`) with the URL/key/parsing isolated in one adapter, and pick **Twelve Data** as the default adapter implementation — *conditional on the user accepting that the app is effectively a personal app under the provider's "internal non-display" wording, or on accepting a paid tier later.* If the user wants a licence that unambiguously permits several people to see flags, the free tier does not exist and this becomes a paid-plan decision (Twelve Data Grow at $29/mo allows "internal display data access" per its pricing page).

## Detailed Findings

### What the codebase already fixes about this decision

- F-02's outcome is a single module returning a normalized daily-candle series per ticker and reporting per-symbol unavailability instead of raising (`context/foundation/roadmap.md:89`).
- The blocking unknowns are exactly the provider choice and the symbol format (`context/foundation/roadmap.md:96-98`).
- The user-facing scan budget is "within a few seconds" for a dozen stocks (`context/foundation/prd.md:95`), and per-row failure must not blank the list (`context/foundation/prd.md:96`).
- Formation analysis must run on **daily** candles, not intraday (`context/foundation/prd.md:98`).
- The roadmap cites `NFR-04` for the daily-candle requirement (`context/foundation/roadmap.md:91`). **Correction**: `context/foundation/prd.md` has no `NFR-NN` identifiers — the NFR section is an unnumbered bullet list (`context/foundation/prd.md:93-98`), and the daily-candle requirement is the fourth bullet at `:98`. The roadmap label is a convenience, not a PRD anchor. Plans should cite `prd.md:98`, not `NFR-04`.
- No market-data dependency exists in the project today; `pyproject.toml` lists only Django, gunicorn, dj-database-url, whitenoise and psycopg.

### Provider-by-provider evidence

#### Twelve Data — best technical fit, restrictive licence

- Free plan "Basic" is **8 API credits/min with an 800-request/day cap**; the plan table marks markets as "US" (`https://twelvedata.com/pricing.md`, checked 2026-10-18).
- The same page's Feature Highlights label Basic as "internal non-display usage only", and the Individual-vs-Business section states display and distribution are limited to internal personal use; it warns that "using the wrong plan tier may violate the terms of service". The paid **Grow** tier ($29/mo) is the first tier listing "internal display data access".
- `interval=1day` returns daily candles with splits/dividends adjustment, back to the first trading date, up to 5,000 rows per request (`https://support.twelvedata.com/en/articles/5656039-how-to-get-historical-prices`, referenced by the provider's help center; the pricing page itself confirms daily/global EOD on Grow+).
- Consequence for a 12-symbol scan: one uncached scan costs 12 credits, which is **more than the 8 credits/min allowance**, so a naive parallel fetch of 12 symbols trips the per-minute limit. With a per-symbol/per-day cache, 12 symbols cost 12 credits per day, under 2% of the 800/day cap.
- GPW (Warsaw) is not on the free tier; it requires Ultra (out of scope per the confirmed US-only decision).

#### FMP — adequate quota, explicit multi-user prohibition

- Basic is **250 calls/day** and lists "End of Day Historical Data" in its Basic column; the comparison table shows a **5 years** historical range (`https://financialmodelingprep.com/developer/docs/pricing`, checked 2026-10-18).
- Terms §2.2.1: the personal licence is "strictly for their own personal, non-business and non-commercial purposes" and the customer "may not ... integrate the Data or Services into any tools or applications accessible by any third parties".
- Terms §2.2.2: without a specific agreement, customers "are prohibited from showcasing FMP Services or Data on platforms including but not limited to websites, blogs, software products, or applications designed for utilization by multiple individuals".
- 250 calls/day vs 12 symbols is comfortable (~20 uncached scans/day), but the licence clause is the blocker for the PRD's multi-user persona.

#### Massive (formerly Polygon.io) — works technically, shallow 2-year depth

- Free "Stocks Basic" is $0/month with **5 API calls/min, 2 years historical data, End of Day Data, Corporate Actions, Minute Aggregates**, and is labelled "Individual use" (`https://massive.com/pricing`, checked 2026-10-18).
- Individual ToS §2 grants use "solely for your own personal, non-commercial, and non-business purposes" (`https://massive.com/legal/individuals-terms-of-service`).
- Market Data Terms §1 is explicit: "you may not use the Market Data to build an application intended for use by end users other than you" (`https://massive.com/legal/market-data-terms-of-service`). The same section requires a Non-Professional representation.
- 5 calls/min means a 12-symbol uncached scan needs pacing (or cache), and the 2-year cap is the shallowest of the "usable" group but still enough for weekly-scale formations.

#### Alpaca Basic — fastest batch path, IEX-only free feed

- Basic plan: free, US stocks and ETFs, real-time **IEX only**, historical data **since 2016**, **200 historical API calls/min** (`https://docs.alpaca.markets/docs/about-market-data-api`, page updated 2026-10-06; checked 2026-10-18).
- Auth is a key/secret header pair (`APCA-API-KEY-ID`, `APCA-API-SECRET-KEY`) on the same page.
- Licence limits: Alpaca's Terms state use is "solely for your own personal and non-commercial purposes" and that making the services available to others through a User Application requires 30 days' advance written notice (`https://files.alpaca.markets/disclosures/library/TermsAndConditions.pdf`, found via search). Alpaca support states plainly "you cannot redistribute Alpaca API data" (`https://alpaca.markets/support/redistribute-alpaca-api`).
- Free feed is IEX (~2.5% of consolidated volume per the vendor's own framing of Basic vs Algo Trader Plus); acceptable for end-of-day bars, but the OHLCV is IEX-sourced, not consolidated.

#### Tiingo — disqualified by its own terms, despite the best free depth

- Free Starter: **500 unique symbols/month, 50 requests/hour, 1,000 requests/day, 1 GB bandwidth, 30+ years of price history** (`https://www.tiingo.com/blog/best-stock-price-api/`, the provider's own blog, checked 2026-10-18; corroborated by a third-party review at `https://www.quantstart.com/articles/evaluating-data-coverage-with-tiingo/`).
- **Disqualifying clause**, ToS §1.6(a) (last updated 2026-10-06, `https://app.tiingo.com/tos/`): on a Starter plan you "may not write, save, archive, back up, or otherwise retain Tiingo Data in any persistent or durable storage", may process it "only transiently", must remove it "in all events, before the applicable process, job, or user session ends", and "the same limits apply to Derived Products". The clause explicitly lists databases, object stores, logs and backups as covered storage.
- §7.3 adds that "all data via the API is for internal consumption only" and that redistribution requires permission and fees.
- Consequence: Tiingo's apparent advantage (30+ years free) is unusable here, because caching candles across a login session and persisting derived signals would both breach §1.6(a). This finding contradicted a first-pass reading that ranked Tiingo first on quota alone.

#### Tradier — viable quota, brokerage account required

- Historical pricing exists as "daily candles (OCHLV)" and "usually cover[s] the entire lifetime of the company" via `/markets/history` with `interval=daily` (`https://docs.tradier.com/docs/historical-data`, checked 2026-10-18).
- Sandbox data is 15-minute delayed; "real-time data is available to all Tradier Brokerage account holders" (`https://docs.tradier.com/docs/market-data`).
- The public FAQ says API access is not charged to Tradier Brokerage account holders and that rate limits "have proven to be loose enough" — but **no numeric free-tier rate limit is published in the pages inspected** (`https://docs.tradier.com/docs/faq`). Unknown, stated as unknown.
- Licence: "Unless you are a Tradier Partner, Tradier APIs are entitled for personal use only" (same FAQ).
- Onboarding cost is the differentiator: it requires opening a brokerage account, which is a heavier prerequisite than an API-key signup and should be treated as a product decision, not a technical detail.

#### Alpha Vantage — rejected on depth, not just quota

- Free is **25 API requests per day** (`https://www.alphavantage.co/support/` and `https://www.alphavantage.co/premium/`, both checked 2026-10-18).
- The free daily endpoint is **unadjusted**; `TIME_SERIES_DAILY_ADJUSTED` and `outputsize=full` are premium (`https://www.alphavantage.co/documentation/`). Without `full`, `outputsize=compact` yields 100 data points.
- Consequence: 100 daily bars is a hard ceiling on pattern window length, and FR-009's "forming" detection needs a configurable window over a year-plus of history. 12 symbols in one scan already consumes 48% of the daily quota.
- Terms §2.1 grants use "for personal, non-commercial use" and defines commercial use to include providing information to anyone other than the User (`https://www.alphavantage.co/terms_of_service/`).

#### Finnhub and EODHD — rejected on tier/depth

- Finnhub: the free plan's rate limit (60 calls/min) is irrelevant because historical stock candles are a premium feature; the free-tier candle path returns an access error. Primary evidence is Finnhub's own pricing page plus staff replies on `https://github.com/finnhubio/Finnhub-API/issues/546` (reviewed in the first pass; not re-verified line-by-line here, so treat the exact error string as unverified).
- EODHD: Free "Sandbox" is **20 calls/day**, **1 year** of history depth, 20 req/min, with a 500-call welcome bonus (`https://eodhd.com/pricing`, checked 2026-10-18). A 12-symbol scan uses 60% of the daily quota, and 1 year of depth is marginal for multi-month formations.

#### Yahoo / yfinance — rejected for a hosted app

- `yfinance` is actively maintained (latest `1.7.0`, 2026-08-26 per PyPI/GitHub releases; verified in the first pass) and `Ticker.history(interval="1d")` returns adjusted OHLCV by default with `auto_adjust=True`.
- Yahoo Terms of Service §2.4 forbids accessing or collecting data "using any automated means ... including but not limited to robots, spiders, scrapers, data mining tools, or data gathering or extraction tools, for any purpose without our express, prior permission" (`https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html`).
- The libraries' own README states the Yahoo finance API "is intended for personal use only" and disclaims affiliation (`https://github.com/ranaroussi/yfinance`).
- Operationally, datacenter IPs (including cloud hosts such as Railway) are the scenario that produces repeated HTTP 429 reports; this was documented in the first pass from dated GitHub issues and a Stack Overflow report from an AWS Lambda context. The Railway-specific behaviour is **unverified**; the mechanism is not.
- This app renders flags to accounts other than the owner's, so the "personal use only" framing does not survive contact with the PRD persona.

### Cross-cutting finding: the free tier does not match the PRD's persona

`context/foundation/prd.md:30` and `:69-70` describe a multi-user app where several individual investors each keep a private watchlist. Every provider inspected either (a) forbids making the data available to users other than the subscriber, or (b) requires a paid tier for display rights:

- Explicit prohibition of multi-user apps: FMP §2.2.1/§2.2.2, Massive Market Data Terms §1, Alpaca Terms/FAQ.
- Display rights gated behind a paid tier: Twelve Data (Grow, "internal display data access"), Alpha Vantage (commercial/premium contact).
- Storage of free data itself prohibited: Tiingo §1.6(a).

So the honest framing is: **a free licence can support a single-user deployment; it cannot support several accounts seeing flags on one shared API key.** This is a product decision for `/10x-plan` / the user, not something F-02 can code around. Two coherent resolutions exist and both preserve the PRD:

1. Treat the MVP as the developer's personal deployment with accounts disabled or limited to people using their own key (changes the access model).
2. Keep accounts and move to the cheapest tier that grants display rights (Twelve Data Grow at $29/mo), keeping the seam and adapter unchanged — the adapter choice does not have to change if the provider is Twelve Data.

## Symbol format (resolves the second roadmap unknown)

- Twelve Data: plain US tickers (`AAPL`); the symbol parameter is a bare ticker (`https://twelvedata.com/pricing.md` plan scope is US markets).
- FMP / Massive / Alpaca / Tiingo / Tradier: plain US tickers as well (`AAPL`).
- The distinguishing format exception is Tradier's handling of class shares: `BRK.A` must be sent as `BRK/A` (`https://docs.tradier.com/docs/market-data`).
- Practical recommendation for FR-003's add form: store the bare uppercase US ticker and let the adapter own any per-provider rewriting. Do not store provider-specific suffixes, because that couples the watchlist model to the vendor.

## Code References

- `context/foundation/roadmap.md:87-100` — F-02 definition, outcome, blockers, unknowns.
- `context/foundation/roadmap.md:165-168` — open roadmap questions (provider, symbol format).
- `context/foundation/prd.md:86-87` — FR-008 free-API requirement and its Socrates note.
- `context/foundation/prd.md:93-98` — unnumbered NFR list; daily-candle requirement at `:98`.
- `context/foundation/prd.md:30`, `:69-70` — multi-user persona and private watchlists.
- `pyproject.toml` — no market-data dependency yet.

## Architecture Insights

- The provider choice should not leak past the adapter: the service boundary already promises a normalized series plus a per-symbol error, which is exactly the shape that lets one adapter be swapped for another without touching detection or views.
- Caching is a functional requirement, not an optimisation: without a per-symbol/per-day cache, Twelve Data's 8 credits/min forces sequential pacing and blows the "few seconds" budget, and the free daily quotas shrink to a handful of scans.
- Deriving a cached value is the only way to respect both NFR latency and free quotas, **and it is what Tiingo's ToS forbids** — so caching policy must be part of the provider decision, not an implementation afterthought.
- Client library vs plain HTTP: no SDK is needed. One endpoint, JSON in/out, and full control over timeouts matters more than SDK convenience. The official Python SDKs also carry maintenance risk (the Alpha Vantage package's last release predates Python 3.12).

## Historical Context (from prior changes)

- `context/foundation/roadmap.md:95` records the blocker as "No free price-data API provider selected yet (FR-008 names the requirement, not the vendor)" — still true; this research supplies the candidate set and the licence complication.
- `context/foundation/lessons.md:5-10` (verify a platform feature against live docs before writing it into a plan) was applied here: every quota and licence claim was checked against a provider page on 2026-10-18 rather than a roundup, and one widely repeated claim (Tiingo as the best free option) was refuted by Tiingo's own ToS.
- `context/changes/account-auth-scaffold/` contains no market-data decisions; it is unrelated beyond having landed the user accounts that make the multi-user licence question real.

## Related Research

- None yet. `context/changes/price-data-fetch-boundary/` contains only this file after this write; the folder previously existed empty (no `change.md`).

## Open Questions

1. **Licence posture (blocking for the plan, owner: user).** Given that no free tier permits several accounts to see derived flags, does the MVP (a) ship as a personal deployment with the multi-user persona relaxed, or (b) budget for Twelve Data Grow (~$29/mo) or equivalent to keep accounts? F-02's code is identical either way if Twelve Data is the adapter.
2. **Provider fallback depth (non-blocking).** If Twelve Data's per-minute cap is hit despite caching, is a second adapter (Alpaca batch, 200 calls/min) worth building into F-02, or is pacing sufficient? Defer to `/10x-plan`.
3. **Adjusted vs unadjusted prices (non-blocking).** Split/dividend adjustment changes historical highs and lows, which directly affects double-top and RGR detection. The chosen data should be adjusted; the detection service must state which convention it assumes.
4. **Tradier's numeric rate limit** is unpublished in the pages inspected — unknown, not verified.

## Verification notes

- `NFR-04` cited in the roadmap does not exist as an identifier in the PRD; the underlying requirement is the fourth NFR bullet (`context/foundation/prd.md:98`).
- Provider terms and quotas are point-in-time facts (2026-10-18) and several are subject to change at the provider's discretion. Alpha Vantage, Twelve Data, Massive, FMP, Alpaca and Tiingo all reserve the right to change limits; EODHD and Tradier publish theirs in plan tables.
- First-pass findings that were **superseded** by direct verification: Tiingo ranked first (refuted by ToS §1.6(a)); Twelve Data ranked as a viable default (true technically, but the licence label "internal non-display usage only" narrows it); a claim that Stooq is keyless and covers GPW (out of scope after the US-only decision, and the keyless path is reported closed by `pydata/pandas-datareader#1012`, not independently re-verified here).
