---
project: Stock Guard
version: 1
status: draft
created: 2026-10-08
updated: 2026-10-08
prd_version: 1
main_goal: market-feedback
top_blocker: external
milestone_id: first-flagged-list
milestone_seq: 1
milestone_status: open
---

# Roadmap: Stock Guard

> Derived from `context/foundation/prd.md` (v1) + auto-researched codebase baseline + `tech-stack.md` / `infrastructure.md` / `deploy-plan.md`.
> Edit-in-place; archive when superseded.
> Slices below are listed in dependency order. The "At a glance" table is the index.

## Milestone

**M-1: First flagged list** — Status: open

- **Intent:** Prove the core product hypothesis end-to-end on live market data — a logged-in investor creates their own private watchlist, the app auto-scans it from a free price API, and the investor sees graded bearish-formation flags (double top / RGR) on the positions where a signal is forming. This is the outcome that validates the whole product wedge: deterministic detection from a price series is a usable "consider selling" signal.
- **Source materials:** `context/foundation/prd.md` (v1)
- **Done when:** every F-NN and S-NN below is `done`.
- **Scope anchors:** US-01; FR-001 … FR-010.

## Vision recap

An individual investor managing several to a dozen-plus positions spends time every day manually opening charts and hunting for bearish signals — tedious work where a single signal is easy to miss. Stock Guard's insight is that classic trend-reversal formations (double top, RGR) are deterministically detectable from a price series, so the app can scan the investor's own list and flag the positions worth a closer look, instead of adding yet another chart-and-indicator tool. The product wedge — the one trait that, if removed, makes the app indistinguishable from a generic market-data tool — is that a per-watchlist formation detector turns a raw daily price series into a single graded "consider selling" signal on the investor's own list.

## North star

**S-03: user sees a graded flag on a scanned list** — this is the first end-to-end flow whose success proves the core hypothesis: live daily candles from a free API, run through the detection service, yield a usable graded flag on a real watchlist.

> "North star" here means the smallest end-to-end slice whose successful delivery would prove the core product hypothesis — placed as early as Prerequisites allow, because everything else only matters if this works.

## At a glance

| ID   | Change ID                  | Outcome (user can …)                                                         | Prerequisites    | PRD refs               | Status   |
| ---- | -------------------------- | ---------------------------------------------------------------------------- | ---------------- | ---------------------- | -------- |
| F-01 | account-auth-scaffold      | (foundation) per-account sign-up/login screens live, backed by Django auth  | —                | FR-001, FR-002, Access Control | ready    |
| F-02 | price-data-fetch-boundary  | (foundation) one module fetches a daily-candle series per symbol from a chosen free API, with partial-failure surfacing | —                | FR-008, NFR-04         | blocked  |
| S-01 | own-watchlist-crud         | user can add, view, and remove stocks on their own private list              | F-01             | FR-003, FR-004, FR-006, US-01 | proposed |
| S-02 | formation-detection-service| user sees a graded bearish-formation score rendered per scanned position     | F-01, S-01, F-02 | FR-009, FR-010, US-01  | blocked  |
| S-03 | scan-on-login-flagged-list | user sees their whole list auto-scanned with graded flags after logging in   | S-01, S-02       | FR-007, FR-004, US-01, NFR-01, NFR-02 | blocked  |
| S-04 | end-to-end-flow-test       | (verification) the login → add → scan → flagged-list flow is proven by one test | S-03            | shape-notes Forward: technical-roadmap | proposed |

## Streams

Navigation aid — groups items that share a Prerequisites chain. Canonical ordering still lives in the dependency graph below; this table is the proposed reading order across parallel tracks.

| Stream | Theme                | Chain                          | Note                                                                             |
| ------ | -------------------- | ------------------------------ | -------------------------------------------------------------------------------- |
| A      | Account & list       | `F-01` → `S-01`                | The private-watchlist chain; lands the account gate the persona requires before any scan can be per-user. |
| B      | Live data & detection| `F-02` → `S-02` → `S-03` → `S-04` | Carries the core hypothesis; joins Stream A at `S-02` (detection scores a user's own list). Sequenced to surface the external API blocker early. |

## Baseline

What's already in place in the codebase as of `2026-10-08` (auto-researched + user-confirmed).
Foundations below assume these are present and do NOT re-scaffold them.

- **Frontend:** absent — no templates/views/static app; only Django admin static (`staticfiles/admin/`). No UI framework declared.
- **Backend / API:** partial — Django 6.1 project boots (`stock_guard/settings.py`, `stock_guard/urls.py`); `/health/` and `admin/` only. No feature app, no login view, no root view.
- **Data:** partial — Django ORM + Postgres/SQLite wiring (`stock_guard/settings.py:93`–`107`), `dj-database-url`, built-in migrations applied. No domain models yet.
- **Auth:** partial — `django.contrib.auth` installed and `AuthenticationMiddleware` wired (`stock_guard/settings.py:49`, `:62`); no registration/login views, no per-user watchlist model, no route protection.
- **Deploy / infra:** present — committed `Dockerfile` is the live build path; Railway service healthy at `stock-guard-production.up.railway.app`; GitHub auto-deploy on `main` verified; CI pre-merge gate in `.github/workflows/ci.yml`.
- **Observability:** absent — no logging config, no error tracking, no metrics.

## Foundations

### F-01: Account auth scaffold

- **Outcome:** (foundation) per-account sign-up and login screens are live, backed by Django's auth, so an unauthenticated visitor lands on a login screen and every subsequent view can resolve the current user.
- **Change ID:** account-auth-scaffold
- **PRD refs:** FR-001, FR-002, Access Control (login model; frontend protected; no anonymous access)
- **Unlocks:** S-01 (per-user watchlist needs a current user), S-02, S-03
- **Prerequisites:** —
- **Parallel with:** F-02
- **Blockers:** —
- **Unknowns:** —
- **Risk:** Django ships auth, so this is mostly wiring views/templates and a redirect from `/`; sequenced first because every user-facing slice needs a current user to scope data to. Risk is low.
- **Status:** ready

### F-02: Price-data fetch boundary

- **Outcome:** (foundation) a single service module returns a normalized daily-candle price series for a given ticker from the chosen free API, and reports a per-symbol unavailability error instead of raising — the seam the detection service and the UI both consume.
- **Change ID:** price-data-fetch-boundary
- **PRD refs:** FR-008, NFR-04 (daily candles), NFR-02 (partial-failure degradation)
- **Unlocks:** S-02 (detection needs a price series), S-03 (graceful per-row unavailability)
- **Prerequisites:** —
- **Parallel with:** F-01
- **Blockers:** No free price-data API provider selected yet (FR-008 names the requirement, not the vendor); the alpha-vantage-style free tiers need an API key and have rate limits.
- **Unknowns:**
  - Which free price API provides daily candles for the target tickers, and does its free tier cover the expected per-user call volume? — Owner: user. Block: yes.
  - What ticker symbol format does the chosen API expect (FR-003 accepts free-text ticker + name)? — Owner: user. Block: yes.
- **Risk:** Left as a seam now, not a full layer: it must not complete caching/rate-limit machinery the first consuming slice can add itself. The real risk is provider selection — a poor fit (no daily candles, or a rate limit that breaks a dozen-stock scan) invalidates the north star, so it is surfaced as a blocking unknown rather than buried.
- **Status:** blocked

## Slices

### S-01: user can add, view, and remove stocks on their own private list

- **Outcome:** user can add a stock (ticker + name) to their own list, view the list, and remove a stock from it — and sees only their own list.
- **Change ID:** own-watchlist-crud
- **PRD refs:** FR-003, FR-004, FR-006, US-01
- **Prerequisites:** F-01
- **Parallel with:** —
- **Blockers:** —
- **Unknowns:** —
- **Risk:** Ships the list surface before detection so the north star has an object to scan; FR-005 (update) is deferred as nice-to-have — delete + re-add covers correction. Risk is the ticker-validation gap (FR-003's Socrates note): free-text tickers can silently break the scan, but that is resolved once F-02's symbol format is known, not here.
- **Status:** proposed

### S-02: user sees a graded bearish-formation score rendered per scanned position

- **Outcome:** user sees each watchlist position rendered with a graded bearish-formation score (low / medium / high), computed by a detection service from that position's daily-candle series, rather than a binary flag.
- **Change ID:** formation-detection-service
- **PRD refs:** FR-009, FR-010, US-01
- **Prerequisites:** F-01, S-01, F-02
- **Parallel with:** —
- **Blockers:** — (depends on F-02's provider selection, but that is F-02's blocker, not this slice's)
- **Unknowns:**
  - What exact confidence cut-off separates "forming" from "high-probability forming" (PRD pins the principle, defers the number)? — Owner: user. Block: no.
- **Risk:** This is the core hypothesis made concrete (the detection math). Split from S-03 deliberately so the detection engine and the auto-scan orchestration are planned as separate changes; the threshold unknown is `Block: no` because a defensible default can be tuned after first signal.
- **Status:** blocked

### S-03: user sees their whole list auto-scanned with graded flags after logging in

- **Outcome:** user can log in and, without doing anything else, see their entire watchlist auto-scanned with graded flags on positions showing a forming bearish formation, and a clear per-row message where price data is unavailable — the rest of the list still shows.
- **Change ID:** scan-on-login-flagged-list
- **PRD refs:** FR-007, FR-004, US-01, NFR-01 (responsiveness), NFR-02 (partial-failure degradation)
- **Prerequisites:** S-01, S-02
- **Parallel with:** —
- **Blockers:** —
- **Unknowns:**
  - How is the scan orchestrated so a dozen sequential API calls stay within the "few seconds" responsiveness budget (parallel fetch, short timeout, or progressive render)? — Owner: user. Block: no.
- **Risk:** North star. Sequence last among the user-facing slices because it composes the list (S-01) and the detection service (S-02) into the automatic scan-on-login trigger (FR-007, switched from manual during shaping). Risk is latency: naive per-row fetching could blow the NFR — flagged as a non-blocking unknown to solve during planning.
- **Status:** blocked

### S-04: the login → add → scan → flagged-list flow is proven by one test

- **Outcome:** (verification) one end-to-end test exercises the key user flow — log in, add a stock, trigger/inspect the scan, confirm a flagged list is rendered — so the primary capability is demonstrably reachable.
- **Change ID:** end-to-end-flow-test
- **PRD refs:** shape-notes `## Forward: technical-roadmap` — "the MVP must include at least one test verifying behavior from the user's perspective — the key flow (login → add a stock → scan → flagged list)".
- **Prerequisites:** S-03
- **Parallel with:** —
- **Blockers:** —
- **Unknowns:** — (test framework/tooling chosen during planning, not fixed here)
- **Risk:** The PRD's only explicit verification requirement. Sequenced after S-03 because there is nothing meaningful to assert until the north-star flow exists. Kept as its own slice so the verification path is visible in the backlog rather than implied.
- **Status:** proposed

## Backlog Handoff

| Roadmap ID | Change ID                  | Suggested issue title                                            | Ready for `/10x-plan` | Notes |
| ---------- | -------------------------- | ---------------------------------------------------------------- | --------------------- | ----- |
| F-01       | account-auth-scaffold      | Add per-account sign-up and login screens                        | yes                   | Run `/10x-plan account-auth-scaffold` |
| F-02       | price-data-fetch-boundary  | Add daily-candle price-fetch service boundary                    | no                    | Blocked on free-API provider selection |
| S-01       | own-watchlist-crud         | Add/view/remove stocks on the user's private watchlist           | no                    | Needs F-01 done first (no blockers, just ordering) |
| S-02       | formation-detection-service| Score and render graded bearish-formation signal per position    | no                    | Needs S-01 + F-02; detection math is the core hypothesis |
| S-03       | scan-on-login-flagged-list | Auto-scan the watchlist on login and show graded flags           | no                    | North star; needs S-01 + S-02 |
| S-04       | end-to-end-flow-test       | Add one end-to-end test for login → add → scan → flagged list    | no                    | Needs S-03; PRD's explicit verification requirement |

## Open Roadmap Questions

1. **Which free price-data API backs FR-008 — and does its free tier provide daily candles at a usable rate for a dozen-stock scan?** — Owner: user. Block: F-02, and transitively S-02, S-03, S-04.
2. **What ticker symbol format will the watchlist store, so FR-003's add form validates instead of silently breaking the scan?** — Owner: user. Block: F-02, S-01.

## Parked

- **Position update (FR-005)** — Why parked: PRD demoted it to nice-to-have; delete + re-add covers the correction path in v1.
- **Real-time push / scheduled email alerts** — Why parked: PRD §Non-Goals; scanning is login/view-open only.
- **Portfolio accounting (cost basis, P&L, dividends, sizing)** — Why parked: PRD §Non-Goals; the watchlist is a scan-candidate list, not a holdings tracker.
- **Automated trade execution / broker integration** — Why parked: PRD §Non-Goals; the app only recommends considering a sell.
- **Backtesting against historical data** — Why parked: PRD §Non-Goals; MVP runs on the live daily-candle series only.
- **Soft-delete / deferred removal and scan history** — Why parked: resolved out of scope by FR-006's Socrates clause (hard removal only for v1).

## Milestone History

(Empty — this is the first milestone.)

## Done

(Empty — `/10x-archive` appends entries here as matching changes are archived.)
