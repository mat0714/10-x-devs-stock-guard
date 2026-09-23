---
project: Stock Guard
version: 1
status: draft
created: 2026-09-20
context_type: greenfield
product_type: web-app
target_scale:
  users: small
  qps: low
  data_volume: small
timeline_budget:
  mvp_weeks: 3
  after_hours_only: true
  hard_deadline: null
---

## Vision & Problem Statement

Manually checking one's own stock portfolio every day is time-consuming: each title requires opening a chart and looking for bearish signals (formations, indicators). An individual investor managing their own portfolio spends time they'd rather spend on other things — and a single signal is easy to miss, because analyzing conflicting data is tedious.

The insight that makes this project worthwhile: classic trend-reversal formations (double top, RGR) are deterministically detectable from a price series — they don't require human judgment in the MVP variant, where we limit ourselves to a single signal type. The status quo of technical-analysis tools focuses on charts and indicators, but doesn't combine them into a single, simple rule of "whether to consider selling here" on one's own list.

> Scale insight (Step 6 Socrates): at 100x the user base, signal quality — not the rule itself — becomes the pressure point: a broader range of stocks and edge cases would demand more patterns and tuning. The per-watchlist formation-detection rule stays unchanged; scaling changes the *coverage and calibration* of the heuristic, not its shape.

## User & Persona

### Primary persona

**Marek**, an individual stock-market investor managing his own portfolio of several to a dozen-plus stocks. He has a basic grasp of technical analysis (knows the concepts of RSI, channel, and simple formations) but doesn't want to manually check the chart of every position every day. He knows which signals to look for, but needs to look for them quickly and systematically — so he wants the app to scan his list and graphically show positions with a bearish formation. He opens the app after logging in, triggers a check, and reviews the flagged positions. Some fellow investors are at the same stage — they want separate accounts with separate lists.

## Success Criteria

### Primary

1. After logging in, the user can add stocks to their own list, trigger a scan, and see a graphical flag on positions whose price series contains a bearish formation (double top or RGR). This flow from login to flagged list works end-to-end.

### Secondary

- No additional nice-to-haves — the MVP focuses on the Primary.

### Guardrails

- Missing price data from the API for a given stock does not break the entire session: the user sees a clear message about unavailability for that position, and the rest of the list still scans.
- The watchlist remains private: a user never sees another user's list or signals.
- The scan returns results within a reasonable time that the user perceives as responsive — missing data or an API error does not hang the interface indefinitely.

## User Stories

### US-01: User sees flagged bearish formations after logging in

- **Given** a logged-in user with at least one stock on their own list
- **When** the app automatically scans the list after login (or when the list view is opened)
- **Then** the user sees their stock list with graphical flags on positions whose price series indicates a bearish formation in progress (double top or RGR), and positions without a formation without a flag

#### Acceptance Criteria

- Positions are graphically marked with the degree of bearish-signal strength (e.g., low / medium / high probability of formation), not just binary.
- If price data for a stock is unavailable, the user sees a clear message about the unavailability of that position — the rest of the list is not blocked by it.
- The user sees only their own stocks and their own signals — they do not see another user's data.

## Functional Requirements

### Authentication / Accounts

- FR-001: The user can register an account (email + password). Priority: must-have
  > Socrates: Counter-argument considered: registration may over-reach for an MVP where users are flat / a local single-account would suffice. Resolution: kept must-have — multi-user (several individual investors, each with own watchlist) is the confirmed primary persona, so per-account registration is load-bearing.
- FR-002: The user can log in to their account. Priority: must-have
  > Socrates: Counter-argument considered: the watchlist is private and price data is public, so a password gate may add friction without protecting anything meaningful. Resolution: kept must-have — multi-user with private watchlists requires account separation; a single-user local mode would drop the confirmed persona scope.

### Watchlist management (CRUD)

- FR-003: The user can add a stock to their list (e.g., ticker + name). Priority: must-have
  > Socrates: Counter-argument considered: free-text tickers invite typos/fake symbols that silently break the scan. Resolution: kept must-have — the MVP needs an add primitive; ticker normalization/validation can be clarified in downstream planning.
- FR-004: The user can view their list of stocks. Priority: must-have
  > Socrates: Counter-argument considered: a bare unsorted view adds no decision value over a raw table and silently imports scan-result persistence. Resolution: kept must-have — viewing is the precondition for scan/update/delete flows and is the surface where the bullish/bearish signal is surfaced (FR-010).
- FR-005: The user can update a position on their list (e.g., change name/ticker). Priority: nice-to-have
  > Socrates: Counter-argument considered: update is over-modeled — the user could delete the bad entry and add the correct one, so a distinct update path isn't load-bearing for the MVP. Resolution: demoted to nice-to-have; delete + re-add covers the correction path in v1.
- FR-006: The user can remove a stock from their list. Priority: must-have
  > Socrates: Counter-argument considered: a watchlist of a dozen stocks rarely needs hard removal, and deferred/partial removal variants would preserve cleanup context. Resolution: kept must-have — removal is the core list-management capability; the user performs hard removal (takes the stock off the list outright), and deferred-removal variants and scan history are out of scope for the MVP.

### Scanning and formation detection

- FR-007: The app automatically scans the user's stock list after login (or when the list view is opened). Priority: must-have
  > Socrates: Counter-argument considered: user-triggered scan requires the investor to remember to press scan, risking missed sell signals on days they forget. Resolution: switched to automatic scan-on-login (user-confirmed) — updates the previously manual Step 3 flow; user no longer triggers scan explicitly.
- FR-008: The app fetches price data from a free API for each stock on the list. Priority: must-have
  > Socrates: Counter-argument considered: binding to a free API now bakes in rate limits/data-gaps/ToS constraints, and mocked fixtures could prove the detection logic in a 3-week MVP. Resolution: kept must-have — live price data is the confirmed dependency (free API per the idea description); the MVP's whole value is real-market signal, not synthetic fixtures.
- FR-009: The app detects a bearish formation (double top or RGR) while it is forming, when there is a high probability it will complete — not only after full formation. Priority: must-have
  > Socrates: Counter-argument considered: probabilistic detection before confirmation risks a false-positive machine that pushes the investor to sell on half-formed patterns that never complete; likewise, shipping both double-top AND RGR in MVP scope may stretch the 3-week timeline. Resolution: kept must-have — detecting formations-in-progress is the core insight that makes this product non-trivial; pattern scope resolved by the user — ship detection for both double top and RGR in the MVP; the precise probability threshold remains a downstream decision captured as an Open Question, not a reason to demote the capability.
- FR-010: The app displays the stock list with a graphical indication of bearish-signal strength — not just binary (yes/no), but in a way that lets the investor judge the probability of formation for each position. Priority: must-have
  > Socrates: Counter-argument considered: a binary detected/not-detected flag is too coarse — the investor loses the probability/strength needed to act. Resolution: reframed to richer signal per user confirmation — the flag conveys signal strength/confidence, not just presence; this couples the scan output to a graded score, consistent with FR-009's probabilistic detection logic.

## Non-Functional Requirements

- Scan latency feels responsive: for a small watchlist (a dozen stocks), the user sees the full list with scan results within a few seconds of login/view open, even when one entry's price data is slow or unavailable.
- Partial data failure degrades gracefully: a failed or missing price fetch for one row is reported on that row alone; it never blanks the whole list or holds the view past the responsiveness budget.
- Watchlist privacy between accounts: no account can read another account's watchlist, symbols, or scan results under any normal operation.
- Formation analysis runs on daily candles: the scanned price series for each watchlist entry consists of daily-candle periods, not intraday/tick data, so the formation analysis reflects a daily-investor decision horizon rather than short-term noise.

## Business Logic

For each stock on the user's watchlist, the app assesses — based on the most recent price series fetched from a free market-data API — whether there is a high probability that a trend-reversal formation (double top or RGR) is currently forming, and presents the strength of that signal as a graded recommendation to consider selling.

Inputs (user-facing, not components): the set of stocks the user has added to their watchlist (id + name/symbol), and the live price series retrieved for each.

Output: a graded sell-signal for each watchlist entry — not a binary detection flag, but a measure of how strongly the price series currently indicates a bearish reversal is forming.

How the user encounters it: after login, the watchlist view auto-scans each entry and renders the graded signal beside the ticker, so the investor can scan the whole list visually for the strongest sell candidates and decide which positions deserve a closer look.

High-probability threshold (principle): a formation is flagged as "high probability of completing" when the detector reports high confidence that an in-progress pattern will reach completion — i.e., the signal graduates from forming to actionable. The exact numerical cut-off for "high confidence" is a downstream decision pinned during stack selection / algorithm tuning, not a value fixed by the product rule; the PRD commits to the principle (graded, confidence-graduated flags; one threshold separates "forming" from "high-probability forming"), and downstream picks the number.

## Access Control

### Login model

- Login to a user account (email + password — typical web login model).
- Registration available to every individual investor (no restrictions in the MVP).

### Roles and permissions

- Flat model: all users are equal.
- Each user sees only their own account and own watchlist.
- No administrator roles in the MVP — there's no need to manage other users.
- Frontend protected: an unauthenticated user lands on the login screen; an authenticated user sees only their own data.
- No public, anonymous access to any data.

## Non-Goals

- No real-time push notifications or scheduled email alerts: scanning happens on login / view-open; the app does not ping or email the user when a signal appears.
- No portfolio accounting: the watchlist is a scan-candidate list, not a holdings tracker. Cost basis, realized/unrealized P&L, dividends, and position sizing are out of scope.
- No automated trade execution or broker integration: the app only *recommends* considering a sell; it does not place, route, or sync orders to any broker.
- No backtesting: the MVP runs on the live daily-candle series only; strategy validation against historical data is deferred to a later version.

## Open Questions

(None currently open.)

> Resolved (no longer open):
> - **FR-009 pattern scope — double top, RGR, or both in the MVP?** — Resolved by user on 2026-09-20: ship detection for both double top and RGR in the MVP. Reflected in FR-009's Socrates resolution clause.
> - **target_scale qps & data_volume** — Resolved by user on 2026-09-20: qps = `low`, data_volume = `small` (Proposal A, schema-idiomatic). Reflected in frontmatter. Note: the downstream *external* free price-data API rate limit (FR-008) remains a stack-selection concern for `/10x-tech-stack-selector`, not a target_scale field.
> - **FR-009 probability threshold — what precise value defines "high probability of formation"?** — Resolved by user on 2026-09-20 (Proposal A): the product rule commits to the *principle* (graded, confidence-graduated signals; one high-probability threshold separates "forming" from "high-probability forming"); the exact numerical cut-off is deferred to downstream stack selection / algorithm tuning and recorded as a supporting clause in `## Business Logic`. The PRD pins the principle, not the number.
